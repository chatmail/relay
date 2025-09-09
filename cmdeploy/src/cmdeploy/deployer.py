import os

from pyinfra.operations import server


class Deployer:
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        default_stages = "install,configure,activate"
        stages = os.getenv("CMDEPLOY_STAGES", default_stages).split(",")

        self.run_install = "install" in stages
        self.run_configure = "configure" in stages
        self.run_activate = "activate" in stages
        self.need_restart = False

    #
    # In any override, this method should return a list of 3-element
    # (user, group, secondary-group-list) tuples.  If the group is None,
    # no group is created corresponding to that user.  If the secondary
    # group list is not None, the listed groups are created as well.
    #
    @staticmethod
    def required_users():
        return []

    def create_groups(self):
        if not self.run_install:
            return

        for user, group, groups in self.required_users():
            if group is not None:
                server.group(
                    name="Create {} group".format(group), group=group, system=True
                )
            if groups is not None:
                for group2 in groups:
                    server.group(
                        name="Create {} group".format(group2), group=group2, system=True
                    )

    def create_users(self):
        if not self.run_install:
            return

        for user, group, groups in self.required_users():
            server.user(
                name="Create {} user".format(user),
                user=user,
                group=group,
                groups=groups,
                system=True,
            )

    def install(self):
        if self.run_install:
            self.need_restart |= bool(self.install_impl())

    #
    # If a subclass overrides this with a method that returns a true
    # value, self.need_restart will be set when install() is called.
    #
    @staticmethod
    def install_impl():
        pass

    def configure(self):
        if self.run_configure:
            self.configure_impl()

    def configure_impl(self):
        pass

    def activate(self):
        if self.run_activate:
            self.activate_impl()

    def activate_impl(self):
        pass
