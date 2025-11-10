import os

from pyinfra.operations import server


class Deployment:
    def install(self, deployer):
        # optional 'required_users' contains a list of (user, group, secondary-group-list) tuples.
        # If the group is None, no group is created corresponding to that user.
        # If the secondary group list is not None, all listed groups are created as well.
        required_users = getattr(deployer, "required_users", [])
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

        ret = bool(deployer.install())
        if ret:
            deployer.need_restart = True

    def configure(self, deployer):
        deployer.configure()

    def activate(self, deployer):
        deployer.activate()

    def perform_stages(self, deployers):
        default_stages = "install,configure,activate"
        stages = os.getenv("CMDEPLOY_STAGES", default_stages).split(",")

        for stage in stages:
            for deployer in deployers:
                getattr(self, stage)(deployer)


class Deployer:
    need_restart = False

    def install(self):
        pass

    def configure(self):
        pass

    def activate(self):
        pass
