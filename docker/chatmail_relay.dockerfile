FROM jrei/systemd-debian:12 AS base

ENV LANG=en_US.UTF-8

RUN echo 'APT::Install-Recommends "0";' > /etc/apt/apt.conf.d/01norecommend && \
    echo 'APT::Install-Suggests "0";' >> /etc/apt/apt.conf.d/01norecommend && \
    apt-get update && \
    apt-get install -y \
        ca-certificates && \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/London \
    apt-get install -y tzdata && \
    apt-get install -y locales && \
    sed -i -e "s/# $LANG.*/$LANG UTF-8/" /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=$LANG \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && \
    apt-get install -y \
        git \
        python3 \
        python3-venv \
        python3-virtualenv \
        gcc \
        python3-dev \
        opendkim \
        opendkim-tools \
        curl \
        rsync \
        unbound \
        unbound-anchor \
        dnsutils \
        postfix \
        acl \
        nginx \
        libnginx-mod-stream \
        fcgiwrap \
        cron \
    && for pkg in core imapd lmtpd; do \
      case "$pkg" in \
        core) sha256="43f593332e22ac7701c62d58b575d2ca409e0f64857a2803be886c22860f5587" ;; \
        imapd) sha256="8d8dc6fc00bbb6cdb25d345844f41ce2f1c53f764b79a838eb2a03103eebfa86" ;; \
        lmtpd) sha256="2f69ba5e35363de50962d42cccbfe4ed8495265044e244007d7ccddad77513ab" ;; \
      esac; \
      url="https://download.delta.chat/dovecot/dovecot-${pkg}_2.3.21%2Bdfsg1-3_amd64.deb"; \
      file="/tmp/$(basename "$url")"; \
      curl -fsSL "$url" -o "$file"; \
      echo "$sha256  $file" | sha256sum -c -; \
      apt-get install -y "$file"; \
      rm -f "$file"; \
    done \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/chatmail

# --- Build-time install stage ---
# Bake the "install" deployer stage into the image; we can't use
# scripts/initenv.sh because /opt/chatmail is empty at build time as 
# source arrives at runtime via volume mount., so we use a throwaway venv.
# On container start only "configure,activate" stages run.
COPY . /tmp/chatmail-src/
WORKDIR /tmp/chatmail-src

# Dummy config — deploy_chatmail() needs a parseable ini to instantiate deployers
RUN printf '[params]\nmail_domain = build.local\n' > /tmp/chatmail.ini

# Do what initenv.sh would do without the docs
RUN python3 -m venv /tmp/build-venv && \
    /tmp/build-venv/bin/pip install --no-cache-dir \
        -e chatmaild -e cmdeploy

RUN CMDEPLOY_STAGES=install \
    CHATMAIL_INI=/tmp/chatmail.ini \
    CHATMAIL_DOCKER=True \
    /tmp/build-venv/bin/pyinfra @local \
        /tmp/chatmail-src/cmdeploy/src/cmdeploy/run.py -y

RUN rm -rf /tmp/chatmail-src /tmp/build-venv /tmp/chatmail.ini

WORKDIR /opt/chatmail
# --- End build-time install stage ---

ARG SETUP_CHATMAIL_SERVICE_PATH=/lib/systemd/system/setup_chatmail.service
COPY ./docker/files/setup_chatmail.service "$SETUP_CHATMAIL_SERVICE_PATH"
RUN ln -sf "$SETUP_CHATMAIL_SERVICE_PATH" "/etc/systemd/system/multi-user.target.wants/setup_chatmail.service"

COPY --chmod=555 ./docker/files/setup_chatmail_docker.sh /setup_chatmail_docker.sh
COPY --chmod=555 ./docker/files/update_ini.sh /update_ini.sh
COPY --chmod=555 ./docker/files/entrypoint.sh /entrypoint.sh

VOLUME ["/sys/fs/cgroup", "/home"]

STOPSIGNAL SIGRTMIN+3

ENTRYPOINT ["/entrypoint.sh"]

CMD [   "--default-standard-output=journal+console", \
        "--default-standard-error=journal+console" ]

