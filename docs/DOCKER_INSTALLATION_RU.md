# Docker Installation (Русский)

> **Этот документ устарел.** Актуальная документация по установке Docker доступна в
> [DOCKER_INSTALLATION_EN.md](DOCKER_INSTALLATION_EN.md).
>
> This document is outdated. See [DOCKER_INSTALLATION_EN.md](DOCKER_INSTALLATION_EN.md) for current Docker installation instructions.

## Краткая инструкция

1. Установите Docker Compose v2 (`docker compose`, не `docker-compose`).

2. Клонируйте репозиторий и соберите образ:
```shell
git clone https://github.com/chatmail/relay
cd relay
docker compose build chatmail
```

3. Скопируйте `docker/example.env` в `.env` и укажите `MAIL_DOMAIN`:
```shell
cp docker/example.env .env
# отредактируйте .env — установите MAIL_DOMAIN
```

4. Запустите:
```shell
docker compose up -d
docker compose logs -f chatmail
```

Подробности: [DOCKER_INSTALLATION_EN.md](DOCKER_INSTALLATION_EN.md)
