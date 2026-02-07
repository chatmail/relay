"""Tests for turnserver functionality, particularly metadata integration."""

import socket
import tempfile
import threading
from pathlib import Path

from chatmaild.config import read_config, write_initial_config
from chatmaild.metadata import MetadataDictProxy, Metadata
from chatmaild.notifier import Notifier
from chatmaild.turnserver import turn_credentials


def test_turn_credentials_function_with_custom_socket():
    """Test that turn_credentials function works with a custom socket path from config."""
    # Create a temporary directory and socket file
    temp_dir = Path(tempfile.mkdtemp())
    temp_socket_path = temp_dir / "test_turn.socket"

    # Create a mock TURN credentials server
    def mock_server():
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(str(temp_socket_path))
        server_sock.listen(1)

        # Accept connection and send mock credentials
        conn, addr = server_sock.accept()
        with conn:
            conn.send(b"mock_turn_credentials_abc123\n")
        server_sock.close()

    # Start server in a background thread
    server_thread = threading.Thread(target=mock_server, daemon=True)
    server_thread.start()

    # Create a config with custom socket path
    config_path = temp_dir / "chatmail.ini"
    write_initial_config(config_path, "test.example.org", {
        "turn_socket_path": str(temp_socket_path)
    })
    config = read_config(config_path)

    # Allow time for server to start
    import time
    time.sleep(0.01)

    # Test that turn_credentials can connect using the config
    credentials = turn_credentials(config)
    assert credentials == "mock_turn_credentials_abc123"

    server_thread.join(timeout=1)  # Clean up thread


def test_metadata_turn_lookup_integration(tmp_path):
    """Test that metadata service properly handles TURN metadata lookups."""
    # Create mock config with custom turn socket path
    config_path = tmp_path / "chatmail.ini"
    socket_path = tmp_path / "test_turn.socket"
    write_initial_config(config_path, "example.org", {
        "turn_socket_path": str(socket_path)
    })
    config = read_config(config_path)

    # Create mock TURN server to return credentials
    def mock_turn_server():
        import os
        os.makedirs(socket_path.parent, exist_ok=True)  # Ensure parent directory exists

        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(str(socket_path))
        server_sock.listen(1)

        # Accept connection and send mock credentials
        conn, addr = server_sock.accept()
        with conn:
            conn.send(b"test_creds_12345\n")
        server_sock.close()

    server_thread = threading.Thread(target=mock_turn_server, daemon=True)
    server_thread.start()

    import time
    time.sleep(0.01)  # Allow server to start

    # Create a MetadataDictProxy with config
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    notifier = Notifier(queue_dir)
    metadata = Metadata(tmp_path / "vmail")

    dict_proxy = MetadataDictProxy(
        notifier=notifier,
        metadata=metadata,
        iroh_relay="https://example.org",
        turn_hostname="example.org",
        config=config
    )

    # Simulate a lookup for TURN credentials using the correct format
    # Input: "shared/0123/vendor/vendor.dovecot/pvt/server/vendor/deltachat/turn"
    # After parts[0].split("/", 2):
    # - keyparts[0] = "shared"
    # - keyparts[1] = "0123"
    # - keyparts[2] = "vendor/vendor.dovecot/pvt/server/vendor/deltachat/turn"
    # So keyname = keyparts[2] should match "vendor/vendor.dovecot/pvt/server/vendor/deltachat/turn"
    parts = [
        "shared/0123/vendor/vendor.dovecot/pvt/server/vendor/deltachat/turn",
        "dummy@user.org"
    ]

    # Call handle_lookup directly
    result = dict_proxy.handle_lookup(parts)

    # Verify the response format is correct for TURN credentials
    assert result.startswith("O")  # Output response starts with 'O'
    assert ":3478:" in result  # Contains port 3478
    assert "test_creds_12345" in result  # Contains credentials returned by mock server
    assert "example.org:3478:test_creds_12345" in result

    server_thread.join(timeout=1)  # Clean up thread