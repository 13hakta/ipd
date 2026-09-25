"""Startup recovery: cleanup of deployments interrupted by a restart."""

import os
import uuid

from conftest import disk_content


def make_orphans(upload_dir):
    """Create leftover files in the same naming scheme as the service"""
    deploy_uuid = str(uuid.uuid4())

    folder = os.path.join(upload_dir, f"backend-{deploy_uuid}")
    os.mkdir(folder)

    with open(os.path.join(folder, "image.tar.gz"), "w") as f:
        f.write("image")

    with open(os.path.join(upload_dir, f"package.tar.{deploy_uuid}"), "w") as f:
        f.write("package")

    return deploy_uuid


def test_recover_removes_leftovers(make_app, upload_dir):
    make_orphans(upload_dir)

    make_app()  # create_app calls recover()

    assert disk_content(upload_dir) == []


def test_recover_keeps_foreign_files(make_app, upload_dir):
    os.mkdir(os.path.join(upload_dir, "backend"))
    os.mkdir(os.path.join(upload_dir, "keep-me"))

    with open(os.path.join(upload_dir, "backend", "data.txt"), "w") as f:
        f.write("data")

    with open(os.path.join(upload_dir, "notes.txt"), "w") as f:
        f.write("notes")

    # Folder without a uuid suffix and a package file with a bad uuid
    with open(os.path.join(upload_dir, "package.tar.notauuid"), "w") as f:
        f.write("package")

    make_app()

    assert disk_content(upload_dir) == [
        "backend",
        "keep-me",
        "notes.txt",
        "package.tar.notauuid",
    ]


def test_recover_leaves_clean_dir_alone(make_app, upload_dir):
    make_app()

    assert disk_content(upload_dir) == []
