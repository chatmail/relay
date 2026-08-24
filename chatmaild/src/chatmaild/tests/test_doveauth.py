import http.client
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import chatmaild.doveauth
from chatmaild.doveauth import (
    CreateHandler,
    DoveAuth,
    DoveAuthServer,
    is_allowed_to_create,
)
from chatmaild.newemail import create_newemail_dict


@pytest.fixture
def doveauth(example_config):
    return DoveAuth(example_config)


def stored_hash(config, addr):
    return config.get_user(addr).get_password_hash()


def test_basic(doveauth, example_config, example_gencreds):
    addr, password = example_gencreds()
    assert doveauth.create_user(addr, password)
    passhash = stored_hash(example_config, addr)
    assert passhash.startswith("{SHA512-CRYPT}")

    # a second login verifies against the stored hash and rewrites nothing
    assert doveauth.create_user(addr, password)
    assert stored_hash(example_config, addr) == passhash


def test_invalid_username_length(example_config):
    config = example_config
    config.username_min_length = 6
    config.username_max_length = 10
    password = create_newemail_dict(config)["password"]
    assert not is_allowed_to_create(config, f"a1234@{config.mail_domain}", password)
    assert is_allowed_to_create(config, f"012345@{config.mail_domain}", password)
    assert is_allowed_to_create(config, f"0123456@{config.mail_domain}", password)
    assert is_allowed_to_create(config, f"0123456789@{config.mail_domain}", password)
    assert not is_allowed_to_create(
        config, f"0123456789x@{config.mail_domain}", password
    )


def test_dont_overwrite_password_on_wrong_login(doveauth, example_config):
    addr = "newuser12@chat.example.org"
    assert doveauth.create_user(addr, "kajdlkajsldk12l3kj1983")
    passhash = stored_hash(example_config, addr)

    assert not doveauth.create_user(addr, "kajdslqwe")
    assert stored_hash(example_config, addr) == passhash

    assert doveauth.create_user(addr, "kajdlkajsldk12l3kj1983")
    assert stored_hash(example_config, addr) == passhash


def test_foreign_domain_is_refused(doveauth):
    assert not doveauth.create_user("newuser12@evil.example.org", "qlwkejqlwe12")


def test_nocreate_file(monkeypatch, tmpdir, doveauth, example_config):
    p = tmpdir.join("nocreate")
    p.write("")
    monkeypatch.setattr(chatmaild.doveauth, "NOCREATE_FILE", str(p))
    addr = "newuser12@chat.example.org"
    assert not doveauth.create_user(addr, "zequ0Aimuchoodaechik")
    assert stored_hash(example_config, addr) is None


def test_invalid_localpart_characters(make_config):
    config = make_config("chat.example.org", {"username_min_length": "3"})
    password = "zequ0Aimuchoodaechik"
    domain = config.mail_domain

    # valid localparts
    assert is_allowed_to_create(config, f"abc123@{domain}", password)
    assert is_allowed_to_create(config, f"a.b-c_d@{domain}", password)

    # uppercase rejected
    assert not is_allowed_to_create(config, f"Abc123@{domain}", password)
    assert not is_allowed_to_create(config, f"ABCDEFG@{domain}", password)

    # spaces and special chars rejected
    assert not is_allowed_to_create(config, f"a b cde@{domain}", password)
    assert not is_allowed_to_create(config, f"abc+def@{domain}", password)
    assert not is_allowed_to_create(config, f"abc!def@{domain}", password)
    assert not is_allowed_to_create(config, f"ab@cdef@{domain}", password)
    assert not is_allowed_to_create(config, f"abc/def@{domain}", password)
    assert not is_allowed_to_create(config, f"abc\\def@{domain}", password)
    assert not is_allowed_to_create(config, f"üser123@{domain}", password)


def test_concurrent_creation_same_account(doveauth, example_config, capsys):
    addr = "racetest1@chat.example.org"
    password = "zequ0Aimuchoodaechik"

    def create(_):
        ok = doveauth.create_user(addr, password)
        return ok, stored_hash(example_config, addr)

    with ThreadPoolExecutor(10) as pool:
        results = list(pool.map(create, range(10)))
    assert all(ok for ok, _ in results)
    # all threads must see the same password hash
    assert len({passhash for _, passhash in results}) == 1
    assert capsys.readouterr().err.count("Created address:") == 1


def test_insufficient_resources_block_creation_not_existing_logins(
    doveauth, example_gencreds, monkeypatch
):
    addr, password = example_gencreds()
    assert doveauth.create_user(addr, password)

    monkeypatch.setattr(
        chatmaild.doveauth, "has_sufficient_resources", lambda config: False
    )
    newaddr, newpassword = example_gencreds()
    assert not doveauth.create_user(newaddr, newpassword)
    assert doveauth.create_user(addr, password)


