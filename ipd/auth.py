# -*- coding: utf-8 -*-

import hmac
import logging
from functools import wraps
from hashlib import sha256
from typing import Optional
from flask import request, abort

USERS: dict = {}

VALID_ROLES = {"ADMIN", "USER"}


def load_db(source: str) -> int:
    """Load auth tokens from file"""
    USERS.clear()

    with open(source, "r") as user_file:
        for num, line in enumerate(user_file, 1):
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split(":")

            if len(parts) != 3:
                logging.warning("Skip malformed auth record %s:%d", source, num)
                continue

            role, user, key = parts

            if not user or role not in VALID_ROLES:
                logging.warning("Skip invalid auth record %s:%d", source, num)
                continue

            USERS[key] = (role, user)

    return len(USERS)


def require_role(role: Optional[str] = None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.headers.get("Authorization")

            if not data:
                abort(401)

            try:
                encoded = data.encode("ascii")
            except UnicodeEncodeError:
                abort(401)

            token_hash = sha256(encoded).hexdigest()

            for key, value in USERS.items():
                if hmac.compare_digest(token_hash, key):
                    user = value
                    break
            else:
                abort(401)

            if role and user[0] != role:
                abort(403)

            return func(user[1], *args, **kwargs)

        return wrapper

    return decorator
