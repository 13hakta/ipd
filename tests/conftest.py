import hashlib
import io
import os
import sys
import tarfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ipd.ipd import create_app  # noqa: E402

CONTROL_SH = """#!/bin/sh
[ "$1" = check ] && exit 1
[ "$1" = prepare ] && exit 1
[ "$1" = deploy ] && exit 1
exit 2
"""

SLOW_CONTROL = """#!/bin/sh
[ "$1" = check ] && exit 1
[ "$1" = prepare ] && exit 1
if [ "$1" = deploy ]; then
    sleep 1
    exit 1
fi
exit 2
"""


@pytest.fixture
def upload_dir(tmp_path):
    directory = tmp_path / "upload"
    directory.mkdir()
    return str(directory)


@pytest.fixture
def auth_db(tmp_path):
    path = tmp_path / "users.txt"
    path.write_text(
        "ADMIN:admin:%s\nUSER:user:%s\n"
        % (
            hashlib.sha256(b"adminkey").hexdigest(),
            hashlib.sha256(b"userkey").hexdigest(),
        )
    )
    return str(path)


@pytest.fixture
def make_app(upload_dir, auth_db):
    def _make(**kwargs):
        return create_app(upload_dir=upload_dir, auth_db=auth_db, **kwargs)

    return _make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_headers():
    return {"Authorization": "adminkey"}


@pytest.fixture
def user_headers():
    return {"Authorization": "userkey"}


@pytest.fixture
def make_package():
    def _make(control_sh=CONTROL_SH):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            info = tarfile.TarInfo("control.sh")
            data = control_sh.encode()
            info.size = len(data)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(data))
        return io.BytesIO(buf.getvalue()), "package.tar"

    return _make


@pytest.fixture
def make_image():
    def _make(data=b"image-data", filename="image.tar.gz"):
        return io.BytesIO(data), filename

    return _make


@pytest.fixture
def slow_package(make_package):
    def _make():
        return make_package(control_sh=SLOW_CONTROL)

    return _make


@pytest.fixture
def upload(client, admin_headers, make_package, make_image):
    def _upload(
        project="backend",
        package=None,
        image=None,
        version=None,
        omit_package=False,
        omit_image=False,
    ):
        data = {"project": project}
        if not omit_package:
            data["package"] = package if package is not None else make_package()
        if not omit_image:
            data["image"] = image if image is not None else make_image()
        if version is not None:
            data["version"] = version
        return client.post("/deploy/upload", data=data, headers=admin_headers)

    return _upload


def disk_content(upload_dir):
    return sorted(os.listdir(upload_dir))
