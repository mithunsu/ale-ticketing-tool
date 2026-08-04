from pathlib import Path
import os

import app as app_module


def _write_env_file(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_create_app_loads_values_from_configured_env_file(monkeypatch, tmp_path):
    temp_env_path = tmp_path / ".env"
    _write_env_file(
        temp_env_path,
        [
            "DB_NAME=test_db",
            "DB_USER=test_user",
            "DB_HOST=test_host",
            "DB_PASSWORD=test_password",
        ],
    )

    monkeypatch.setattr(app_module, "LOCAL_ENV_FILE", temp_env_path)
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    app = app_module.create_app()

    assert app is not None
    assert os.getenv("DB_NAME") == "test_db"
    assert os.getenv("DB_USER") == "test_user"
    assert os.getenv("DB_HOST") == "test_host"
    assert os.getenv("DB_PASSWORD") == "test_password"


def test_create_app_does_not_override_existing_environment(monkeypatch, tmp_path):
    temp_env_path = tmp_path / ".env"
    _write_env_file(
        temp_env_path,
        [
            "DB_HOST=file_host",
            "DB_NAME=file_db",
        ],
    )

    monkeypatch.setattr(app_module, "LOCAL_ENV_FILE", temp_env_path)
    monkeypatch.setenv("DB_HOST", "existing_host")
    monkeypatch.delenv("DB_NAME", raising=False)

    app = app_module.create_app()

    assert app is not None
    assert os.getenv("DB_HOST") == "existing_host"
    assert os.getenv("DB_NAME") == "file_db"
