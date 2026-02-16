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

# Dovecot is installed by the pyinfra install stage below (DovecotDeployer),
# which downloads+verifies SHA256 hashes from the canonical source in
# cmdeploy/src/cmdeploy/dovecot/deployer.py — no need to duplicate here.
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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/chatmail

# --- Build-time: install cmdeploy venv and run install stage ---
# Editable install so importlib.resources reads directly from the source tree.
# On container start only "configure,activate" stages run.
COPY . /opt/chatmail/
WORKDIR /opt/chatmail

RUN printf '[params]\nmail_domain = build.local\n' > /tmp/chatmail.ini

RUN python3 -m venv /opt/cmdeploy && \
    /opt/cmdeploy/bin/pip install --no-cache-dir \
        -e chatmaild/ -e cmdeploy/

RUN CMDEPLOY_STAGES=install \
    CHATMAIL_INI=/tmp/chatmail.ini \
    CHATMAIL_NOSYSCTL=True \
    CHATMAIL_NOPORTCHECK=True \
    /opt/cmdeploy/bin/pyinfra @local \
        /opt/chatmail/cmdeploy/src/cmdeploy/run.py -y

RUN cp -a www/ /opt/chatmail-www/

RUN rm -f /tmp/chatmail.ini
# --- End build-time install ---

ENV CHATMAIL_INI=/etc/chatmail/chatmail.ini
ENV PATH="/opt/cmdeploy/bin:${PATH}"
RUN ln -s /etc/chatmail/chatmail.ini /opt/chatmail/chatmail.ini

ARG SETUP_CHATMAIL_SERVICE_PATH=/lib/systemd/system/setup_chatmail.service
COPY ./docker/files/setup_chatmail.service "$SETUP_CHATMAIL_SERVICE_PATH"
RUN ln -sf "$SETUP_CHATMAIL_SERVICE_PATH" "/etc/systemd/system/multi-user.target.wants/setup_chatmail.service"

COPY --chmod=555 ./docker/files/setup_chatmail_docker.sh /setup_chatmail_docker.sh
COPY --chmod=555 ./docker/files/entrypoint.sh /entrypoint.sh

VOLUME ["/sys/fs/cgroup", "/home"]

STOPSIGNAL SIGRTMIN+3

ENTRYPOINT ["/entrypoint.sh"]

CMD [   "--default-standard-output=journal+console", \
        "--default-standard-error=journal+console" ]

