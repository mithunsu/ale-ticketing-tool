from datetime import datetime, timezone
import secrets
import threading

import psycopg
import pytest
from werkzeug.security import check_password_hash

from app import create_app
from conftest import csrf_headers


class _StubCursor:
    def __init__(self, insert_result=None, insert_error=None, fetchall_result=None):
        self.insert_result = insert_result
        self.insert_error = insert_error
        self.fetchall_result = fetchall_result if fetchall_result is not None else []
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

    def fetchall(self):
        return self.fetchall_result


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
        response = client.post("/api/admin/users", json=_valid_payload(), headers=csrf_headers(client, Origin="http://localhost:5173"))

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
        response = client.post("/api/admin/users", json=_valid_payload(role=role), headers=csrf_headers(client))

    assert response.status_code == 201
    assert cursor.executed[0][1][2] == role


@pytest.mark.parametrize("role", ["requester", "support_engineer", "manager"])
def test_non_admin_cannot_provision_users(monkeypatch, role):
    app, cursor, _connection = _app_with_current_user(monkeypatch, role=role)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/admin/users", json=_valid_payload(), headers=csrf_headers(client))

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"
    assert cursor.executed == []


def test_unauthenticated_request_is_rejected(monkeypatch):
    app, cursor, _connection = _app_with_current_user(monkeypatch)

    with app.test_client() as client:
        response = client.post("/api/admin/users", json=_valid_payload(), headers=csrf_headers(client))

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
        response = client.post("/api/admin/users", json=payload, headers=csrf_headers(client))

    assert response.status_code == 400
    assert field in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_duplicate_email_is_safe_conflict(monkeypatch):
    duplicate_error = psycopg.errors.UniqueViolation("users_email_unique")
    cursor = _StubCursor(insert_error=duplicate_error)
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/admin/users", json=_valid_payload(), headers=csrf_headers(client))

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
        response = client.post("/api/admin/users", json=_valid_payload(), headers=csrf_headers(client))

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "postgresql://" not in response.get_data(as_text=True)
    assert "db-password" not in response.get_data(as_text=True)
    assert connection.committed is False


