"""Run the lua scripts we ship under lupa, which bundles Lua 5.4 like dovecot."""

import pytest
from chatmaild.tests.plugin import *  # noqa: F403
from lupa import lua54

from cmdeploy.basedeploy import get_resource
from cmdeploy.tests.plugin import *  # noqa: F403


class Lua:
    """A Lua runtime to load shipped scripts and mocks into."""

    def __init__(self):
        self.rt = lua54.LuaRuntime(unpack_returned_tuples=True)
        self.g = self.rt.globals()

    def load(self, path):
        self.rt.execute(get_resource(path).read_text())

    def table(self, **kwargs):
        return self.rt.table(**kwargs)


@pytest.fixture
def lua():
    return Lua()
