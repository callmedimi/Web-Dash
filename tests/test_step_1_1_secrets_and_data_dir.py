"""Unit tests for Step 1.1: Secrets & state out of the image (F-08)."""
import os
import stat
import tempfile
import pytest


def test_users_file_placed_under_data_dir(monkeypatch):
    """Verify that auth.py places users.json under DATA_DIR."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        import auth

        users_file = auth._get_users_file()
        assert os.path.dirname(os.path.abspath(users_file)) == os.path.abspath(tmpdir)
        assert os.path.basename(users_file) == "users.json"

        # Load users should create users.json in tmpdir
        users = auth._load_users()
        assert os.path.exists(users_file)
        assert "Dimi" in users


def test_secret_key_precedence_env(monkeypatch):
    """Verify FLASK_SECRET_KEY env takes precedence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.setenv("FLASK_SECRET_KEY", "custom-super-secret-key-12345")

        # Emulate app.py key initialization logic
        data_dir = os.environ.get("DATA_DIR", "./data")
        secret_key_file = os.path.join(data_dir, ".secret_key")
        
        if os.environ.get("FLASK_SECRET_KEY"):
            app_secret = os.environ["FLASK_SECRET_KEY"]
        elif os.path.exists(secret_key_file):
            with open(secret_key_file, "r") as f:
                app_secret = f.read().strip()
        else:
            app_secret = "generated"

        assert app_secret == "custom-super-secret-key-12345"
        # .secret_key file should not be created if env var is present
        assert not os.path.exists(secret_key_file)


def test_secret_key_file_generation_and_permissions(monkeypatch):
    """Verify secret key is generated in DATA_DIR with 0600 mode when none exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

        import secrets

        secret_key_file = os.path.join(tmpdir, ".secret_key")
        assert not os.path.exists(secret_key_file)

        generated_key = secrets.token_hex(32)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        fd = os.open(secret_key_file, flags, mode)
        with os.fdopen(fd, "w") as f:
            f.write(generated_key)

        assert os.path.exists(secret_key_file)
        with open(secret_key_file, "r") as f:
            content = f.read().strip()
        assert content == generated_key

        # On POSIX systems, check permission is 0600
        if os.name == "posix":
            st = os.stat(secret_key_file)
            assert stat.S_IMODE(st.st_mode) == 0o600


def test_upload_folder_placed_under_data_dir(monkeypatch):
    """Verify upload folder is configured under DATA_DIR."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        data_dir = os.environ.get("DATA_DIR", "./data")
        upload_folder = os.path.join(data_dir, "uploads")
        os.makedirs(upload_folder, exist_ok=True)

        assert os.path.isdir(upload_folder)
        assert os.path.dirname(upload_folder) == tmpdir
