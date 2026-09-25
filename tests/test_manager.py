import time

import ipd.manager as manager_module

from conftest import disk_content


def wait_status(client, headers, project, uuid, expected, timeout=15):
    deadline = time.time() + timeout
    state = None

    while time.time() < deadline:
        state = status(client, headers, project, uuid)
        if state == expected:
            return state
        time.sleep(0.1)

    return state


def status(client, headers, project, uuid):
    response = client.get("/deploy/status/%s/%s" % (project, uuid), headers=headers)
    return response.data.decode().strip()


def test_status_of_unknown_project(client, admin_headers):
    response = client.get("/deploy/status/nowhere", headers=admin_headers)

    assert response.data == b"no"


def test_second_upload_waits_for_busy_project_and_completes(
    upload, client, admin_headers, slow_package, upload_dir
):
    u1 = upload(project="alpha", package=slow_package()).data.decode()
    time.sleep(0.3)
    u2 = upload(project="alpha", package=slow_package()).data.decode()

    assert u1 != u2
    assert status(client, admin_headers, "alpha", u2) in ("await", "active")

    assert wait_status(client, admin_headers, "alpha", u1, "ok") == "ok"
    assert wait_status(client, admin_headers, "alpha", u2, "ok") == "ok"
    # No leaked files
    assert disk_content(upload_dir) == []


def test_superseded_awaiting_deployment_reports_changed_and_discards(
    upload, client, admin_headers, slow_package, upload_dir
):
    u3 = upload(project="beta", package=slow_package()).data.decode()
    time.sleep(0.3)
    u4 = upload(project="beta", package=slow_package()).data.decode()
    u5 = upload(project="beta").data.decode()

    assert status(client, admin_headers, "beta", u4) == "changed"
    assert not any(u4 in name for name in disk_content(upload_dir))

    assert wait_status(client, admin_headers, "beta", u5, "ok") == "ok"
    assert disk_content(upload_dir) == []


def test_queue_served_lifo(monkeypatch, upload, client, admin_headers, slow_package):
    monkeypatch.setattr(manager_module, "TASKS_MAX", 1)

    upload(project="alpha", package=slow_package())
    time.sleep(0.3)

    beta = upload(project="beta", package=slow_package()).data.decode()
    gamma = upload(project="gamma").data.decode()

    # Gamma was uploaded last and must be processed before beta (LIFO)
    assert wait_status(client, admin_headers, "gamma", gamma, "ok") == "ok"
    assert status(client, admin_headers, "beta", beta) in ("await", "active")

    assert wait_status(client, admin_headers, "beta", beta, "ok") == "ok"


def test_all_deployments_complete_with_limited_capacity(
    monkeypatch, upload, client, admin_headers, slow_package, upload_dir
):
    monkeypatch.setattr(manager_module, "TASKS_MAX", 1)

    uuids = [
        upload(project="p%d" % i, package=slow_package()).data.decode()
        for i in range(3)
    ]

    for i, uuid in enumerate(uuids):
        assert wait_status(client, admin_headers, "p%d" % i, uuid, "ok") == "ok"

    assert disk_content(upload_dir) == []


def test_upload_rejected_when_queue_is_full(
    monkeypatch, upload, client, admin_headers, slow_package
):
    monkeypatch.setattr(manager_module, "TASKS_MAX", 1)
    monkeypatch.setattr(manager_module, "QUEUE_MAX", 1)

    upload(project="alpha", package=slow_package())
    time.sleep(0.3)
    upload(project="beta", package=slow_package())

    # Queue already holds one awaiting deployment
    response = upload(project="gamma")

    assert response.status_code == 400
    assert response.data == b"err"
