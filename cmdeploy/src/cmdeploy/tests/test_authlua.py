"""Test auth.lua script against mocked dovecot auth API."""

import jinja2
import pytest
from chatmaild.doveauth import encrypt_password, verify_password

from cmdeploy.basedeploy import get_resource

USER1 = "user12345@chat.example.org"
USER2 = "newuser12@chat.example.org"
OK, UNKNOWN, MISMATCH = 1, -2, -3

DOVECOT_MOCKS = """
create_status = 200

dovecot = {
  auth = {
    PASSDB_RESULT_OK = OK,
    PASSDB_RESULT_USER_UNKNOWN = UNKNOWN,
    PASSDB_RESULT_PASSWORD_MISMATCH = MISMATCH,
    USERDB_RESULT_OK = OK,
    USERDB_RESULT_USER_UNKNOWN = UNKNOWN,
  },
  http = {
    client = function(options)
      client_options = options
      return {request = function(_, options)
        create_request = options
        return {
          set_payload = function(_, payload) create_payload = payload end,
          submit = function()
            return {status = function() return create_status end}
          end,
        }
      end}
    end,
  },
}
"""


def load_authlua(lua, config):
    lua.g.OK, lua.g.UNKNOWN, lua.g.MISMATCH = OK, UNKNOWN, MISMATCH
    lua.rt.execute(DOVECOT_MOCKS)
    template = jinja2.Template(get_resource("dovecot/auth.lua.j2").read_text())
    lua.rt.execute(template.render(config=config))
    assert lua.g.script_init() == 0
    return lua


@pytest.fixture
def authlua(lua, example_config):
    return load_authlua(lua, example_config)


@pytest.fixture
def request_for(lua):
    def request_for(addr):
        def password_verify(_self, hashed, plain):
            return 1 if verify_password(hashed, plain) else 0

        return lua.table(user=addr, password_verify=password_verify)

    return request_for


@pytest.fixture
def create_user(example_config):
    def create_user(addr, password):
        example_config.get_user(addr).set_password(encrypt_password(password))

    return create_user


@pytest.fixture
def write_password_file(example_config):
    def write_password_file(addr, content):
        maildir = example_config.mailboxes_dir / addr
        maildir.mkdir(parents=True, exist_ok=True)
        maildir.joinpath("password").write_text(content)

    return write_password_file


def test_http_client_uses_dovecot_setting_names(authlua):
    """dovecot's lua http binding silently ignores keys it does not know."""
    assert dict(authlua.g.client_options) == {
        "request_timeout_msecs": 5000,
        "max_attempts": 1,
    }


def test_existing_address_correct_password(authlua, request_for, create_user):
    create_user(USER1, "correctgoose")
    res, fields = authlua.g.auth_password_verify(request_for(USER1), "correctgoose")
    assert res == OK
    assert fields["uid"] == fields["gid"] == "vmail"
    assert fields["home"].endswith(USER1)
    assert authlua.g.create_payload is None


def test_existing_address_wrong_password(authlua, request_for, create_user):
    create_user(USER1, "correctgoose")
    res, _ = authlua.g.auth_password_verify(request_for(USER1), "wronghorse")
    assert res == MISMATCH


def test_foreign_domain_is_refused_without_calling_out(
    authlua, request_for, create_user
):
    create_user("user12345@evil.example.org", "correctgoose")
    request = request_for("user12345@evil.example.org")
    res, _ = authlua.g.auth_password_verify(request, "correctgoose")
    assert res == UNKNOWN
    assert authlua.g.auth_userdb_lookup(request)[0] == UNKNOWN
    assert authlua.g.create_payload is None


def test_name_shorter_than_the_domain_is_refused(authlua, request_for):
    for name in ("x", "", "chat.example.org"):
        res, _ = authlua.g.auth_password_verify(request_for(name), "correctgoose")
        assert res == UNKNOWN
        assert authlua.g.auth_userdb_lookup(request_for(name))[0] == UNKNOWN
    assert authlua.g.create_payload is None


