import os
from pathlib import Path
import sys

import pytest


# Ensure backend package imports work regardless of where pytest is launched.
BACKEND_DIR = Path(__file__).resolve().parents[1]
backend_path = str(BACKEND_DIR)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


@pytest.fixture(autouse=True)
def _set_test_secret(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key-1234567890")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")


def get_csrf_token(client):
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    token = response.get_json()["data"]["csrf_token"]
    assert token
    return token


def csrf_headers(client, **extra_headers):
    headers = {"X-CSRF-Token": get_csrf_token(client)}
    headers.update(extra_headers)
    return headers
