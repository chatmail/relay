import socket
import threading

import pytest

from chatmaild.metadata import turn_credentials


@pytest.fixture
def turn_socket(tmp_path):
    sock_path = str(tmp_path / "turn.socket")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)
    yield sock_path, server
    server.close()


def test_turn_credentials_timeout(turn_socket):
    sock_path, server = turn_socket
    with pytest.raises(socket.timeout):
        # Inside turn_credentials the kernel listen backlog (1)
        # completes connect() without accept()
        # so the client blocks on readline() until the 5s timeout fires.
        turn_credentials(sock_path)


def test_turn_credentials_connection_refused_on_not_existing_socket(tmp_path):
    missing = str(tmp_path / "nonexistent.socket")
    with pytest.raises((ConnectionRefusedError, FileNotFoundError)):
        turn_credentials(missing)


def test_turn_credentials_socket_success(turn_socket):
    sock_path, server = turn_socket

    def respond():
        conn, _ = server.accept()
        conn.sendall(b"testuser:testpass\n")
        conn.close()

    t = threading.Thread(target=respond, daemon=True)
    t.start()

    result = turn_credentials(sock_path)
    assert result == "testuser:testpass"
