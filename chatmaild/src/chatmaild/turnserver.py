#!/usr/bin/env python3
import socket


def turn_credentials(turn_socket_path) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client_socket:
        client_socket.settimeout(5)
        client_socket.connect(turn_socket_path)
        with client_socket.makefile("rb") as file:
            return file.readline().decode("utf-8").strip()
