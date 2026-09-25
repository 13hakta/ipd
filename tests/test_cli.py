"""Tests for the ipd user CLI."""

from ipd.cli import user_cli


def test_user_add_generates_token(tmp_path):
    db = tmp_path / "users.txt"

    code = user_cli(["add", "USER", "alice", "-f", str(db)])

    assert code == 0
    content = db.read_text()
    assert "USER:alice:" in content
    # Token is random, only the hash is stored
    assert "token" not in content


def test_user_add_with_fixed_token(tmp_path):
    import hashlib

    db = tmp_path / "users.txt"
    token = "my-secret-token"

    code = user_cli(["add", "ADMIN", "bob", "-f", str(db), "--token", token])

    assert code == 0
    digest = hashlib.sha256(token.encode()).hexdigest()
    assert f"ADMIN:bob:{digest}" in db.read_text()


def test_user_add_rejects_bad_role(tmp_path):
    db = tmp_path / "users.txt"

    code = user_cli(["add", "SUPERUSER", "x", "-f", str(db)])

    assert code == 2
    assert not db.exists()


def test_user_add_rejects_duplicate_name(tmp_path):
    db = tmp_path / "users.txt"

    assert user_cli(["add", "USER", "alice", "-f", str(db)]) == 0
    assert user_cli(["add", "ADMIN", "alice", "-f", str(db)]) == 1

    # Only the first record is stored
    lines = [line for line in db.read_text().splitlines() if line]
    assert len(lines) == 1


def test_user_list(tmp_path, capsys):
    db = tmp_path / "users.txt"
    db.write_text(
        "ADMIN:admin:%s\n"
        "# comment\n"
        "USER:user:%s\n"
        "broken-line\n" % ("a" * 64, "b" * 64)
    )

    code = user_cli(["list", "-f", str(db)])
    out = capsys.readouterr().out

    assert code == 0
    assert "ADMIN:admin" in out
    assert "USER:user" in out
    assert "broken" not in out
    assert "comment" not in out


def test_user_list_missing_file(tmp_path, capsys):
    code = user_cli(["list", "-f", str(tmp_path / "absent.txt")])

    assert code == 1
