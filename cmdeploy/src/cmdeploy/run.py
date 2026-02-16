import importlib.resources
import os

import pyinfra

# pyinfra runs this module as a python file and not as a module so
# import paths must be absolute
from cmdeploy.deployers import deploy_chatmail


def main():
    config_path = os.getenv(
        "CHATMAIL_INI",
        importlib.resources.files("cmdeploy").joinpath("../../../chatmail.ini"),
    )
    disable_mail = bool(os.environ.get("CHATMAIL_DISABLE_MAIL"))
    website_only = bool(os.environ.get("CHATMAIL_WEBSITE_ONLY"))

    deploy_chatmail(config_path, disable_mail, website_only)


if pyinfra.is_cli:
    main()