class TestHttpPost:
    @pytest.fixture
    def doveauth_server(self, example_config):
        server = DoveAuthServer(example_config, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"127.0.0.1:{server.server_address[1]}"
        server.shutdown()
        server.server_close()

    @pytest.fixture
    def post(self, doveauth_server):
        def post(path, data):
            conn = http.client.HTTPConnection(doveauth_server, timeout=10)
            try:
                return self.post_on(conn, path, data).status
            finally:
                conn.close()

        return post

    @pytest.fixture
    def connection(self, doveauth_server):
        """One kept-alive connection, which is all dovecot's HTTP client opens."""
        conn = http.client.HTTPConnection(doveauth_server, timeout=10)
        yield conn
        conn.close()

    @staticmethod
    def post_on(conn, path, data):
        conn.request("POST", path, body=data)
        resp = conn.getresponse()
        resp.read()
        return resp

    def test_create_and_verify(self, post, example_config, example_gencreds):
        addr, password = example_gencreds()
        assert post("/create", f"{addr}\t{password}".encode()) == 200
        assert stored_hash(example_config, addr).startswith("{SHA512-CRYPT}")

        # second login with the same password verifies, a wrong one is refused
        assert post("/create", f"{addr}\t{password}".encode()) == 200
        assert post("/create", f"{addr}\twrong{password}".encode()) == 403

    def test_password_special_chars_survive_transport(self, post, example_gencreds):
        addr, _ = example_gencreds()
        password = "laksjdlaksjdlak\\sjdlk\"12j'3l1/k2\tj3123"
        body = f"{addr}\t{password}".encode()
        assert post("/create", body) == 200
        assert post("/create", body) == 200
        assert post("/create", f"{addr}\totherpassword1".encode()) == 403

    def test_password_must_be_utf8(self, post, example_gencreds):
        addr, _ = example_gencreds()
        assert post("/create", f"{addr}\tpässwort12".encode()) == 200
        assert post("/create", addr.encode() + b"\tp\xe4sswort12") == 400

    def test_nul_is_refused_before_crypt_sees_it(self, post, example_gencreds):
        addr, _ = example_gencreds()
        assert post("/create", f"{addr}\tpass\0word12".encode()) == 400
        assert (
            post("/create", "us\0er12345@chat.example.org\tlongenough1".encode()) == 400
        )

    def test_refused_creation(self, post, example_gencreds):
        addr, _ = example_gencreds()
        assert post("/create", f"{addr}\tshort".encode()) == 403
        assert post("/create", b"not-an-address\tlongenoughpassword") == 403
        body = "bürger123@chat.example.org\tlongenoughpw".encode()
        assert post("/create", body) == 403
        assert post("/create", b"") == 403

    def test_body_length_limit(self, post, example_gencreds):
        addr, _ = example_gencreds()
        fill = CreateHandler.max_body_len - len(addr) - len("\t")
        body = f"{addr}\t{'x' * fill}".encode()
        assert len(body) == CreateHandler.max_body_len
        assert post("/create", body) == 200

        body = f"{addr}\t{'x' * (fill + 1)}".encode()
        assert len(body) == CreateHandler.max_body_len + 1
        assert post("/create", body) == 400

    def test_connection_is_reused_across_200_replies(
        self, connection, example_gencreds
    ):
        addr, password = example_gencreds()
        body = f"{addr}\t{password}".encode()
        # create, then verify the same password, on one connection
        for _ in range(2):
            resp = self.post_on(connection, "/create", body)
            assert (resp.status, resp.will_close) == (200, False)

    @pytest.mark.parametrize(
        "path,data,status",
        [
            ("/other", b"not read", 404),
            ("/create", b"x" * (CreateHandler.max_body_len + 1), 400),
            ("/create", b"not-an-address\tlongenoughpassword", 403),
        ],
    )
    def test_error_replies_close_the_connection(self, connection, path, data, status):
        resp = self.post_on(connection, path, data)
        assert (resp.status, resp.will_close) == (status, True)

    @pytest.mark.parametrize("content_length", [None, "-1", "notanumber", "999999"])
    def test_bad_content_length(self, connection, content_length):
        # the fixture timeout turns a server that waits for the body into a failure
        connection.putrequest("POST", "/create", skip_accept_encoding=True)
        if content_length is not None:
            connection.putheader("Content-Length", content_length)
        connection.endheaders()
        resp = connection.getresponse()
        assert resp.status == 400
        assert resp.will_close
