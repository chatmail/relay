import importlib.resources
import os

import pyinfra

from cmdeploy import deploy_chatmail


def main():
    config_path = os.getenv(
        "CHATMAIL_INI",
        importlib.resources.files("cmdeploy").joinpath("../../../chatmail.ini"),
    )
    disable_mail = bool(os.environ.get("CHATMAIL_DISABLE_MAIL"))

    deploy_chatmail(config_path, disable_mail)


if pyinfra.is_cli:
    main()
