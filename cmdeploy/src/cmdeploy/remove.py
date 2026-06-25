import importlib.resources
import os

import pyinfra

# pyinfra runs this module as a python file and not as a module so
# import paths must be absolute
from cmdeploy.removers import remove_chatmail


def main():
    config_path = os.getenv(
        "CHATMAIL_INI",
        importlib.resources.files("cmdeploy").joinpath("../../../chatmail.ini"),
    )
    keep_packages = bool(os.environ.get("CHATMAIL_KEEP_PACKAGES"))

    remove_chatmail(config_path, keep_packages=keep_packages)


if pyinfra.is_cli:
    main()