def _sample_user_row(**overrides):
    row = {
        "id": "user-1",
        "name": "Alice Admin",
        "email": "alice@example.com",
        "role": "admin",
        "department": "IT",
        "status": "active",
        "must_change_password": False,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "last_login_at": datetime(2026, 1, 3, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return (
        row["id"],
        row["name"],
        row["email"],
        row["role"],
        row["department"],
        row["status"],
        row["must_change_password"],
        row["created_at"],
        row["updated_at"],
        row["last_login_at"],
    )


def test_unauthenticated_list_users_request_is_rejected(monkeypatch):
    app, cursor, _connection = _app_with_current_user(monkeypatch)

    with app.test_client() as client:
        response = client.get("/api/admin/users")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert cursor.executed == []


@pytest.mark.parametrize("role", ["requester", "support_engineer", "manager"])
def test_non_admin_cannot_list_users(monkeypatch, role):
    app, cursor, _connection = _app_with_current_user(monkeypatch, role=role)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/admin/users")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"
    assert cursor.executed == []


def test_admin_can_list_active_and_suspended_users(monkeypatch):
    rows = [
        _sample_user_row(id="user-1", name="Alice Admin", status="active"),
        _sample_user_row(id="user-2", name="Bob Requester", role="requester", status="inactive"),
    ]
    cursor = _StubCursor(fetchall_result=rows)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/admin/users")

    assert response.status_code == 200
    users = response.get_json()["data"]["users"]
    statuses = {user["status"] for user in users}
    assert statuses == {"active", "inactive"}


def test_list_users_response_exposes_expected_safe_fields(monkeypatch):
    rows = [_sample_user_row()]
    cursor = _StubCursor(fetchall_result=rows)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/admin/users")

    assert response.status_code == 200
    user = response.get_json()["data"]["users"][0]
    assert user == {
        "id": "user-1",
        "name": "Alice Admin",
        "email": "alice@example.com",
        "role": "admin",
        "department": "IT",
        "status": "active",
        "must_change_password": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
        "last_login_at": "2026-01-03T00:00:00+00:00",
    }


def test_list_users_never_exposes_password_hash(monkeypatch):
    rows = [_sample_user_row()]
    cursor = _StubCursor(fetchall_result=rows)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/admin/users")

    body = response.get_data(as_text=True)
    assert "password_hash" not in body
    users = response.get_json()["data"]["users"]
    disallowed_keys = {"password", "password_hash", "temporary_password"}
    assert all(not (disallowed_keys & user.keys()) for user in users)


def test_list_users_database_error_is_masked(monkeypatch):
    cursor = _StubCursor(insert_error=psycopg.OperationalError("postgresql://db-user:db-password@internal"))
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/admin/users")

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "postgresql://" not in response.get_data(as_text=True)
    assert "db-password" not in response.get_data(as_text=True)


class _RoleLockStubCursor:
    """Stub cursor for the role-change endpoint's single locking SELECT + optional UPDATE.

    `locked_rows` models the result of the combined "target row + all active admin rows"
    FOR UPDATE query (consumed via fetchall()); `updated_row` models the UPDATE ... RETURNING
    result (consumed via fetchone()), issued only when a role change actually occurs.
    """

    def __init__(self, locked_rows=None, updated_row=None, error=None):
        self.locked_rows = locked_rows if locked_rows is not None else []
        self.updated_row = updated_row
        self.error = error
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if self.error is not None:
            raise self.error

    def fetchall(self):
        return self.locked_rows

    def fetchone(self):
        return self.updated_row


TARGET_USER_ID = "11111111-1111-1111-1111-111111111111"


def _role_payload(role="support_engineer", **overrides):
    payload = {"role": role}
    payload.update(overrides)
    return payload


def test_unauthenticated_role_change_request_is_rejected(monkeypatch):
    app, _cursor, _connection = _app_with_current_user(monkeypatch)

    with app.test_client() as client:
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(),
            headers=csrf_headers(client, Origin="http://localhost:5173"),
        )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize("role", ["requester", "support_engineer", "manager"])
def test_non_admin_cannot_change_roles(monkeypatch, role):
    cursor = _RoleLockStubCursor()
    app, _cursor, _connection = _app_with_current_user(monkeypatch, role=role, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(),
            headers=csrf_headers(client),
        )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"
    assert cursor.executed == []


def test_admin_can_change_requester_to_support_engineer(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="support_engineer", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="support_engineer"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["role"] == "support_engineer"
    assert connection.committed is True


def test_admin_can_change_support_engineer_to_manager(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="support_engineer", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="manager", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="manager"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["role"] == "manager"


def test_admin_can_promote_user_to_admin(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="manager", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="admin", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="admin"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["role"] == "admin"
    # Promotion never demotes an admin, so only the lock query + UPDATE run (no extra check).
    assert len(cursor.executed) == 2


def test_role_change_rejects_invalid_role(monkeypatch):
    cursor = _RoleLockStubCursor()
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="superuser"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 400
    assert "role" in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_role_change_rejects_unknown_fields(monkeypatch):
    cursor = _RoleLockStubCursor()
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(current_role="requester"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 400
    assert "current_role" in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_role_change_nonexistent_target_user_returns_404(monkeypatch):
    cursor = _RoleLockStubCursor(locked_rows=[])
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(),
            headers=csrf_headers(client),
        )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "USER_NOT_FOUND"


@pytest.mark.parametrize("new_role", ["requester", "support_engineer", "manager"])
def test_admin_cannot_demote_self(monkeypatch, new_role):
    self_row = _sample_user_row(id=TARGET_USER_ID, role="admin", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[self_row])
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    import app.routes.auth as auth

    monkeypatch.setattr(
        auth,
        "_user_lookup_by_id",
        lambda _user_id: (TARGET_USER_ID, "Admin", "admin@example.com", "admin", "active", "hash", False),
    )

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role=new_role),
            headers=csrf_headers(client),
        )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "SELF_DEMOTION_FORBIDDEN"
    assert len(cursor.executed) == 1


def test_other_admin_may_demote_admin_when_another_active_admin_remains(monkeypatch):
    other_active_admin_row = _sample_user_row(id="admin-1", role="admin", status="active")
    target_row = _sample_user_row(id=TARGET_USER_ID, role="admin", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="manager", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[other_active_admin_row, target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="manager"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["role"] == "manager"


def test_last_active_admin_cannot_be_demoted(monkeypatch):
    # Only the target itself comes back locked: no other active admin exists.
    target_row = _sample_user_row(id=TARGET_USER_ID, role="admin", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row])
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="manager"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "LAST_ACTIVE_ADMIN"
    assert connection.committed is False  # Rejected before the UPDATE ever ran.
    assert len(cursor.executed) == 1  # Decision made from the lock query alone; no extra query.


def test_same_role_request_is_a_safe_noop(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="manager", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row])
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="manager"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["role"] == "manager"
    # Same-role request never issues an UPDATE.
    assert len(cursor.executed) == 1


def test_role_update_changes_only_role_and_updated_at(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="manager", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="manager"),
            headers=csrf_headers(client),
        )

    update_query, update_params = cursor.executed[-1]
    assert "UPDATE users" in update_query
    assert "SET role = %s, updated_at = CURRENT_TIMESTAMP" in update_query
    for untouched_column in ("status", "password_hash", "must_change_password", "department", "email", "name", "sso_id"):
        assert f"{untouched_column} =" not in update_query
    assert update_params == ("manager", TARGET_USER_ID)


def test_lock_query_precedes_the_last_admin_decision(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="manager", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="manager"),
            headers=csrf_headers(client),
        )

    lock_query, lock_params = cursor.executed[0]
    assert "FOR UPDATE" in lock_query
    assert "role = 'admin'" in lock_query
    assert "status = 'active'" in lock_query
    assert "ORDER BY id" in lock_query
    assert lock_params == (TARGET_USER_ID,)
    # The UPDATE (if any) must come strictly after the lock query.
    assert cursor.executed[-1][0] != lock_query or len(cursor.executed) == 1


