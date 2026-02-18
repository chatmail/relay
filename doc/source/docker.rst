Docker installation
===================

This section provides instructions for installing a chatmail relay
using Docker Compose.

.. note::

   Docker support is experimental and not yet covered by automated tests, please report bugs.


Known limitations
-----------------

- Requires cgroups v2 on the host. Operation with cgroups v1 has not been tested.
- This preliminary image simply wraps the cmdeploy process detailed in the :doc:`getting_started` instructions in a full Debian-systemd image. 
- Currently, the image has only been tested and built on amd64, though arm64 should theoretically work as well.


Prerequisites
-------------

- **Docker Compose v2** (``docker compose``, not ``docker-compose``) is
  required for its ``cgroup: host`` support (`Install instructions <https://docs.docker.com/engine/install/debian/#install-using-the-repository>`_:)

- **DNS records** for your domain (see step 1 below).

- **Kernel parameters** — ``fs.inotify.max_user_instances`` and
  ``fs.inotify.max_user_watches`` must be raised on the host because they
  cannot be changed inside the container (see step 2 below).


Preliminary setup
-----------------

We use ``chat.example.org`` as the chatmail domain in the following
steps. Please substitute it with your own domain.

1. Setup the initial DNS records.
   The following is an example in the familiar BIND zone file format with
   a TTL of 1 hour (3600 seconds).
   Please substitute your domain and IP addresses.

   ::

       chat.example.org. 3600 IN A 198.51.100.5
       chat.example.org. 3600 IN AAAA 2001:db8::5
       www.chat.example.org. 3600 IN CNAME chat.example.org.
       mta-sts.chat.example.org. 3600 IN CNAME chat.example.org.

2. Configure kernel parameters on the host, as these can not be set from the container::

       echo "fs.inotify.max_user_instances=65536" | sudo tee -a /etc/sysctl.d/99-inotify.conf
       echo "fs.inotify.max_user_watches=65536" | sudo tee -a /etc/sysctl.d/99-inotify.conf
       sudo sysctl --system


Docker Compose Setup
--------------------

Pre-built images are available from GitHub Container Registry. The
``main`` branch and tagged releases are pushed automatically by CI::

    docker pull ghcr.io/chatmail/relay:main      # latest main branch
    docker pull ghcr.io/chatmail/relay:1.2.3     # tagged release


Create service directory
^^^^^^^^^^^^^^^^^^^^^^^^

Either:

- Create a service directory, e.g., `/srv/chatmail-relay`::

    mkdir -p /srv/chatmail-relay && cd /srv/chatmail-relay
    wget https://raw.githubusercontent.com/chatmail/relay/refs/heads/main/docker-compose.yaml https://raw.githubusercontent.com/chatmail/relay/refs/heads/main/docker-compose.override.yaml.example
    wget https://raw.githubusercontent.com/chatmail/relay/refs/heads/main/docker/env.example -O .env
    

- or clone the chatmail repo ::

   git clone https://github.com/chatmail/relay
   cd relay
   cp example.env .env



Customize and start
^^^^^^^^^^^^^^^^^^^

1. All local customizations (data paths, extra volumes, config mounts) go in
   ``docker-compose.override.yaml``, which Compose merges automatically with
   the base file. By default, all data is stored in docker volumes, you will
   likely want to at least create and configure the mail storage location. Copy
   the example to get started::

       cp docker/docker-compose.override.yaml.example docker-compose.override.yaml
       # and edit docker-compose.override.yaml


2. Configure the ``.env`` file. Only ``MAIL_DOMAIN`` is required, the domain
   name of the future server.

   The container generates a ``chatmail.ini`` with defaults from
   ``MAIL_DOMAIN`` on first start. To customize chatmail settings, mount
   your own ``chatmail.ini`` instead (see `Custom chatmail.ini`_ below).

3. Start the container::

       docker compose up -d
       docker compose logs -f chatmail   # view logs, Ctrl+C to exit

4. After installation is complete, open ``https://chat.example.org`` in
   your browser.


Managing the server
-------------------