def test_slash_in_username_is_refused(authlua, request_for):
    request = request_for("../../etc/shadow@chat.example.org")
    res, _ = authlua.g.auth_password_verify(request, "somepassword")
    assert res == UNKNOWN
    assert authlua.g.auth_userdb_lookup(request)[0] == UNKNOWN
    assert authlua.g.create_payload is None


def test_localpart_policy_is_left_to_doveauth(authlua, request_for):
    authlua.g.create_status = 403
    res, _ = authlua.g.auth_password_verify(request_for("@chat.example.org"), "somepw")
    assert res == UNKNOWN
    assert authlua.g.create_payload == "@chat.example.org\tsomepw"


def test_unknown_address_is_created_via_endpoint(authlua, request_for):
    res, fields = authlua.g.auth_password_verify(request_for(USER2), "brandnewpass")
    assert res == OK
    assert fields["home"].endswith(USER2)
    assert authlua.g.create_payload == f"{USER2}\tbrandnewpass"
    assert authlua.g.create_request["url"] == "http://127.0.0.1:10084/create"


# a policy refusal and a doveauth that is down are both fail-closed
@pytest.mark.parametrize("status", [403, 0])
def test_creation_that_is_not_answered_with_200_is_user_unknown(
    authlua, request_for, status
):
    authlua.g.create_status = status
    res, _ = authlua.g.auth_password_verify(request_for(USER2), "brandnewpass")
    assert res == UNKNOWN


def test_userdb_unknown_before_creation_ok_after(authlua, request_for, create_user):
    request = request_for(USER1)
    res, _ = authlua.g.auth_userdb_lookup(request)
    assert res == UNKNOWN
    # a userdb lookup must never create anything
    assert authlua.g.create_payload is None

    create_user(USER1, "correctgoose")
    res, fields = authlua.g.auth_userdb_lookup(request)
    assert res == OK
    assert fields["home"].endswith(USER1)
    assert fields["uid"] == fields["gid"] == "vmail"


def test_empty_password_file_is_unknown(authlua, request_for, write_password_file):
    write_password_file(USER1, "")
    assert authlua.g.auth_userdb_lookup(request_for(USER1))[0] == UNKNOWN

    write_password_file(USER1, "\n")
    assert authlua.g.auth_userdb_lookup(request_for(USER1))[0] == UNKNOWN


def test_password_file_format_checks(authlua, request_for, write_password_file):
    write_password_file(USER1, encrypt_password("correctgoose") + "\n")
    res, _ = authlua.g.auth_password_verify(request_for(USER1), "correctgoose")
    assert res == OK
    assert authlua.g.auth_userdb_lookup(request_for(USER1))[0] == OK

    passhash = encrypt_password("correctgoose")
    write_password_file(USER1, passhash + "\ntrailing junk")
    authlua.g.create_status = 403
    res, _ = authlua.g.auth_password_verify(request_for(USER1), "correctgoose")
    assert res == UNKNOWN
    assert authlua.g.auth_userdb_lookup(request_for(USER1))[0] == UNKNOWN


def test_ipv4_relay_uses_bracketed_domain(lua, ipv4_config, request_for):
    # mail_domain is "[1.3.3.7]" here, and is_ours must not read it as a pattern
    authlua = load_authlua(lua, ipv4_config)
    addr = f"user12345@{ipv4_config.mail_domain}"
    ipv4_config.get_user(addr).set_password(encrypt_password("correctgoose"))

    res, fields = authlua.g.auth_password_verify(request_for(addr), "correctgoose")
    assert res == OK
    assert fields["home"].endswith(addr)
    assert authlua.g.auth_userdb_lookup(request_for(addr))[0] == OK
    assert authlua.g.auth_userdb_lookup(request_for(USER1))[0] == UNKNOWN
