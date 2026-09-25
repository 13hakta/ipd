import hashlib

from ipd.auth import load_db, USERS


def write(tmp_path, content):
    path = tmp_path / "users.txt"
    path.write_text(content)
    return str(path)


def test_load_db_skips_malformed_lines(tmp_path):
    source = write(
        tmp_path,
        "\n".join(
            [
                "broken-line-without-colons",
                "TOO:MANY:COLONS:here",
                "SUPERROLE:x:%s" % hashlib.sha256(b"a").hexdigest(),
                "USER::%s" % hashlib.sha256(b"b").hexdigest(),
            ]
        ),
    )

    assert load_db(source) == 0
    assert USERS == {}


def test_load_db_ignores_comments_and_empty_lines(tmp_path):
    good = hashlib.sha256(b"adminkey").hexdigest()
    source = write(tmp_path, "# comment\n\nADMIN:admin:%s\n" % good)

    assert load_db(source) == 1
    assert USERS[good] == ("ADMIN", "admin")


def test_load_db_valid_records(tmp_path):
    admin = hashlib.sha256(b"adminkey").hexdigest()
    user = hashlib.sha256(b"userkey").hexdigest()
    source = write(tmp_path, "ADMIN:admin:%s\nUSER:user:%s\n" % (admin, user))

    assert load_db(source) == 2
    assert USERS[admin] == ("ADMIN", "admin")
    assert USERS[user] == ("USER", "user")


def test_no_authorization_unauthorized(client):
    response = client.get("/deploy/list")

    assert response.status_code == 401


def test_bad_token_unauthorized(client):
    response = client.get("/deploy/list", headers={"Authorization": "wrong"})

    assert response.status_code == 401


def test_non_ascii_token_unauthorized(client):
    response = client.get("/deploy/list", headers={"Authorization": "ключ"})

    assert response.status_code == 401


def test_insufficient_role_forbidden(client, user_headers):
    response = client.get("/deploy/stat", headers=user_headers)

    assert response.status_code == 403


def test_admin_role_allowed(client, admin_headers):
    response = client.get("/deploy/stat", headers=admin_headers)

    assert response.status_code == 200
