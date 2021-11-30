# -*- coding: utf-8 -*-

import re

ALLOWED_EXTENSIONS = {"tar", "tgz", "gz", "bz2"}

PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def valid_project(name: str) -> bool:
    """Check that project name is safe to use in filesystem path"""
    return bool(PROJECT_NAME_RE.fullmatch(name))


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
