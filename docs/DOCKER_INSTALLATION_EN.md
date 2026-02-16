# Known issues and limitations

- Requires cgroups v2 configured in the system. Operation with cgroups v1 has not been tested.
- Yes, of course, using systemd inside a container is a hack, and it would be better to split it into several services, but since this is an MVP, it turned out to be easier to do it this way initially than to rewrite the entire deployment system.
- The Docker image is only suitable for amd64. If you need to run it on a different architecture, try modifying the Dockerfile (specifically the part responsible for installing dovecot).

# Docker installation
This section provides instructions for installing Chatmail using Docker Compose.

**Note:** Docker Compose v2 is required (`docker compose`, not `docker-compose`) for its support of the `cgroup: host` option in `docker-compose.yaml` is only supported by Compose v2.
[see documentation](https://docs.docker.com/engine/install/debian/#install-using-the-repository)
```shell
apt install docker-ce docker-compose-plugin docker.io- docker-compose-
```

## Preliminary setup
We use `chat.example.org` as the Chatmail domain in the following steps.
Please substitute it with your own domain.

1. Setup the initial DNS records.
   The following is an example in the familiar BIND zone file format with
   a TTL of 1 hour (3600 seconds).
   Please substitute your domain and IP addresses.

   ```
    chat.example.com. 3600 IN A 198.51.100.5
    chat.example.com. 3600 IN AAAA 2001:db8::5
    www.chat.example.com. 3600 IN CNAME chat.example.com.
    mta-sts.chat.example.com. 3600 IN CNAME chat.example.com.
   ```

2. Configure kernel parameters because they cannot be changed inside the container, specifically `fs.inotify.max_user_instances` and `fs.inotify.max_user_watches`. Run the following:

```shell
echo "fs.inotify.max_user_instances=65536" | sudo tee -a /etc/sysctl.d/99-inotify.conf
echo "fs.inotify.max_user_watches=65536" | sudo tee -a /etc/sysctl.d/99-inotify.conf
sudo sysctl --system
```

## Building the image

Clone the repository and build the Docker image:

```shell
git clone https://github.com/chatmail/relay
cd relay
docker compose build chatmail
```

The build bakes all binaries, Python packages, and the install stage into the image. After building, only `docker-compose.yaml` and `.env` are needed to run the container.

## Running with Docker Compose

1. Copy `docker-compose.yaml` and `docker/example.env` into a working directory:

```shell
cp docker-compose.yaml /path/to/your/workdir/
cp docker/example.env /path/to/your/workdir/.env
```

If you are running from the cloned repo directory, just copy the env file:

```shell
cp ./docker/example.env .env
```

2. Configure environment variables in the `.env` file.
   Below is the list of variables used during deployment:

- `MAIL_DOMAIN` – The domain name of the future server. (required)
- `DEBUG_COMMANDS_ENABLED` – Run debug commands before installation. (default: `false`)
- `FORCE_REINIT_INI_FILE` – Recreate the ini configuration file on startup. (default: `false`)
- `USE_FOREIGN_CERT_MANAGER` – Use a third-party certificate manager. (default: `false`)
- `PATH_TO_SSL` – Path to where the certificates are stored. (default: `/var/lib/acme/live/${MAIL_DOMAIN}`)
- `ENABLE_CERTS_MONITORING` – Enable certificate monitoring if `USE_FOREIGN_CERT_MANAGER=true`. If certificates change, services will be automatically restarted. (default: `false`)
- `CERTS_MONITORING_TIMEOUT` – Interval in seconds to check if certificates have changed. (default: `60`)
- `CMDEPLOY_STAGES` – Deployment stages to run on container start. (default: `"configure,activate"`). Set to `"install,configure,activate"` to force a full reinstall.

You can also use any variables from the [ini configuration file](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/ini/chatmail.ini.f); they must be in uppercase.

3. Start the container:

```shell
docker compose up -d # start service
docker compose logs -f chatmail # view container logs, press CTRL+C to exit
```

4. After installation is complete, you can open `https://<your_domain_name>` in your browser.

## Managing the server

Use `docker exec` to run cmdeploy commands inside the container:

```shell
# Show required DNS records
docker exec chatmail /opt/cmdeploy/bin/cmdeploy dns --ssh-host @docker

# Check server status
docker exec chatmail /opt/cmdeploy/bin/cmdeploy status --ssh-host @docker

# Run benchmarks (can also run from any machine with cmdeploy installed)
docker exec chatmail /opt/cmdeploy/bin/cmdeploy bench chat.example.com
```

## Customization

### Custom website

You can customize the Chatmail landing page by mounting a directory with your own website source files.

1. Create a directory with your custom website source:

```shell
mkdir -p ./custom/www/src
nano ./custom/www/src/index.md
```

2. In `docker-compose.yaml`, uncomment or add the website volume mount:

```yaml
services:
  chatmail:
    volumes:
      ...
      - ./custom/www:/opt/chatmail-www
```

3. Restart the service:

```shell
docker compose down
docker compose up -d
```

### Custom chatmail.ini

Instead of using environment variables, you can mount your own `chatmail.ini` configuration file. This is useful if you prefer managing the full ini file directly or want to share one configuration across environments.

1. In `docker-compose.yaml`, uncomment or add the ini volume mount:

```yaml
services:
  chatmail:
    volumes:
      ...
      - ./chatmail.ini:/etc/chatmail/chatmail.ini
```

2. Environment variables from `.env` are still applied on top of the mounted file at container start, so you can combine both approaches.

## Migrating from a bare-metal install

If you have an existing bare-metal Chatmail installation and want to switch to Docker:

1. Stop all existing services:

```shell
systemctl stop postfix dovecot doveauth nginx opendkim unbound acmetool-redirector \
  filtermail filtermail-incoming chatmail-turn iroh-relay chatmail-metadata \
  lastlogin mtail
systemctl disable postfix dovecot doveauth nginx opendkim unbound acmetool-redirector \
  filtermail filtermail-incoming chatmail-turn iroh-relay chatmail-metadata \
  lastlogin mtail
```

2. Convert your existing `chatmail.ini` to the Docker `.env` format:

```shell
python3 docker/cm_ini_to_env.py /usr/local/lib/chatmaild/chatmail.ini .env
```

or mount it (see above).

3. Copy persistent data into the `./data/` subdirectories:

```shell
mkdir -p data/chatmail-dkimkeys data/chatmail-acme data/chatmail

# DKIM keys
cp -a /etc/dkimkeys/* data/chatmail-dkimkeys/

# ACME certificates and account
rsync -a /var/lib/acme/ data/chatmail-acme/

# Mail data
rsync -a /home/ data/chatmail/
```

Alternatively, you can mount `/home/vmail` directly by changing the volume in `docker-compose.yaml`:

```yaml
- /home/vmail:/home/vmail
```

The three `./data/` subdirectories cover all persistent state. Everything else is regenerated by the `configure` and `activate` stages on container start.

## Forcing a full reinstall

The Docker image bakes the install stage (binary downloads, package setup, chatmaild venv) into the image at build time. On container start, only the `configure` and `activate` stages run by default.

To force a full reinstall (e.g., after updating the source), either rebuild the image:

```shell
docker compose build chatmail
docker compose up -d
```

Or override the stages at runtime without rebuilding:

```shell
CMDEPLOY_STAGES="install,configure,activate" docker compose up -d
```
