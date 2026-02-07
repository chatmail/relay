import socket
import threading
import time
from unittest.mock import patch

import pytest

from chatmaild.turnserver import turn_credentials

SOCKET_PATH = "/run/chatmail-turn/turn.socket"


@pytest.fixture
def turn_socket(tmp_path):
    """Create a real Unix socket server at a temp path."""
    sock_path = str(tmp_path / "turn.socket")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)
    yield sock_path, server
    server.close()


def _call_turn_credentials(sock_path):
    """Call turn_credentials but connect to sock_path instead of hardcoded path."""
    original_connect = socket.socket.connect

    def patched_connect(self, address):
        if address == SOCKET_PATH:
            address = sock_path
        return original_connect(self, address)

    with patch.object(socket.socket, "connect", patched_connect):
        return turn_credentials()


def test_turn_credentials_timeout(turn_socket):
    """Server accepts but never responds — must raise socket.timeout."""
    sock_path, server = turn_socket

    def accept_and_hang():
        conn, _ = server.accept()
        time.sleep(30)
        conn.close()

    t = threading.Thread(target=accept_and_hang, daemon=True)
    t.start()

    with pytest.raises(socket.timeout):
        _call_turn_credentials(sock_path)


def test_turn_credentials_connection_refused(tmp_path):
    """Socket file doesn't exist — must raise ConnectionRefusedError or FileNotFoundError."""
    missing = str(tmp_path / "nonexistent.socket")
    with pytest.raises((ConnectionRefusedError, FileNotFoundError)):
        _call_turn_credentials(missing)


def test_turn_credentials_success(turn_socket):
    """Server responds with credentials — must return stripped string."""
    sock_path, server = turn_socket

    def respond():
        conn, _ = server.accept()
        conn.sendall(b"testuser:testpass\n")
        conn.close()

    t = threading.Thread(target=respond, daemon=True)
    t.start()

    result = _call_turn_credentials(sock_path)
    assert result == "testuser:testpass"
