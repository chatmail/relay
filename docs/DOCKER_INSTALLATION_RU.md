# Известные проблемы и ограничения
- Chatmail будет переустановлен при каждом запуске контейнера (при первом - долго, при последующих быстрее). Так устроен изначальный установщик, потому что он не был заточен под docker. В конце документации [представлено](#фиксирование-версии-chatmail) возможное решение
- Требуется настроенный в системе cgroups v2. Работа с cgroups v1 не тестировалась.
- Да, понятно дело что systemd использовать в контейнере костыль и надо это всё разнести на несколько сервисов, но это MVP и в первом приближении оказалось сделать проще так, чем переписывать всю систему развертывания.
- docker образ подходит только для amd64, если нужно запустить на другой архитектуре, попробуйте изменить dockerfile (конкретно ту часть что ответсвенна за установку dovecot)

# Docker installation
Здесь представлена инструкция по установке chatmail с помощью docker-compose.

## Предварительная настройка
We use `chat.example.org` as the chatmail domain in the following steps.
Please substitute it with your own domain. 

1. Настройте начальные записи DNS.Ниже приведен пример в привычном формате файла зоны BIND сTTL 1 час (3600 секунд).
   Замените домен и IP-адреса на свои.

   ```
    chat.example.com. 3600 IN A 198.51.100.5
    chat.example.com. 3600 IN AAAA 2001:db8::5
    www.chat.example.com. 3600 IN CNAME chat.example.com.
    mta-sts.chat.example.com. 3600 IN CNAME chat.example.com.
   ```

2. Склонируйте репозиторий на свой сервер.

   ```shell
    git clone https://github.com/chatmail/relay
    cd relay
   ```

## Installation

1. Скопировать файл `./docker/docker-compose-default.yaml` в `docker-compose.yaml`. Это нужно потому что `docker-compose.yaml` находится в `.gitignore` и не будет создавать конфликты при обновлении гит репозитория.
```shell
cp ./docker/docker-compose-default.yaml docker-compose.yaml
```

3. Настроить параметры ядра, потому что внутри контейнера их нельзя изменить, а конкретно `fs.inotify.max_user_instances` и `fs.inotify.max_user_watches`. Для этого выполнить следующее:
```shell
echo "fs.inotify.max_user_instances=65536" | sudo tee -a /etc/sysctl.d/99-inotify.conf
echo "fs.inotify.max_user_watches=65536" | sudo tee -a /etc/sysctl.d/99-inotify.conf
sudo sysctl --system
```

4. Настроить переменные окружения контейнера. Ниже перечислен список переменных учавствующих при развертывании.
- `MAIL_DOMAIN` - Доменное имя будущего сервера. (required)
- `DEBUG_COMMANDS_ENABLED` - Выполнить debug команды перед установкой. (default: `false`)
- `FORCE_REINIT_INI_FILE` - Пересоздавать ini файл конфигурации при запуске. (default: `false`)
- `USE_FOREIGN_CERT_MANAGER` - Использовать сторонний менеджер сертификатов. (default: `false`)
- `RECREATE_VENV` - Пересоздать виртуальное окружение (venv). Если выставлено `true`, то окружение будет пересоздано при запуске контейнера, из-за чего включение сервиса займет больше времени, но поможет избежать ряда ошибок. (default: `false`)
- `INI_FILE` - путь к ini файлу конфигурации. (default: `./chatmail.ini`)
- `PATH_TO_SSL_CONTAINER` - Путь где располагаются сертификаты. (default: `/var/lib/acme/live/${MAIL_DOMAIN}`)
- `ENABLE_CERTS_MONITORING` - Включить мониторинг сертификатов, если `USE_FOREIGN_CERT_MANAGER=true`.  Если сертфикаты изменятся сервисы будут автоматически перезапущены. (default: `false`)
- `CERTS_MONITORING_TIMEOUT` - Раз во сколько секунд проверять что изменились сертификаты. (default: `'60'`)

Также могут быть использованы все переменные из [ini файла конфигурации](https://github.com/chatmail/relay/blob/main/chatmaild/src/chatmaild/ini/chatmail.ini.f), они обязаны быть в uppercase формате. 

Ниже перечислены переменные, которые обязательны быть выставлены при развертывании через docker:
- `CHANGE_KERNEL_SETTINGS` - Менять настройки ядра (`fs.inotify.max_user_instances` и `fs.inotify.max_user_watches`) при запуске. При запуске в контейнере смена настроек ядра не может быть выполнена! (default: `False`)

5. Настроить переменные окружения в `.env` файле. Эти переменные используются в `docker-compose.yaml` файле, чтобы передавать повторяющиеся значения.

6. Собрать docker образ
```shell
docker compose build chatmail
```

7. Запустить docker compose и дождаться завершения установки
```shell
docker compose up -d # запуск сервиса
docker compose logs -f chatmail # просмотр логов контейнера. Для выхода нажать CTRL+C
```

8. По окончанию установки можно открыть в браузер `https://<your_domain_name>`

## Использование кастомных файлов
При использовании docker есть возможность использовать измененые файлы конфигурации, чтобы сделать установку более персонализированной. Обычно это требуется для секции `www/src`, чтобы ознакомительная страница Chatmail была сделана на ваш вкус. Но также это можно использовать и для любых других случаев.

Для того чтобы корректно выполнить подмену файлов необходимо 
1. создать каталог `./custom`, он находится в `.gitignore`, поэтому при обновлении не вызовет конфликтов.
```shell
mkdir -p ./custom
```

2. Изменить нужный файл. Для примера возьмем `index.md`
```shell
mkdir -p ./custom/www/src
nano ./custom/www/src/index.md
```

3. В `docker-compose.yaml` добавить монтирование файла с помощью секции `volumes`
```yaml
services:
  chatmail:
    volumes:
      ...
      ## custom resources
      - ./custom/www/src/index.md:/opt/chatmail/www/src/index.md
```

4. Перезапустить сервис
```shell
docker compose down
docker compose up -d
```

## Фиксирование версии Chatmail
> [!note]
> Это опциональные шаги, их делать требуется только если вас не устраивает что сервис устанавливается каждый раз при запуске

Поскольку в текущей версии docker chatmail сервис устанавливается каждый раз запуске контейнера, чтобы этого не происходило можно зафиксировать версию контейнера после установки. Делается это следующим образом:

1. Зафиксировать текущее состояние сконфигурированного контейнера
```shell
docker container commit chatmail configured-chatmail:$(date +'%Y-%m-%d')
docker image ls | grep configured-chatmail
```

2. Изменить entrypoint для контейнера в `docker-compose.yaml` на
```yaml
services:
  chatmail:
    image: <image name from step 1>
    volumes:
      ...
      ## custom resources
      - ./custom/setup_chatmail_docker.sh:/setup_chatmail_docker.sh
```

3. Создать файл `./custom/setup_chatmail_docker.sh` с новым файлом конфигурации
```shell
mkdir -p ./custom
cat > ./custom/setup_chatmail_docker.sh << 'EOF'
#!/bin/bash

set -eo pipefail

export ENABLE_CERTS_MONITORING="${ENABLE_CERTS_MONITORING:-true}"
export CERTS_MONITORING_TIMEOUT="${CERTS_MONITORING_TIMEOUT:-60}"
export PATH_TO_SSL_CONTAINER="${PATH_TO_SSL_CONTAINER:-/var/lib/acme/live/${MAIL_DOMAIN}}"

calculate_hash() {
    find "$PATH_TO_SSL_CONTAINER" -type f -exec sha1sum {} \; | sort | sha1sum | awk '{print $1}'
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

4. Перезапустить сервис
```shell
docker compose down
docker compose up -d
```
