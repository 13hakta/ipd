"""Graceful shutdown and per-step timeouts."""

import time

from ipd.deployment import Deployment
from ipd.manager import ProjectManager
from ipd.project import Project

from conftest import SLOW_CONTROL

from test_deployment import FakeManager, run_deployment


def make_project_deployment(tmp_path, control_sh=SLOW_CONTROL):
    """Create a deployment of a project and start it like the manager does"""
    project = Project()
    deployment = Deployment("backend", str(tmp_path / "upload"), "image.tar.gz")
    deployment.parent = project
    deployment.manager = FakeManager()

    import io
    import os
    import tarfile

    os.makedirs(deployment.upload_folder, exist_ok=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo("control.sh")
        data = control_sh.encode()
        info.size = len(data)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(data))

    with open(deployment.package_file, "wb") as f:
        f.write(buf.getvalue())

    with open(deployment.image_file, "wb") as f:
        f.write(b"image")

    # Register in the project the same way the manager does
    assert project.process(deployment) == 0
    return project, deployment


def test_stop_waits_for_running_deployment(tmp_path):
    manager = ProjectManager()
    project, deployment = make_project_deployment(tmp_path)
    manager.projects["backend"] = project

    start = time.time()
    manager.stop(timeout=10)

    # The slow deployment (sleep 1 in deploy) finished before stop returned
    assert not deployment.thread.is_alive()
    assert project.state() == 4
    assert time.time() - start >= 1


def test_stop_reports_timeout(tmp_path, caplog):
    manager = ProjectManager()
    project, deployment = make_project_deployment(tmp_path)
    manager.projects["backend"] = project

    with caplog.at_level("WARNING"):
        manager.stop(timeout=0.2)

    assert deployment.thread.is_alive()
    assert "still running" in caplog.text

    deployment.thread.join(10)


def test_check_step_timeout_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECK_TIMEOUT", "1")

    control_sh = '#!/bin/sh\n[ "$1" = check ] && sleep 5\nexit 2\n'

    import tarfile

    info = tarfile.TarInfo("control.sh")
    info.mode = 0o755

    state, _, upload_dir = run_deployment(tmp_path, [(info, control_sh.encode())])

    assert state == 1031
