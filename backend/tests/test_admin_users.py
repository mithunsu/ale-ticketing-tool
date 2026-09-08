from datetime import datetime, timezone

import psycopg
import pytest
from werkzeug.security import check_password_hash

from app import create_app


class _StubCursor:
    def __init__(self, insert_result=None, insert_error=None):
        self.insert_result = insert_result
        self.insert_error = insert_error
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if self.insert_error is not None:
            raise self.insert_error

    def fetchone(self):
        return self.insert_result


class _StubConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


def _app_with_current_user(monkeypatch, role="admin", cursor=None):
    app = create_app()
    cursor = cursor or _StubCursor(
        insert_result=(
            "user-1",
            "New User",
            "new.user@example.com",
            "requester",
            "Product Test",
            "active",
            True,
            datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
    )
    connection = _StubConnection(cursor)

    import app.routes.admin_users as admin_users
    import app.routes.auth as auth

    monkeypatch.setattr(auth, "_user_lookup_by_id", lambda _user_id: ("admin-1", "Admin", "admin@example.com", role, "active", "hash", False))
    monkeypatch.setattr(admin_users, "get_db_connection", lambda: connection)
    return app, cursor, connection


def _authenticate(client):
    with client.session_transaction() as session:
        session["user_id"] = "admin-1"


def _valid_payload(**overrides):
    payload = {
        "name": "New User",
        "email": " New.User@Example.COM ",
        "role": "requester",
        "department": "Product Test",
    }
    payload.update(overrides)
    return payload


def test_admin_creates_user_with_one_time_temporary_password(monkeypatch, caplog):
    app, cursor, connection = _app_with_current_user(monkeypatch)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/admin/users", json=_valid_payload(), headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 201
    payload = response.get_json()["data"]
    temporary_password = payload["temporary_password"]
    assert payload["user"] == {
        "id": "user-1",
        "name": "New User",
        "email": "new.user@example.com",
        "role": "requester",
        "department": "Product Test",
        "status": "active",
        "must_change_password": True,
        "created_at": "2026-09-01T00:00:00+00:00",
    }
    query, params = cursor.executed[0]
    assert "%s" in query
    assert "New User" not in query
    assert "sso_id" in query
    assert "NULL" in query
    assert params[:4] == ("New User", "new.user@example.com", "requester", "Product Test")
    assert check_password_hash(params[4], temporary_password)
    assert params[4] != temporary_password
    assert temporary_password not in query
    assert temporary_password not in caplog.text
    assert params[4] not in response.get_data(as_text=True)
    assert connection.committed is True
    assert response.headers["X-Request-ID"]
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


@pytest.mark.parametrize("role", ["requester", "support_engineer", "manager", "admin"])
def test_admin_can_provision_every_allowed_role(monkeypatch, role):
    app, cursor, _connection = _app_with_current_user(monkeypatch)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/admin/users", json=_valid_payload(role=role))

    assert response.status_code == 201
    assert cursor.executed[0][1][2] == role


@pytest.mark.parametrize("role", ["requester", "support_engineer", "manager"])
def test_non_admin_cannot_provision_users(monkeypatch, role):
    app, cursor, _connection = _app_with_current_user(monkeypatch, role=role)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/admin/users", json=_valid_payload())

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"
    assert cursor.executed == []


def test_unauthenticated_request_is_rejected(monkeypatch):
    app, cursor, _connection = _app_with_current_user(monkeypatch)

    with app.test_client() as client:
        response = client.post("/api/admin/users", json=_valid_payload())

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert cursor.executed == []


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (_valid_payload(name=None), "name"),
        (_valid_payload(email=None), "email"),
        (_valid_payload(role=None), "role"),
        (_valid_payload(name="   "), "name"),
        (_valid_payload(email="not-an-email"), "email"),
        (_valid_payload(role="Admin"), "role"),
        (_valid_payload(password="attempted-password"), "password"),
        (_valid_payload(status="inactive"), "status"),
        (_valid_payload(must_change_password=False), "must_change_password"),
        (_valid_payload(password_hash="attempted-hash"), "password_hash"),
    ],
)
def test_invalid_creation_data_is_rejected(monkeypatch, payload, field):
    app, cursor, _connection = _app_with_current_user(monkeypatch)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/admin/users", json=payload)

    assert response.status_code == 400
    assert field in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_duplicate_email_is_safe_conflict(monkeypatch):
    duplicate_error = psycopg.errors.UniqueViolation("users_email_unique")
    cursor = _StubCursor(insert_error=duplicate_error)
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/admin/users", json=_valid_payload())

    assert response.status_code == 409
    assert response.get_json()["error"] == {
        "code": "USER_ALREADY_EXISTS",
        "message": "An account with this email already exists.",
    }
    assert "users_email_unique" not in response.get_data(as_text=True)
    assert connection.committed is False


def test_database_error_is_masked_without_credential_leak(monkeypatch):
    cursor = _StubCursor(insert_error=psycopg.OperationalError("postgresql://db-user:db-password@internal"))
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/admin/users", json=_valid_payload())

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "postgresql://" not in response.get_data(as_text=True)
    assert "db-password" not in response.get_data(as_text=True)
    assert connection.committed is False