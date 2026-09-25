"""New endpoints: /health and /metrics, and idempotent uploads."""

from conftest import disk_content


def test_health_needs_no_auth(client):
    response = client.get("/deploy/health")

    assert response.status_code == 200
    assert response.data == b"ok\n"


def test_metrics_requires_admin(client, user_headers):
    response = client.get("/deploy/metrics", headers=user_headers)

    assert response.status_code == 403


def test_metrics_requires_auth(client):
    assert client.get("/deploy/metrics").status_code == 401


def test_metrics_format(client, admin_headers, upload):
    upload()

    response = client.get("/deploy/metrics", headers=admin_headers)

    assert response.status_code == 200
    body = response.data.decode()

    assert "ipd_projects 1" in body
    assert "ipd_uploads_total 1" in body
    assert "ipd_queue_depth 0" in body  # started immediately, queue is empty
    assert "ipd_processed_bytes_total" in body
    assert "ipd_uptime_seconds" in body
    assert response.headers["Content-Type"].startswith("text/plain")


def test_idempotent_upload_returns_same_uuid(upload, upload_dir):
    first = upload(headers={"Idempotency-Key": "build-123"})
    second = upload(headers={"Idempotency-Key": "build-123"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data == first.data

    # The retry must not store anything on disk
    assert len(disk_content(upload_dir)) == 2  # folder + package of one upload


def test_idempotent_key_without_retry_creates_new(upload):
    first = upload(headers={"Idempotency-Key": "build-1"})
    other = upload(headers={"Idempotency-Key": "build-2"})

    assert other.status_code == 200
    assert other.data != first.data


def test_idempotent_upload_without_key(upload):
    first = upload()
    second = upload()

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data != first.data


def test_idempotent_rejects_too_long_key(upload, upload_dir):
    response = upload(headers={"Idempotency-Key": "x" * 129})

    assert response.status_code == 400
    assert disk_content(upload_dir) == []
