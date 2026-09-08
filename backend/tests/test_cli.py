import psycopg
from werkzeug.security import check_password_hash

from app import create_app


class _StubCursor:
    def __init__(self, select_result=None, insert_result=None, insert_error=None):
        self.select_result = select_result
        self.insert_result = insert_result
        self.insert_error = insert_error
        self.executed = []
        self.fetchone_result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if query.strip().upper().startswith("SELECT"):
            self.fetchone_result = self.select_result
        else:
            if self.insert_error is not None:
                raise self.insert_error
            self.fetchone_result = self.insert_result

    def fetchone(self):
        result = self.fetchone_result
        self.fetchone_result = None
        return result


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


def _create_app_with_db(monkeypatch, cursor):
    app = create_app()
    connection = _StubConnection(cursor)

    import app.cli as cli

    monkeypatch.setattr(cli, "get_db_connection", lambda: connection)
    return app, connection


def _command_input(name="Admin User", email="admin@example.com", department="Operations", password="CorrectHorse12"):
    return f"{name}\n{email}\n{department}\n{password}\n{password}\n"


def _insert_execution(cursor):
    return next((execution for execution in cursor.executed if "INSERT INTO users" in execution[0]), None)


def test_create_admin_inserts_normalized_secure_account(monkeypatch):
    password = "Correct Horse Battery 12"
    cursor = _StubCursor(insert_result=("user-1", "Admin User", "admin.user@example.com", "admin", "active"))
    app, connection = _create_app_with_db(monkeypatch, cursor)

    result = app.test_cli_runner().invoke(
        args=["create-admin"],
        input=_command_input(email=" Admin.User@Example.COM ", password=password),
    )

    assert result.exit_code == 0
    insert = _insert_execution(cursor)
    assert insert is not None
    query, params = insert
    assert "%s" in query
    assert "Admin User" not in query
    assert params[0] == "Admin User"
    assert params[1] == "admin.user@example.com"
    assert params[2] == "Operations"
    assert check_password_hash(params[3], password) is True
    assert params[3] != password
    assert "'admin'" in query
    assert "'active'" in query
    assert "false" in query
    assert connection.committed is True
    assert "Admin account created successfully." in result.output
    assert "Email: admin.user@example.com" in result.output
    assert password not in result.output
    assert params[3] not in result.output


def test_create_admin_rejects_duplicate_email_without_insert(monkeypatch):
    cursor = _StubCursor(select_result=(1,))
    app, connection = _create_app_with_db(monkeypatch, cursor)

    result = app.test_cli_runner().invoke(args=["create-admin"], input=_command_input())

    assert result.exit_code != 0
    assert "An account with this email already exists." in result.output
    assert _insert_execution(cursor) is None
    assert connection.committed is False


def test_create_admin_allows_another_admin_with_different_email(monkeypatch):
    cursor = _StubCursor(insert_result=("user-2", "Second Admin", "second@example.com", "admin", "active"))
    app, connection = _create_app_with_db(monkeypatch, cursor)

    result = app.test_cli_runner().invoke(
        args=["create-admin"],
        input=_command_input(name="Second Admin", email="second@example.com"),
    )

    assert result.exit_code == 0
    assert _insert_execution(cursor) is not None
    assert connection.committed is True


def test_create_admin_rejects_password_confirmation_mismatch_without_database_access(monkeypatch):
    cursor = _StubCursor()
    app, _connection = _create_app_with_db(monkeypatch, cursor)
    password = "CorrectHorse12"

    result = app.test_cli_runner().invoke(
        args=["create-admin"],
        input="Admin User\nadmin@example.com\n\nCorrectHorse12\nDifferentHorse12\n",
    )

    assert result.exit_code != 0
    assert cursor.executed == []
    assert password not in result.output
    assert "DifferentHorse12" not in result.output


def test_create_admin_rejects_short_password_without_insert(monkeypatch):
    cursor = _StubCursor()
    app, _connection = _create_app_with_db(monkeypatch, cursor)

    result = app.test_cli_runner().invoke(
        args=["create-admin"],
        input=_command_input(password="too-short"),
    )

    assert result.exit_code != 0
    assert "Password must be at least 12 characters." in result.output
    assert _insert_execution(cursor) is None
    assert "too-short" not in result.output


def test_create_admin_rejects_whitespace_only_name_without_insert(monkeypatch):
    cursor = _StubCursor()
    app, _connection = _create_app_with_db(monkeypatch, cursor)

    result = app.test_cli_runner().invoke(args=["create-admin"], input=_command_input(name="   "))

    assert result.exit_code != 0
    assert "Name must not be empty." in result.output
    assert _insert_execution(cursor) is None


def test_create_admin_masks_database_errors_and_password(monkeypatch):
    cursor = _StubCursor(insert_error=psycopg.OperationalError("postgresql://db-user:db-password@internal"))
    app, connection = _create_app_with_db(monkeypatch, cursor)
    password = "CorrectHorse12"

    result = app.test_cli_runner().invoke(args=["create-admin"], input=_command_input(password=password))

    assert result.exit_code != 0
    assert "Unable to create the administrator account." in result.output
    assert "postgresql://" not in result.output
    assert "db-password" not in result.output
    assert password not in result.output
    assert connection.committed is False