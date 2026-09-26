from pyinfra.operations import apt, server

from cmdeploy.basedeploy import Deployer


class WebsockifyDeployer(Deployer):
    def __init__(self, config):
        self.config = config

    def install(self):
        apt.packages(name="Install websockify", packages=["websockify"])

    def configure(self):
        self.ensure_systemd_unit("websockify/websockify-imap.service")
        self.ensure_systemd_unit("websockify/websockify-submission.service")

    def activate(self):
        self.ensure_service("websockify-imap.service")
        self.ensure_service("websockify-submission.service")
