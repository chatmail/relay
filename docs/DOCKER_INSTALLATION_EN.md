# Known issues and limitations

- Chatmail will be reinstalled every time the container is started (longer the first time, faster on subsequent starts). This is how the original installer works because it wasn’t designed for Docker. At the end of the documentation, there’s a [proposed solution](#locking-the-chatmail-version).
- Requires cgroups v2 configured in the system. Operation with cgroups v1 has not been tested.
- Yes, of course, using systemd inside a container is a hack, and it would be better to split it into several services, but since this is an MVP, it turned out to be easier to do it this way initially than to rewrite the entire deployment system.
- The Docker image is only suitable for amd64. If you need to run it on a different architecture, try modifying the Dockerfile (specifically the part responsible for installing dovecot).

# Docker installation
This section provides instructions for installing Chatmail using docker-compose.

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

2. clone the repository on your server.

   ```shell
    git clone https://github.com/chatmail/relay
    cd relay
   ```

## Installation

1. Copy the file `./docker/docker-compose-default.yaml` to `docker-compose.yaml`. This is necessary because `docker-compose.yaml` is in `.gitignore` and won’t cause conflicts when updating the git repository.

```shell
cp ./docker/docker-compose-default.yaml docker-compose.yaml
```

3. Configure environment variables in the `.env` file. These variables are used in the `docker-compose.yaml` file to pass repeated values.

4. Configure kernel parameters because they cannot be changed inside the container, specifically `fs.inotify.max_user_instances` and `fs.inotify.max_user_watches`. Run the following:

```shell
echo "fs.inotify.max_user_instances=65536" | sudo tee -a /etc/sysctl.d/99-inotify.conf
echo "fs.inotify.max_user_watches=65536" | sudo tee -a /etc/sysctl.d/99-inotify.conf
sudo sysctl --system
```

5. Configure container environment variables. Below is the list of variables used during deployment:

- `MAIL_DOMAIN` – The domain name of the future server. (required)
- `DEBUG_COMMANDS_ENABLED` – Run debug commands before installation. (default: `false`)
- `FORCE_REINIT_INI_FILE` – Recreate the ini configuration file on startup. (default: `false`)
- `USE_FOREIGN_CERT_MANAGER` – Use a third-party certificate manager. (default: `false`)
- `RECREATE_VENV` - Recreate the virtual environment (venv). If set to `true`, the environment will be recreated when the container starts, which will increase the startup time of the service but can help avoid certain errors. (default: `false`)
- `INI_FILE` – Path to the ini configuration file. (default: `./chatmail.ini`)
- `PATH_TO_SSL` – Path to where the certificates are stored. (default: `/var/lib/acme/live/${MAIL_DOMAIN}`)
- `ENABLE_CERTS_MONITORING` – Enable certificate monitoring if `USE_FOREIGN_CERT_MANAGER=true`. If certificates change, services will be automatically restarted. (default: `false`)
- `CERTS_MONITORING_TIMEOUT` – Interval in seconds to check if certificates have changed. (default: `'60'`)

You can also use any variables from the [ini configuration file](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/ini/chatmail.ini.f); they must be in uppercase.

Mandatory variables for deployment via Docker:

- `CHANGE_KERNEL_SETTINGS` – Change kernel settings (`fs.inotify.max_user_instances` and `fs.inotify.max_user_watches`) on startup. Changing kernel settings inside the container is not possible! (default: `False`)

6. Build the Docker image:

```shell
docker compose build chatmail
```

7. Start docker compose and wait for the installation to finish:

```shell
docker compose up -d # start service
docker compose logs -f chatmail # view container logs, press CTRL+C to exit
```

8. After installation is complete, you can open `https://<your_domain_name>` in your browser.

## Using custom files

When using Docker, you can apply modified configuration files to make the installation more personalized. This is usually needed for the `www/src` section so that the Chatmail landing page is customized to your taste, but it can be used for any other cases as well.

To replace files correctly:

1. Create the `./custom` directory. It is in `.gitignore`, so it won’t cause conflicts when updating.

```shell
mkdir -p ./custom
```

2. Modify the required file. For example, `index.md`:

```shell
mkdir -p ./custom/www/src
nano ./custom/www/src/index.md
```

3. In `docker-compose.yaml`, add the file mount in the `volumes` section:

```yaml
services:
  chatmail:
    volumes:
      ...
      ## custom resources
      - ./custom/www/src/index.md:/opt/chatmail/www/src/index.md
```

4. Restart the service:

```shell
docker compose down
docker compose up -d
```

## Locking the Chatmail version

> [!note]
> These steps are optional and should only be done if you are not satisfied that the service is installed each time the container starts.

Since the current Docker version installs the Chatmail service every time the container starts, you can lock the container version after installation as follows:

1. Commit the current state of the configured container:

```shell
docker container commit chatmail configured-chatmail:$(date +'%Y-%m-%d')
docker image ls | grep configured-chatmail
```

2. Change the entrypoint for the container in `docker-compose.yaml` to:

```yaml
services:
  chatmail:
    image: <image name from step 1>
    volumes:
      ...
      ## custom resources
      - ./custom/setup_chatmail_docker.sh:/setup_chatmail_docker.sh
```

3. Create the file `./custom/setup_chatmail_docker.sh` with the new configuration:

```shell
mkdir -p ./custom
cat > ./custom/setup_chatmail_docker.sh << 'EOF'
#!/bin/bash

set -eo pipefail

export ENABLE_CERTS_MONITORING="${ENABLE_CERTS_MONITORING:-true}"
export CERTS_MONITORING_TIMEOUT="${CERTS_MONITORING_TIMEOUT:-60}"
export PATH_TO_SSL="${PATH_TO_SSL:-/var/lib/acme/live/${MAIL_DOMAIN}}"

calculate_hash() {
    find "$PATH_TO_SSL" -type f -exec sha1sum {} \; | sort | sha1sum | awk '{print $1}'
}

monitor_certificates() {
    if [ "$ENABLE_CERTS_MONITORING" != "true" ]; then
        echo "Certs monitoring disabled."
        exit 0
    fi

    current_hash=$(calculate_hash)
    previous_hash=$current_hash

    while true; do
        current_hash=$(calculate_hash)
        if [[ "$current_hash" != "$previous_hash" ]]; then
        # TODO: add an option to restart at a specific time interval 
            echo "[INFO] Certificate's folder hash was changed, restarting nginx, dovecot and postfix services."
            systemctl restart nginx.service
            systemctl reload dovecot.service
            systemctl reload postfix.service
            previous_hash=$current_hash
        fi
        sleep $CERTS_MONITORING_TIMEOUT
    done
}

monitor_certificates &
EOF
```

4. Restart the service:

```shell
docker compose down
docker compose up -d
```
