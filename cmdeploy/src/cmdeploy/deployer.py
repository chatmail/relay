import os

from pyinfra.operations import server


class Deployer:

    def __init__(self):
        default_stages = "install,configure,activate"
        self.stages = os.getenv("CMDEPLOY_STAGES", default_stages).split(",")
        self.need_restart = False

    def install(self):
        if "install" not in self.stages:
            return

        # optional 'required_users' contains a list of (user, group, secondary-group-list) tuples.
        # If the group is None, no group is created corresponding to that user.
        # If the secondary group list is not None, all listed groups are created as well.
        required_users = getattr(self, "required_users", [])
        for user, group, groups in required_users:
            if group is not None:
                server.group(
                    name="Create {} group".format(group), group=group, system=True
                )
            if groups is not None:
                for group2 in groups:
                    server.group(
                        name="Create {} group".format(group2), group=group2, system=True
                    )
            server.user(
                name="Create {} user".format(user),
                user=user,
                group=group,
                groups=groups,
                system=True,
            )

        self.need_restart |= bool(self.install_impl())

    #
    # If a subclass overrides this with a method that returns a true
    # value, self.need_restart will be set when install() is called.
    #
    @staticmethod
    def install_impl():
        pass

    def configure(self):
        if "configure" in self.stages:
            self.configure_impl()

    def configure_impl(self):
        pass

    def activate(self):
        if "activate" in self.stages:
            self.activate_impl()

    def activate_impl(self):
        pass