def test_role_update_uses_bound_parameters_not_string_interpolation(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="manager", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="manager"),
            headers=csrf_headers(client),
        )

    for query, params in cursor.executed:
        assert TARGET_USER_ID not in query
        assert "manager" not in query
        assert params is None or "%s" in query


def test_role_change_response_never_exposes_password_hash(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="manager", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(role="manager"),
            headers=csrf_headers(client),
        )

    assert "password_hash" not in response.get_data(as_text=True)
    assert "password_hash" not in response.get_json()["data"]["user"]


def test_role_change_database_failure_during_lock_phase_rolls_back_safely(monkeypatch):
    cursor = _RoleLockStubCursor(error=psycopg.OperationalError("postgresql://db-user:db-password@internal"))
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/role",
            json=_role_payload(),
            headers=csrf_headers(client),
        )

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "postgresql://" not in response.get_data(as_text=True)
    assert "db-password" not in response.get_data(as_text=True)
    assert connection.committed is False


def _status_payload(status="inactive", **overrides):
    payload = {"status": status}
    payload.update(overrides)
    return payload


def test_unauthenticated_status_change_request_is_rejected(monkeypatch):
    app, _cursor, _connection = _app_with_current_user(monkeypatch)

    with app.test_client() as client:
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(),
            headers=csrf_headers(client, Origin="http://localhost:5173"),
        )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize("role", ["requester", "support_engineer", "manager"])
def test_non_admin_cannot_change_status(monkeypatch, role):
    cursor = _RoleLockStubCursor()
    app, _cursor, _connection = _app_with_current_user(monkeypatch, role=role, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(),
            headers=csrf_headers(client),
        )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"
    assert cursor.executed == []


