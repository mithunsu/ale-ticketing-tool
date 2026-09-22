import psycopg
import pytest

from app import create_app
from conftest import csrf_headers


class _StubCursor:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchall(self):
        return self.rows


class _StubConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        pass


CURRENT_USER_ID = "d2f7b022-7772-4d2a-a92c-0e9e110d9f01"

ROWS = [
    ("s1", "Sam Support", "support_engineer"),
    ("m1", "Mary Manager", "manager"),
]


def _app_with_user(monkeypatch, role, rows=None):
    app = create_app()
    cursor = _StubCursor(rows if rows is not None else ROWS)
    connection = _StubConnection(cursor)

    import app.routes.auth as auth
    import app.routes.users as users

    monkeypatch.setattr(
        auth,
        "_user_lookup_by_id",
        lambda _user_id: (CURRENT_USER_ID, "Actor", "actor@example.com", role, "active", "hash", False),
    )
    monkeypatch.setattr(users, "get_db_connection", lambda: connection)
    return app, cursor, connection


def _authenticate(client):
    with client.session_transaction() as session:
        session["user_id"] = CURRENT_USER_ID


def test_manager_can_list_assignable_users(monkeypatch):
    app, cursor, _connection = _app_with_user(monkeypatch, "manager")

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/users/assignable", headers=csrf_headers(client))

    assert response.status_code == 200
    query, params = cursor.executed[0]
    assert params is None
    assert response.get_json()["data"]["users"] == [
        {"id": "s1", "name": "Sam Support", "role": "support_engineer"},
        {"id": "m1", "name": "Mary Manager", "role": "manager"},
    ]


def test_admin_can_list_assignable_users(monkeypatch):
    rows = ROWS + [(CURRENT_USER_ID, "Andy Admin", "admin")]
    app, cursor, _connection = _app_with_user(monkeypatch, "admin", rows=rows)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/users/assignable", headers=csrf_headers(client))

    assert response.status_code == 200
    query, params = cursor.executed[0]
    assert params == (CURRENT_USER_ID,)
    assert "%s" in query
    users_payload = response.get_json()["data"]["users"]
    assert {"id": CURRENT_USER_ID, "name": "Andy Admin", "role": "admin"} in users_payload


def test_requester_cannot_list_assignable_users(monkeypatch):
    app, cursor, _connection = _app_with_user(monkeypatch, "requester")

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/users/assignable", headers=csrf_headers(client))

    assert response.status_code == 403
    assert cursor.executed == []


def test_support_engineer_cannot_list_assignable_users(monkeypatch):
    app, cursor, _connection = _app_with_user(monkeypatch, "support_engineer")

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/users/assignable", headers=csrf_headers(client))

    assert response.status_code == 403
    assert cursor.executed == []


def test_unauthenticated_request_is_rejected():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/api/users/assignable")

    assert response.status_code == 401


def test_manager_query_excludes_requesters_and_admins_and_inactive_users(monkeypatch):
    app, cursor, _connection = _app_with_user(monkeypatch, "manager")

    with app.test_client() as client:
        _authenticate(client)
        client.get("/api/users/assignable", headers=csrf_headers(client))

    query, _params = cursor.executed[0]
    assert "status = 'active'" in query
    assert "role IN ('support_engineer', 'manager')" in query
    assert "id = %s" not in query


def test_admin_query_includes_self_but_not_other_admins(monkeypatch):
    app, cursor, _connection = _app_with_user(monkeypatch, "admin")

    with app.test_client() as client:
        _authenticate(client)
        client.get("/api/users/assignable", headers=csrf_headers(client))

    query, params = cursor.executed[0]
    assert "status = 'active'" in query
    assert "role IN ('support_engineer', 'manager') OR id = %s" in query
    assert params == (CURRENT_USER_ID,)


def test_response_contains_only_id_name_role(monkeypatch):
    app, cursor, _connection = _app_with_user(monkeypatch, "manager")

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/users/assignable", headers=csrf_headers(client))

    for user in response.get_json()["data"]["users"]:
        assert set(user.keys()) == {"id", "name", "role"}


def test_ordering_is_preserved_from_query(monkeypatch):
    app, cursor, _connection = _app_with_user(monkeypatch, "manager")

    with app.test_client() as client:
        _authenticate(client)
        client.get("/api/users/assignable", headers=csrf_headers(client))

    query, _params = cursor.executed[0]
    assert "ORDER BY name ASC, id ASC" in query


# The admin query's "OR id = %s" self branch must still require status = 'active';
# this runs the exact production SQL against a real database to prove that.
ADMIN_ASSIGNABLE_USERS_QUERY = """
    SELECT id, name, role
    FROM users
    WHERE status = 'active' AND (role IN ('support_engineer', 'manager') OR id = %s)
    ORDER BY name ASC, id ASC;
"""


def test_inactive_current_admin_self_is_excluded_by_real_query(postgres_disposable_db):
    test_db = postgres_disposable_db

    with psycopg.connect(**test_db["config"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (name, email, role, department, status, password_hash, must_change_password)
                VALUES
                    ('Inactive Admin', 'inactive.admin@example.com', 'admin', 'IT', 'inactive', 'placeholder_hash', false),
                    ('Active Engineer', 'active.engineer@example.com', 'support_engineer', 'Support', 'active', 'placeholder_hash', false),
                    ('Active Manager', 'active.manager@example.com', 'manager', 'Support', 'active', 'placeholder_hash', false)
                RETURNING id, role;
                """
            )
            inserted = cursor.fetchall()
        connection.commit()

    inactive_admin_id = str(next(row[0] for row in inserted if row[1] == "admin"))

    with psycopg.connect(**test_db["config"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(ADMIN_ASSIGNABLE_USERS_QUERY, (inactive_admin_id,))
            result_ids = {str(row[0]) for row in cursor.fetchall()}

    assert inactive_admin_id not in result_ids
    assert len(result_ids) == 2