Use ``docker exec`` to run cmdeploy commands inside the container::

    # Show required DNS records
    docker exec chatmail /opt/cmdeploy/bin/cmdeploy dns --ssh-host @local

    # Check server status
    docker exec chatmail /opt/cmdeploy/bin/cmdeploy status --ssh-host @local

    # Run benchmarks (can also run from any machine with cmdeploy installed)
    docker exec chatmail /opt/cmdeploy/bin/cmdeploy bench chat.example.org


Customization
-------------

Custom website
^^^^^^^^^^^^^^

You can customize the chatmail landing page by mounting a directory with
your own website source files.

1. Create a directory with your custom website source::

       mkdir -p ./custom/www/src
       nano ./custom/www/src/index.md

2. Add the volume mount in ``docker-compose.override.yaml``::

       services:
         chatmail:
           volumes:
             - ./custom/www:/opt/chatmail-www

3. Restart the service::

       docker compose down
       docker compose up -d


Custom chatmail.ini
^^^^^^^^^^^^^^^^^^^

There are two configuration modes:

**Simple (default):** Set ``MAIL_DOMAIN`` in ``.env``. The container
auto-generates ``chatmail.ini`` with defaults on first start. This is
sufficient for most deployments.

**Advanced:** Generate a ``chatmail.ini``, edit it, and mount it into
the container. This gives you full control over all chatmail settings.

1. Extract the generated config from a running container::

       docker cp chatmail:/etc/chatmail/chatmail.ini ./chatmail.ini

2. Edit ``chatmail.ini`` as needed.

3. Add the volume mount in ``docker-compose.override.yaml`` ::

       services:
         chatmail:
           volumes:
             - ./chatmail.ini:/etc/chatmail/chatmail.ini

4. Restart the container, the container skips generating a new one: ::

       docker compose down && docker compose up -d


Migrating from a bare-metal install
------------------------------------

If you have an existing bare-metal chatmail installation and want to
switch to Docker:

1. Stop all existing services::

       systemctl stop postfix dovecot doveauth nginx opendkim unbound \
         acmetool-redirector filtermail filtermail-incoming chatmail-turn \
         iroh-relay chatmail-metadata lastlogin mtail
       systemctl disable postfix dovecot doveauth nginx opendkim unbound \
         acmetool-redirector filtermail filtermail-incoming chatmail-turn \
         iroh-relay chatmail-metadata lastlogin mtail

2. Copy your existing ``chatmail.ini`` and mount it into the container
   (see `Custom chatmail.ini`_ above)::

       cp /usr/local/lib/chatmaild/chatmail.ini ./chatmail.ini

3. Copy persistent data into the ``./data/`` subdirectories (for example, as configured in `Customize and start`_) ::

       mkdir -p data/chatmail-dkimkeys data/chatmail-acme data/chatmail

       # DKIM keys
       cp -a /etc/dkimkeys/* data/chatmail-dkimkeys/

       # ACME certificates and account
       rsync -a /var/lib/acme/ data/chatmail-acme/

       # Mail data
       rsync -a /home/ data/chatmail/

   Alternatively, mount ``/home/vmail`` directly by changing the volume
   in ``docker-compose-override.yaml``::

       - /home/vmail:/home/vmail

   The three ``./data/`` subdirectories cover all persistent state.
   Everything else is regenerated by the ``configure`` and ``activate``
   stages on container start.

Building the image
------------------

Clone the repository and build the Docker image::

    git clone https://github.com/chatmail/relay
    cd relay
    docker compose build chatmail

The build bakes all binaries, Python packages, and the install stage
into the image. After building, only ``docker-compose.yaml`` and ``.env``
are needed to run the container.

You can transfer a locally built image to your server directly (pigz is parallel `gzip` which can be used instead as well) ::

    docker save chatmail-relay:latest | pigz | ssh chat.example.org 'pigz -d | docker load'


Forcing a full reinstall
------------------------

On container start, only the ``configure`` and ``activate`` stages run by default.

To force a full reinstall (e.g. after updating the source), either
rebuild the image::

    docker compose build chatmail
    docker compose up -d

Or override the stages at runtime without rebuilding::

    CMDEPLOY_STAGES="install,configure,activate" docker compose up -d