def test_admin_can_deactivate_active_requester(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="inactive")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="inactive"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["status"] == "inactive"
    assert connection.committed is True


def test_admin_can_reactivate_inactive_requester(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="inactive")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="active"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["status"] == "active"


def test_admin_can_deactivate_support_engineer(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="support_engineer", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="support_engineer", status="inactive")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="inactive"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["status"] == "inactive"


def test_admin_can_reactivate_support_engineer(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="support_engineer", status="inactive")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="support_engineer", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="active"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["status"] == "active"


def test_status_change_rejects_invalid_status(monkeypatch):
    cursor = _RoleLockStubCursor()
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="suspended"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 400
    assert "status" in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_status_change_rejects_unknown_fields(monkeypatch):
    cursor = _RoleLockStubCursor()
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(current_status="active", role="manager"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 400
    details = response.get_json()["error"]["details"]
    assert "current_status" in details
    assert "role" in details
    assert cursor.executed == []


def test_status_change_nonexistent_target_user_returns_404(monkeypatch):
    cursor = _RoleLockStubCursor(locked_rows=[])
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(),
            headers=csrf_headers(client),
        )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "USER_NOT_FOUND"


def test_admin_cannot_deactivate_self(monkeypatch):
    self_row = _sample_user_row(id=TARGET_USER_ID, role="admin", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[self_row])
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    import app.routes.auth as auth

    monkeypatch.setattr(
        auth,
        "_user_lookup_by_id",
        lambda _user_id: (TARGET_USER_ID, "Admin", "admin@example.com", "admin", "active", "hash", False),
    )

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="inactive"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "SELF_DEACTIVATION_FORBIDDEN"
    assert len(cursor.executed) == 1


def test_other_admin_may_deactivate_admin_when_another_active_admin_remains(monkeypatch):
    other_active_admin_row = _sample_user_row(id="admin-1", role="admin", status="active")
    target_row = _sample_user_row(id=TARGET_USER_ID, role="admin", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="admin", status="inactive")
    cursor = _RoleLockStubCursor(locked_rows=[other_active_admin_row, target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="inactive"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["status"] == "inactive"


def test_last_active_admin_cannot_be_deactivated(monkeypatch):
    # Only the target itself comes back locked: no other active admin exists.
    target_row = _sample_user_row(id=TARGET_USER_ID, role="admin", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row])
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="inactive"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "LAST_ACTIVE_ADMIN"
    assert connection.committed is False
    assert len(cursor.executed) == 1


def test_active_to_active_is_a_safe_noop(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    cursor = _RoleLockStubCursor(locked_rows=[target_row])
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="active"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["status"] == "active"
    # Same-status request never issues an UPDATE.
    assert len(cursor.executed) == 1


def test_inactive_to_inactive_is_a_safe_noop(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="inactive")
    cursor = _RoleLockStubCursor(locked_rows=[target_row])
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="inactive"),
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["status"] == "inactive"
    assert len(cursor.executed) == 1


def test_status_update_changes_only_status_and_updated_at(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="inactive")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="inactive"),
            headers=csrf_headers(client),
        )

    update_query, update_params = cursor.executed[-1]
    assert "UPDATE users" in update_query
    assert "SET status = %s, updated_at = CURRENT_TIMESTAMP" in update_query
    for untouched_column in ("role", "password_hash", "must_change_password", "department", "email", "name", "sso_id"):
        assert f"{untouched_column} =" not in update_query
    assert update_params == ("inactive", TARGET_USER_ID)


def test_status_update_uses_bound_parameters_not_string_interpolation(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="inactive")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="inactive"),
            headers=csrf_headers(client),
        )

    for query, params in cursor.executed:
        assert TARGET_USER_ID not in query
        assert "inactive" not in query
        assert params is None or "%s" in query


