# -*- coding: utf-8 -*-

import re
import shutil

ALLOWED_EXTENSIONS = {"tar", "tgz", "gz", "bz2"}

PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Keep some headroom so the upload never fills the disk to zero
DISK_MARGIN = 100 * 1024 * 1024


def enough_disk(path: str, size: int) -> bool:
    """Check that path has room for size bytes plus a safety margin"""
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        # Cant stat the path (missing directory etc.), let the
        # write attempt fail with its own error instead
        return True

    return usage.free > size + DISK_MARGIN


def valid_project(name: str) -> bool:
    """Check that project name is safe to use in filesystem path"""
    return bool(PROJECT_NAME_RE.fullmatch(name))


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
