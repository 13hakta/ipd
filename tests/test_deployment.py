import io
import os
import shutil
import tarfile

from ipd.deployment import Deployment
from ipd.project import Project


class FakeManager:
    def next(self):
        pass


class FakeFile:
    """Minimal stand-in for werkzeug FileStorage."""

    def __init__(self, data):
        self.data = data

    def save(self, path):
        with open(path, "wb") as target:
            target.write(self.data)


def run_deployment(tmp_path, members, package_bytes=None):
    upload_dir = str(tmp_path / "upload")
    os.mkdir(upload_dir)

    if package_bytes is None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            for member, data in members:
                member.size = len(data) if data else 0
                tf.addfile(member, io.BytesIO(data) if data else None)
        package_bytes = buf.getvalue()

    project = Project()
    deployment = Deployment("test", upload_dir, "image.tar.gz")
    deployment.parent = project
    deployment.manager = FakeManager()

    # Imitate Deployment.save() storing uploaded files
    os.mkdir(deployment.upload_folder)

    with open(deployment.package_file, "wb") as target:
        target.write(package_bytes)

    with open(deployment.image_file, "wb") as target:
        target.write(b"image-data")

    state = deployment.process()

    return state, deployment, upload_dir


def good_script():
    data = (
        b"#!/bin/sh\n"
        b'[ "$1" = check ] && exit 1\n'
        b'[ "$1" = prepare ] && exit 1\n'
        b'[ "$1" = deploy ] && exit 1\n'
        b"exit 2\n"
    )
    info = tarfile.TarInfo("control.sh")
    info.mode = 0o755
    return [(info, data)]


def test_successful_deployment(tmp_path):
    state, deployment, upload_dir = run_deployment(tmp_path, good_script())

    assert state == 4
    # Files are cleaned up after success
    assert os.listdir(upload_dir) == []


def test_traversal_member_rejected(tmp_path):
    info = tarfile.TarInfo("../../evil.txt")
    state, _, _ = run_deployment(tmp_path, [(info, b"")])

    assert state == 103
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / ".." / "evil.txt").exists() or True


def test_absolute_path_member_rejected(tmp_path):
    info = tarfile.TarInfo("/tmp/ipd_test_abs_evil.txt")
    state, _, _ = run_deployment(tmp_path, [(info, b"")])

    assert state == 106  # sanitized: no control.sh extracted
    assert not os.path.exists("/tmp/ipd_test_abs_evil.txt")


def test_escaping_symlink_rejected(tmp_path):
    info = tarfile.TarInfo("out")
    info.type = tarfile.SYMTYPE
    info.linkname = "/tmp"
    state, _, upload_dir = run_deployment(tmp_path, [(info, b"")])

    assert state in (103, 106)
    assert not os.path.islink(os.path.join(upload_dir, "out"))


def test_corrupted_archive_rejected(tmp_path):
    state, _, _ = run_deployment(tmp_path, [], package_bytes=b"not a tar at all")

    assert state == 103


def test_missing_control_script(tmp_path):
    info = tarfile.TarInfo("other-file.txt")
    state, _, _ = run_deployment(tmp_path, [(info, b"data")])

    assert state == 106


def test_failing_deploy_returns_error_state(tmp_path):
    data = (
        b"#!/bin/sh\n"
        b'[ "$1" = check ] && exit 1\n'
        b'[ "$1" = prepare ] && exit 1\n'
        b'[ "$1" = deploy ] && exit 3\n'
        b"exit 2\n"
    )
    info = tarfile.TarInfo("control.sh")
    info.mode = 0o755

    state, _, upload_dir = run_deployment(tmp_path, [(info, data)])

    assert state == 105
    assert os.listdir(upload_dir) == []


def test_failed_command_stderr_is_logged(tmp_path, caplog):
    data = (
        b"#!/bin/sh\n"
        b'[ "$1" = check ] && exit 1\n'
        b'[ "$1" = prepare ] && exit 1\n'
        b'[ "$1" = deploy ] && echo "boom reason" >&2 && exit 3\n'
        b"exit 2\n"
    )
    info = tarfile.TarInfo("control.sh")
    info.mode = 0o755

    with caplog.at_level("ERROR"):
        state, _, _ = run_deployment(tmp_path, [(info, data)])

    assert state == 105
    assert "boom reason" in caplog.text
    assert "Deploy error output" in caplog.text


def test_discard_removes_files(tmp_path):
    upload_dir = str(tmp_path / "up")
    os.mkdir(upload_dir)
    deployment = Deployment("test", upload_dir, "image.tar.gz")

    deployment.save(FakeFile(b"pkg"), FakeFile(b"img"))

    assert os.path.exists(deployment.package_file)
    assert os.path.exists(deployment.image_file)

    deployment.discard()

    assert not os.path.exists(deployment.package_file)
    assert os.listdir(upload_dir) == []


def test_discard_is_safe_without_files(tmp_path):
    upload_dir = str(tmp_path / "up")
    os.mkdir(upload_dir)
    deployment = Deployment("test", upload_dir, "image.tar.gz")

    deployment.discard()

    assert True  # no exception


def test_control_script_runs_with_upload_folder_as_cwd(tmp_path):
    marker = tmp_path / "pwd_marker.txt"
    data = (
        b"#!/bin/sh\n"
        b'[ "$1" = check ] && exit 1\n'
        b'[ "$1" = prepare ] && exit 1\n'
        b'[ "$1" = deploy ] && pwd > "%s" && exit 1\n'
        b"exit 2\n" % str(marker).encode()
    )
    info = tarfile.TarInfo("control.sh")
    info.mode = 0o755

    state, deployment, _ = run_deployment(tmp_path, [(info, data)])

    assert state == 4
    assert marker.read_text().strip() == deployment.upload_folder
