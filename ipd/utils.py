# -*- coding: utf-8 -*-

import random


ALLOWED_EXTENSIONS = {"tar", "tgz", "gz", "bz2"}


def gen_code() -> str:
    code = random.randrange(0, 999999, 1)
    return str(code).zfill(6)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
