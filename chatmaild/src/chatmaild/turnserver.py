#!/usr/bin/env python3
import base64
import hashlib
import hmac
import time


def coturn_credentials() -> str:
    secret = "north"

    ttl = 5 * 24 * 3600  # Time to live
    timestamp = int(time.time()) + ttl
    username = str(timestamp)
    dig = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    password = base64.b64encode(dig).decode()

    return f"{username}:{password}"
