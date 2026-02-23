# syntax=docker/dockerfile:1
FROM jrei/systemd-debian:12 AS base

ENV LANG=en_US.UTF-8

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    echo 'APT::Install-Recommends "0";' > /etc/apt/apt.conf.d/01norecommend && \
    echo 'APT::Install-Suggests "0";' >> /etc/apt/apt.conf.d/01norecommend && \
    apt-get update && \
    apt-get install -y \
        ca-certificates \
        git \
        python3 \
        python3-venv \
        gcc \
        python3-dev && \
    DEBIAN_FRONTEND=noninteractive TZ=UTC \
    apt-get install -y tzdata locales && \
    sed -i -e "s/# $LANG.*/$LANG UTF-8/" /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=$LANG

# --- Build-time: install cmdeploy venv and run install stage ---
# Editable install so importlib.resources reads directly from the source tree.
# On container start only "configure,activate" stages run.

# Copy dependency metadata first so pip install layer is cached
COPY cmdeploy/pyproject.toml /opt/chatmail/cmdeploy/pyproject.toml
COPY chatmaild/pyproject.toml /opt/chatmail/chatmaild/pyproject.toml

# Dummy scaffolding so editable install can discover packages
RUN mkdir -p /opt/chatmail/cmdeploy/src/cmdeploy \
             /opt/chatmail/chatmaild/src/chatmaild && \
    touch /opt/chatmail/cmdeploy/src/cmdeploy/__init__.py \
          /opt/chatmail/chatmaild/src/chatmaild/__init__.py

# Dummy git repo: .git/ is excluded from the build context (.dockerignore)
# but setuptools calls `git ls-files` when building the sdist.
WORKDIR /opt/chatmail
RUN --mount=type=cache,target=/root/.cache/pip \
    git init -q && \
    python3 -m venv /opt/cmdeploy && \
    /opt/cmdeploy/bin/pip install -e chatmaild/ -e cmdeploy/

# Full source copy (editable install's .egg-link still points here)
COPY . /opt/chatmail/

RUN printf '[params]\nmail_domain = build.local\n' > /tmp/chatmail.ini

RUN CMDEPLOY_STAGES=install \
    CHATMAIL_INI=/tmp/chatmail.ini \
    CHATMAIL_NOSYSCTL=True \
    CHATMAIL_NOPORTCHECK=True \
    /opt/cmdeploy/bin/pyinfra @local \
        /opt/chatmail/cmdeploy/src/cmdeploy/run.py -y

RUN cp -a www/ /opt/chatmail-www/

RUN rm -f /tmp/chatmail.ini

# Record image version (used in deploy fingerprint at runtime).
# GIT_HASH is passed as a build arg (from docker-compose or CI) so that
# .git/ can be excluded from the build context via .dockerignore.
ARG GIT_HASH=unknown
RUN echo "$GIT_HASH" > /etc/chatmail-image-version && \
    echo "$GIT_HASH" > /etc/chatmail-version
# --- End build-time install ---

ENV TZ=:/etc/localtime
ENV PATH="/opt/cmdeploy/bin:${PATH}"
RUN ln -s /etc/chatmail/chatmail.ini /opt/chatmail/chatmail.ini

ARG CHATMAIL_INIT_SERVICE_PATH=/lib/systemd/system/chatmail-init.service
COPY ./docker/files/chatmail-init.service "$CHATMAIL_INIT_SERVICE_PATH"
RUN ln -sf "$CHATMAIL_INIT_SERVICE_PATH" "/etc/systemd/system/multi-user.target.wants/chatmail-init.service"

# Remove default nginx site config at build time (not in entrypoint)
RUN rm -f /etc/nginx/sites-enabled/default

COPY --chmod=555 ./docker/files/chatmail-init.sh /chatmail-init.sh
COPY --chmod=555 ./docker/files/entrypoint.sh /entrypoint.sh

# Certificate monitoring as a proper systemd timer (not a background process)
COPY --chmod=555 ./docker/files/chatmail-certmon.sh /chatmail-certmon.sh
COPY ./docker/files/chatmail-certmon.service /lib/systemd/system/chatmail-certmon.service
COPY ./docker/files/chatmail-certmon.timer /lib/systemd/system/chatmail-certmon.timer
RUN ln -sf /lib/systemd/system/chatmail-certmon.timer /etc/systemd/system/timers.target.wants/chatmail-certmon.timer

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD systemctl is-active dovecot postfix nginx unbound opendkim filtermail doveauth chatmail-metadata || exit 1

STOPSIGNAL SIGRTMIN+3

ENTRYPOINT ["/entrypoint.sh"]

CMD [   "--default-standard-output=journal+console", \
        "--default-standard-error=journal+console" ]
