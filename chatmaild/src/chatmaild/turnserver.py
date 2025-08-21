#!/usr/bin/env python3
import socket


def turn_credentials() -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client_socket:
        client_socket.connect("/run/chatmail-turn/turn.socket")
        with client_socket.makefile("rb") as file:
            return file.readline().decode("utf-8")
