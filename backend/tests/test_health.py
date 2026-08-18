import psycopg

from app import create_app
from app.routes import health as health_routes


SAFE_ERROR_CODE = "DATABASE_UNAVAILABLE"
SAFE_ERROR_MESSAGE = "The database connection is unavailable."


class _StubCursor:
    def __init__(self, fetchone_result=(1,), execute_error=None, fetchone_error=None):
        self.closed = False
        self.entered = False
        self.exited = False
        self.executed_queries = []
        self.fetchone_called = False
        self.fetchone_result = fetchone_result
        self.execute_error = execute_error
        self.fetchone_error = fetchone_error

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.exited = True
        self.close()

    def execute(self, query):
        self.executed_queries.append(query)
        if self.execute_error is not None:
            raise self.execute_error
        return None

    def fetchone(self):
        self.fetchone_called = True
        if self.fetchone_error is not None:
            raise self.fetchone_error
        return self.fetchone_result

    def close(self):
        self.closed = True


class _StubConnection:
    def __init__(self, cursor_instance):
        self.closed = False
        self.entered = False
        self.exited = False
        self.cursor_instance = cursor_instance

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.exited = True
        self.close()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def _assert_sanitized_unhealthy_payload(payload):
    assert payload["status"] == "unhealthy"
    assert payload["backend"] == "active"
    assert payload["database"] == "unavailable"
    assert payload["error"]["code"] == SAFE_ERROR_CODE
    assert payload["error"]["message"] == SAFE_ERROR_MESSAGE

    payload_text = str(payload)
    assert "simulated" not in payload_text.lower()
    assert "exception" not in payload_text.lower()
    assert "traceback" not in payload_text.lower()
    assert "password" not in payload_text.lower()
    assert "user" not in payload_text.lower()
    assert "db_host" not in payload_text.lower()
    assert "localhost" not in payload_text.lower()
    assert "select 1" not in payload_text.lower()


def test_health_endpoint_success(monkeypatch):
    app = create_app()
    stub_cursor = _StubCursor(fetchone_result=(1,))
    stub_connection = _StubConnection(cursor_instance=stub_cursor)

    monkeypatch.setattr(health_routes, "get_db_connection", lambda: stub_connection)

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.is_json is True
    assert response.headers.get("X-Request-ID")

    payload = response.get_json()
    assert payload["status"] == "healthy"
    assert payload["backend"] == "active"
    assert payload["database"] == "connected"

    assert stub_connection.entered is True
    assert stub_connection.exited is True
    assert stub_connection.closed is True
    assert stub_cursor.entered is True
    assert stub_cursor.exited is True
    assert stub_cursor.closed is True
    assert stub_cursor.executed_queries == ["SELECT 1;"]
    assert stub_cursor.fetchone_called is True


def test_health_endpoint_database_failure(monkeypatch):
    app = create_app()

    def _raise_db_error():
        raise psycopg.OperationalError("simulated connection failure with localhost:5432")

    monkeypatch.setattr(health_routes, "get_db_connection", _raise_db_error)

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.is_json is True
    assert response.headers.get("X-Request-ID")

    payload = response.get_json()
    _assert_sanitized_unhealthy_payload(payload)


def test_health_endpoint_query_execution_failure(monkeypatch):
    app = create_app()
    stub_cursor = _StubCursor(
        execute_error=psycopg.OperationalError("simulated execute failure"),
    )
    stub_connection = _StubConnection(cursor_instance=stub_cursor)

    monkeypatch.setattr(health_routes, "get_db_connection", lambda: stub_connection)

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.is_json is True
    assert response.headers.get("X-Request-ID")

    payload = response.get_json()
    _assert_sanitized_unhealthy_payload(payload)
    assert stub_cursor.executed_queries == ["SELECT 1;"]
    assert stub_cursor.fetchone_called is False


def test_health_endpoint_unexpected_select_result(monkeypatch):
    app = create_app()
    stub_cursor = _StubCursor(fetchone_result=(2,))
    stub_connection = _StubConnection(cursor_instance=stub_cursor)

    monkeypatch.setattr(health_routes, "get_db_connection", lambda: stub_connection)

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.is_json is True
    assert response.headers.get("X-Request-ID")

    payload = response.get_json()
    _assert_sanitized_unhealthy_payload(payload)
    assert stub_cursor.executed_queries == ["SELECT 1;"]
    assert stub_cursor.fetchone_called is True
