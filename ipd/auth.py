# -*- coding: utf-8 -*-

from functools import wraps
from flask import request, abort
from hashlib import sha256

USERS = {}


def load_db(source: str) -> None:
    user_file = open(source, "r")

    for line in user_file:
        role, user, key = line.rstrip("\n").split(":")

        if user:
            USERS[key] = (role, user)

    user_file.close()


def require_role(role: str = None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "Authorization" not in request.headers:
                abort(401)

            data = request.headers["Authorization"].encode("ascii", "ignore")

            try:
                user = USERS[sha256(data).hexdigest()]
            except KeyError:
                abort(401)

            if role and user[0] != role:
                abort(401)

            return func(user[1], *args, **kwargs)

        return wrapper

    return decorator
