#!/usr/local/lib/chatmaild/venv/bin/python3

"""CGI script for creating new accounts."""

import json
import os
import random
import secrets
import string

from chatmaild.config import Config, read_config

CONFIG_PATH = "/usr/local/lib/chatmaild/chatmail.ini"
ALPHANUMERIC = string.ascii_lowercase + string.digits
ALPHANUMERIC_PUNCT = string.ascii_letters + string.digits + string.punctuation


def create_newemail_dict(config: Config):
    user = "".join(random.choices(ALPHANUMERIC, k=config.username_min_length))
    password = "".join(
        secrets.choice(ALPHANUMERIC_PUNCT)
        for _ in range(config.password_min_length + 3)
    )
    redirect_uri = os.getenv("REQUEST_URI")
    invite_token = redirect_uri[5:] if redirect_uri != "/new" else ""
    return dict(email=f"{user}@{config.mail_domain}", password=f"{invite_token}{password}")


def print_new_account():
    config = read_config(CONFIG_PATH)
    creds = create_newemail_dict(config)

    print("Content-Type: application/json")
    print("")
    print(json.dumps(creds))


if __name__ == "__main__":
    print_new_account()
