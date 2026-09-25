import io
import os
import tarfile

import pytest

from ipd.utils import valid_project

from conftest import disk_content

BAD_PROJECT_NAMES = [
    "",
    "..",
    "../../tmp/evil",
    "a/b",
    "a\\b",
    "a b",
    ".hidden",
    "-x",
    "x" * 65,
]


@pytest.mark.parametrize("name", ["backend", "front-end", "my.app_2", "x" * 64])
def test_valid_project_accepts(name):
    assert valid_project(name)


@pytest.mark.parametrize("name", BAD_PROJECT_NAMES)
def test_valid_project_rejects(name):
    assert not valid_project(name)


@pytest.mark.parametrize("name", BAD_PROJECT_NAMES)
def test_upload_rejects_bad_project_name(upload, upload_dir, name):
    response = upload(project=name)

    assert response.status_code == 400
    assert response.data == b"err"
    # Nothing is written to disk
    assert disk_content(upload_dir) == []


def test_upload_rejects_missing_package(client, admin_headers, make_image):
    response = client.post(
        "/deploy/upload",
        data={"project": "backend", "image": make_image()},
        headers=admin_headers,
    )

    assert response.status_code == 400


def test_upload_rejects_missing_image(upload, upload_dir):
    response = upload(omit_image=True)

    assert response.status_code == 400
    assert disk_content(upload_dir) == []


def test_upload_rejects_empty_image_name(upload, upload_dir, make_package):
    response = upload(image=(io.BytesIO(b"data"), ""))

    assert response.status_code == 400
    assert disk_content(upload_dir) == []


def test_upload_rejects_bad_extension(upload, upload_dir, make_image):
    response = upload(image=make_image(filename="virus.exe"))

    assert response.status_code == 400
    assert disk_content(upload_dir) == []


def test_upload_rejects_oversized(make_app, upload_dir, make_package, make_image):
    app = make_app(max_upload_size=1000)
    client = app.test_client()

    response = client.post(
        "/deploy/upload",
        data={
            "project": "backend",
            "package": make_package(),
            "image": make_image(data=b"z" * 10000),
        },
        headers={"Authorization": "adminkey"},
    )

    assert response.status_code == 413
    assert disk_content(upload_dir) == []


def test_upload_stores_files_and_returns_uuid(upload, upload_dir):
    response = upload()

    assert response.status_code == 200
    uuid = response.data.decode()

    assert f"backend-{uuid}" in disk_content(upload_dir)
    assert f"package.tar.{uuid}" in disk_content(upload_dir)


def test_upload_registers_project_for_info(upload, client, admin_headers):
    upload(project="backend", version="1.2.3")

    info = client.get("/deploy/info/backend", headers=admin_headers)

    assert info.status_code == 200
    assert info.data != b"no"
    assert b"1.2.3" in info.data
