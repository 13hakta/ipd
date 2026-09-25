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


def test_user_del_removes_only_target_user(tmp_path, capsys):
    db = tmp_path / "users.txt"
    db.write_text(
        "ADMIN:admin:%s\nUSER:alice:%s\nUSER:bob:%s\n" % ("a" * 64, "b" * 64, "c" * 64)
    )

    code = user_cli(["del", "alice", "-f", str(db)])
    out = capsys.readouterr().out

    assert code == 0
    assert "User removed: alice" in out
    content = db.read_text()
    assert "alice" not in content
    assert "ADMIN:admin" in content
    assert "USER:bob" in content


def test_user_del_missing_user(tmp_path, capsys):
    db = tmp_path / "users.txt"
    db.write_text("ADMIN:admin:%s\n" % ("a" * 64))

    code = user_cli(["del", "ghost", "-f", str(db)])
    out = capsys.readouterr().out

    assert code == 1
    assert "No such user: ghost" in out
    # File is untouched
    assert db.read_text() == "ADMIN:admin:%s\n" % ("a" * 64)


def test_user_passwd_replaces_token_keeps_role(tmp_path, capsys):
    import hashlib

    db = tmp_path / "users.txt"
    db.write_text("USER:alice:%s\nADMIN:admin:%s\n" % ("b" * 64, "c" * 64))

    code = user_cli(["passwd", "alice", "-f", str(db), "--token", "new-secret"])
    out = capsys.readouterr().out

    assert code == 0
    assert "Token changed for: alice" in out
    digest = hashlib.sha256(b"new-secret").hexdigest()
    assert f"USER:alice:{digest}" in db.read_text()
    assert ("b" * 64) not in db.read_text()
    # Other users are untouched
    assert f"ADMIN:admin:{'c' * 64}" in db.read_text()


def test_user_passwd_random_token(tmp_path, capsys):
    db = tmp_path / "users.txt"
    db.write_text("USER:alice:%s\n" % ("b" * 64))

    code = user_cli(["passwd", "alice", "-f", str(db)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Token (shown once):" in out
    # New random token hash differs from the old one
    assert ("b" * 64) not in db.read_text()


def test_user_passwd_missing_user(tmp_path, capsys):
    db = tmp_path / "users.txt"
    db.write_text("ADMIN:admin:%s\n" % ("a" * 64))

    code = user_cli(["passwd", "ghost", "-f", str(db)])

    assert code == 1
    assert "ghost" not in db.read_text()