def test_status_change_response_never_exposes_password_hash(monkeypatch):
    target_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="inactive")
    cursor = _RoleLockStubCursor(locked_rows=[target_row], updated_row=updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(status="inactive"),
            headers=csrf_headers(client),
        )

    assert "password_hash" not in response.get_data(as_text=True)
    assert "password_hash" not in response.get_json()["data"]["user"]


def test_status_change_database_failure_rolls_back_safely(monkeypatch):
    cursor = _RoleLockStubCursor(error=psycopg.OperationalError("postgresql://db-user:db-password@internal"))
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.patch(
            f"/api/admin/users/{TARGET_USER_ID}/status",
            json=_status_payload(),
            headers=csrf_headers(client),
        )

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "postgresql://" not in response.get_data(as_text=True)
    assert "db-password" not in response.get_data(as_text=True)
    assert connection.committed is False


def _create_admin_user(db_config, name, email):
    with psycopg.connect(**db_config, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, role, department, status, password_hash, must_change_password)
                VALUES (%s, %s, 'admin', 'IT', 'active', 'placeholder_hash', false)
                RETURNING id;
                """,
                (name, email),
            )
            row = cur.fetchone()
            assert row is not None
            return str(row[0])


def test_concurrent_cross_demotion_of_last_two_admins_cannot_both_succeed(postgres_disposable_db):
    """Real two-connection Postgres concurrency test.

    Stub-cursor unit tests above run entirely single-threaded/sequentially and cannot model
    two genuinely concurrent PostgreSQL transactions racing for the same row locks, so this
    integration test exercises the real locking behavior against a disposable database.
    """
    test_db = postgres_disposable_db
    admin_a_id = _create_admin_user(test_db["config"], "Admin A", "admin.a@example.com")
    admin_b_id = _create_admin_user(test_db["config"], "Admin B", "admin.b@example.com")

    app_a = create_app()
    app_b = create_app()
    barrier = threading.Barrier(2)
    results = {}

    def _attempt_demotion(app, actor_id, target_id, key):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = actor_id
            headers = csrf_headers(client)
            barrier.wait()
            response = client.patch(
                f"/api/admin/users/{target_id}/role",
                json={"role": "manager"},
                headers=headers,
            )
            results[key] = (response.status_code, response.get_json())

    thread_a = threading.Thread(target=_attempt_demotion, args=(app_a, admin_a_id, admin_b_id, "a"))
    thread_b = threading.Thread(target=_attempt_demotion, args=(app_b, admin_b_id, admin_a_id, "b"))
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=10)
    thread_b.join(timeout=10)

    assert "a" in results and "b" in results
    statuses = sorted(status for status, _body in results.values())
    assert statuses == [200, 403]

    rejected_key = "a" if results["a"][0] == 403 else "b"
    assert results[rejected_key][1]["error"]["code"] == "LAST_ACTIVE_ADMIN"

    with psycopg.connect(**test_db["config"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'active';")
            (remaining_active_admins,) = cur.fetchone()
    assert remaining_active_admins >= 1


def test_concurrent_cross_endpoint_demotion_and_deactivation_cannot_both_succeed(postgres_disposable_db):
    """Proves the role-change and status-change endpoints share one locking protocol.

    Admin A is demoted (via PATCH .../role) at the same time Admin B is deactivated
    (via PATCH .../status). Only one of the two operations may succeed, because both
    endpoints lock the same target-plus-active-admins row set in the same id order.
    """
    test_db = postgres_disposable_db
    admin_a_id = _create_admin_user(test_db["config"], "Admin A", "admin.a@example.com")
    admin_b_id = _create_admin_user(test_db["config"], "Admin B", "admin.b@example.com")

    app_a = create_app()
    app_b = create_app()
    barrier = threading.Barrier(2)
    results = {}

    def _attempt(app, actor_id, path, body, key):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = actor_id
            headers = csrf_headers(client)
            barrier.wait()
            response = client.patch(path, json=body, headers=headers)
            results[key] = (response.status_code, response.get_json())

    # admin_a (acting as itself's peer B) demotes admin_b's role; admin_b deactivates admin_a's status.
    thread_role = threading.Thread(
        target=_attempt,
        args=(app_a, admin_a_id, f"/api/admin/users/{admin_b_id}/role", {"role": "manager"}, "role"),
    )
    thread_status = threading.Thread(
        target=_attempt,
        args=(app_b, admin_b_id, f"/api/admin/users/{admin_a_id}/status", {"status": "inactive"}, "status"),
    )
    thread_role.start()
    thread_status.start()
    thread_role.join(timeout=10)
    thread_status.join(timeout=10)

    assert "role" in results and "status" in results
    statuses = sorted(status for status, _body in results.values())
    assert statuses == [200, 403]

    rejected_key = "role" if results["role"][0] == 403 else "status"
    assert results[rejected_key][1]["error"]["code"] == "LAST_ACTIVE_ADMIN"

    with psycopg.connect(**test_db["config"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'active';")
            (remaining_active_admins,) = cur.fetchone()
    assert remaining_active_admins >= 1


def _reset_password_stub_cursor(updated_row, error=None):
    return _StubCursor(insert_result=updated_row, insert_error=error)


@pytest.mark.parametrize("role", ["requester", "support_engineer", "manager"])
def test_non_admin_cannot_reset_passwords(monkeypatch, role):
    cursor = _reset_password_stub_cursor(None)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, role=role, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"
    assert cursor.executed == []


def test_unauthenticated_reset_password_request_is_rejected(monkeypatch):
    cursor = _reset_password_stub_cursor(None)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client, Origin="http://localhost:5173"),
        )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize("role", ["requester", "support_engineer", "manager", "admin"])
def test_admin_can_reset_password_for_every_target_role(monkeypatch, role):
    updated_row = _sample_user_row(id=TARGET_USER_ID, role=role, status="active")
    cursor = _reset_password_stub_cursor(updated_row)
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["user"]["role"] == role
    assert body["temporary_password"]
    assert connection.committed is True


def test_admin_cannot_reset_their_own_password(monkeypatch):
    cursor = _reset_password_stub_cursor(None)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    import app.routes.auth as auth

    monkeypatch.setattr(
        auth,
        "_user_lookup_by_id",
        lambda _user_id: (TARGET_USER_ID, "Admin", "admin@example.com", "admin", "active", "hash", False),
    )

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "SELF_PASSWORD_RESET_FORBIDDEN"
    assert cursor.executed == []


def test_reset_password_nonexistent_target_returns_404(monkeypatch):
    cursor = _reset_password_stub_cursor(None)
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "USER_NOT_FOUND"
    assert connection.committed is False


def test_reset_password_generates_server_side_secure_temporary_password(monkeypatch):
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    cursor = _reset_password_stub_cursor(updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    captured = {}

    def _fake_token_urlsafe(nbytes):
        captured["nbytes"] = nbytes
        return "server-generated-temporary-password"

    monkeypatch.setattr(secrets, "token_urlsafe", _fake_token_urlsafe)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["temporary_password"] == "server-generated-temporary-password"
    assert captured["nbytes"] == 24  # Same secure generator/length as POST /api/admin/users.


def test_reset_password_stores_hash_not_plaintext(monkeypatch):
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    cursor = _reset_password_stub_cursor(updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    temporary_password = response.get_json()["data"]["temporary_password"]
    update_query, update_params = cursor.executed[0]
    assert "password_hash = %s" in update_query
    stored_hash = update_params[0]
    assert stored_hash != temporary_password
    assert check_password_hash(stored_hash, temporary_password)


def test_reset_password_sets_must_change_password_true(monkeypatch):
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active", must_change_password=True)
    cursor = _reset_password_stub_cursor(updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert response.get_json()["data"]["user"]["must_change_password"] is True
    update_query, _params = cursor.executed[0]
    assert "must_change_password = true" in update_query


def test_reset_password_role_remains_unchanged(monkeypatch):
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="manager", status="active")
    cursor = _reset_password_stub_cursor(updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert response.get_json()["data"]["user"]["role"] == "manager"
    update_query, _params = cursor.executed[0]
    assert "role =" not in update_query


def test_reset_password_leaves_inactive_target_inactive(monkeypatch):
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="inactive")
    cursor = _reset_password_stub_cursor(updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["status"] == "inactive"
    update_query, _params = cursor.executed[0]
    assert "status =" not in update_query


def test_reset_password_update_touches_only_expected_columns(monkeypatch):
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    cursor = _reset_password_stub_cursor(updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    update_query, update_params = cursor.executed[0]
    assert "UPDATE users" in update_query
    assert "SET password_hash = %s, must_change_password = true, updated_at = CURRENT_TIMESTAMP" in update_query
    for untouched_column in ("role", "status", "name", "email", "department", "sso_id", "last_login_at"):
        assert f"{untouched_column} =" not in update_query
    assert update_params[1] == TARGET_USER_ID


def test_reset_password_uses_bound_parameters_not_string_interpolation(monkeypatch):
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    cursor = _reset_password_stub_cursor(updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    for query, params in cursor.executed:
        assert TARGET_USER_ID not in query
        assert params is None or "%s" in query


def test_reset_password_response_never_exposes_password_hash(monkeypatch):
    updated_row = _sample_user_row(id=TARGET_USER_ID, role="requester", status="active")
    cursor = _reset_password_stub_cursor(updated_row)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert "password_hash" not in response.get_data(as_text=True)
    assert "password_hash" not in response.get_json()["data"]["user"]


def test_reset_password_rejects_unknown_json_fields(monkeypatch):
    cursor = _reset_password_stub_cursor(None)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            json={"must_change_password": False, "status": "inactive"},
            headers=csrf_headers(client),
        )

    assert response.status_code == 400
    details = response.get_json()["error"]["details"]
    assert "must_change_password" in details
    assert "status" in details
    assert cursor.executed == []


def test_reset_password_database_failure_returns_safe_error_and_no_temporary_password(monkeypatch, caplog):
    cursor = _reset_password_stub_cursor(
        None, error=psycopg.OperationalError("postgresql://db-user:db-password@internal")
    )
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post(
            f"/api/admin/users/{TARGET_USER_ID}/reset-password",
            headers=csrf_headers(client),
        )

    assert response.status_code == 500
    body = response.get_data(as_text=True)
    assert response.get_json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "temporary_password" not in body
    assert "postgresql://" not in body
    assert "db-password" not in body
    # The secret itself must never be logged, even though the (generic) DB error may be.
    assert "temporary_password" not in caplog.text
    assert connection.committed is False


def test_integration_reset_password_enforces_password_change_on_next_request(postgres_disposable_db):
    """Proves the reset actually restricts the target's next protected request, not just a DB row."""
    test_db = postgres_disposable_db
    target_user_id = test_db["user_id"]  # requester, active, must_change_password=False by fixture
    admin_id = _create_admin_user(test_db["config"], "Admin", "admin.reset@example.com")

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = target_user_id
        before_response = client.get("/api/tickets")
        assert before_response.status_code == 200

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin_id
        reset_response = client.post(
            f"/api/admin/users/{target_user_id}/reset-password",
            headers=csrf_headers(client),
        )

    assert reset_response.status_code == 200
    reset_body = reset_response.get_json()["data"]
    assert reset_body["temporary_password"]
    assert reset_body["user"]["role"] == "requester"
    assert reset_body["user"]["status"] == "active"

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = target_user_id
        after_response = client.get("/api/tickets")

    assert after_response.status_code == 403
    assert after_response.get_json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    with psycopg.connect(**test_db["config"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role, status FROM users WHERE id = %s;", (target_user_id,))
            role, status = cur.fetchone()
    assert role == "requester"
    assert status == "active"