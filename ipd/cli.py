# -*- coding: utf-8 -*-

"""Command line helpers to manage the auth file."""

import argparse
import hashlib
import os
import secrets

from .auth import VALID_ROLES


def default_db() -> str:
    return os.environ.get("AUTH_DB", "users.txt")


def cmd_add(args) -> int:
    if args.role not in VALID_ROLES:
        print("Invalid role: %s, expected one of %s" % (args.role, sorted(VALID_ROLES)))
        return 2

    if os.path.exists(args.file):
        with open(args.file, "r") as db:
            for line in db:
                parts = line.strip().split(":")

                if len(parts) == 3 and parts[1] == args.name:
                    print("User already exists: %s" % args.name)
                    return 1

    token = args.token or secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()

    with open(args.file, "a") as db:
        db.write("%s:%s:%s\n" % (args.role, args.name, digest))

    print("User added: %s:%s" % (args.role, args.name))
    print("Token (shown once): %s" % token)
    return 0


def cmd_list(args) -> int:
    if not os.path.exists(args.file):
        print("No such file: %s" % args.file)
        return 1

    with open(args.file, "r") as db:
        for line in db:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split(":")

            if len(parts) == 3:
                print("%s:%s" % (parts[0], parts[1]))

    return 0


def cmd_del(args) -> int:
    if not os.path.exists(args.file):
        print("No such file: %s" % args.file)
        return 1

    with open(args.file, "r") as db:
        lines = db.readlines()

    kept = []
    removed = 0

    for line in lines:
        parts = line.strip().split(":")

        if len(parts) == 3 and parts[1] == args.name:
            removed += 1
        else:
            kept.append(line)

    if not removed:
        print("No such user: %s" % args.name)
        return 1

    with open(args.file, "w") as db:
        db.writelines(kept)

    print("User removed: %s (%d record)" % (args.name, removed))
    return 0


def cmd_passwd(args) -> int:
    if not os.path.exists(args.file):
        print("No such file: %s" % args.file)
        return 1

    with open(args.file, "r") as db:
        lines = db.readlines()

    token = args.token or secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    updated = 0
    result = []

    for line in lines:
        parts = line.strip().split(":")

        if len(parts) == 3 and parts[1] == args.name:
            result.append("%s:%s:%s\n" % (parts[0], args.name, digest))
            updated += 1
        else:
            result.append(line)

    if not updated:
        print("No such user: %s" % args.name)
        return 1

    with open(args.file, "w") as db:
        db.writelines(result)

    print("Token changed for: %s" % args.name)
    print("Token (shown once): %s" % token)
    return 0


def user_cli(argv) -> int:
    parser = argparse.ArgumentParser(prog="ipd user")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="add a user, print a new token")
    add.add_argument("role", help="user role: ADMIN or USER")
    add.add_argument("name", help="user name")
    add.add_argument("-f", "--file", default=default_db(), help="auth file")
    add.add_argument("--token", default=None, help="use given token instead of random")
    add.set_defaults(func=cmd_add)

    lst = sub.add_parser("list", help="list users")
    lst.add_argument("-f", "--file", default=default_db(), help="auth file")
    lst.set_defaults(func=cmd_list)

    delete = sub.add_parser("del", help="remove a user")
    delete.add_argument("name", help="user name")
    delete.add_argument("-f", "--file", default=default_db(), help="auth file")
    delete.set_defaults(func=cmd_del)

    passwd = sub.add_parser("passwd", help="issue a new token for a user")
    passwd.add_argument("name", help="user name")
    passwd.add_argument("-f", "--file", default=default_db(), help="auth file")
    passwd.add_argument(
        "--token", default=None, help="use given token instead of random"
    )
    passwd.set_defaults(func=cmd_passwd)

    args = parser.parse_args(argv)
    return args.func(args)
