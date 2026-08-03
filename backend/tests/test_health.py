import psycopg

from app import create_app
from app.routes import health as health_routes


def test_health_endpoint_returns_expected_payload():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.is_json is True

    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["message"] == "ALE Ticket Management API is running"


class _StubCursor:
    def __init__(self):
        self.closed = False

    def execute(self, _query):
        return None

    def fetchone(self):
        return (1,)

    def close(self):
        self.closed = True


class _StubConnection:
    def __init__(self):
        self.closed = False
        self.cursor_instance = _StubCursor()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_database_health_endpoint_success(monkeypatch):
    app = create_app()
    stub_connection = _StubConnection()

    monkeypatch.setattr(health_routes, "get_db_connection", lambda: stub_connection)

    with app.test_client() as client:
        response = client.get("/health/database")

    assert response.status_code == 200
    assert response.is_json is True

    payload = response.get_json()
    assert payload["status"] == "healthy"
    assert payload["database"] == "connected"
    assert stub_connection.cursor_instance.closed is True
    assert stub_connection.closed is True


def test_database_health_endpoint_failure(monkeypatch):
    app = create_app()

    def _raise_db_error():
        raise psycopg.OperationalError("simulated connection failure")

    monkeypatch.setattr(health_routes, "get_db_connection", _raise_db_error)

    with app.test_client() as client:
        response = client.get("/health/database")

    assert response.status_code == 503
    assert response.is_json is True

    payload = response.get_json()
    assert payload["status"] == "unhealthy"
    assert payload["database"] == "unavailable"
