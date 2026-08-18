import logging
import re

from app import create_app
from app.routes import health as health_routes


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class _StubCursor:
    def __init__(self):
        self.executed_queries = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return None

    def execute(self, query):
        self.executed_queries.append(query)

    def fetchone(self):
        return (1,)


class _StubConnection:
    def __init__(self):
        self.cursor_instance = _StubCursor()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return None

    def cursor(self):
        return self.cursor_instance


def _stub_get_db_connection():
    return _StubConnection()


def _assert_safe_generated_request_id(value):
    assert isinstance(value, str)
    assert value
    assert len(value) <= 128
    assert UUID_PATTERN.match(value)
    assert "\n" not in value
    assert "\r" not in value


def test_response_has_generated_request_id_when_header_is_missing(monkeypatch):
    app = create_app()
    monkeypatch.setattr(health_routes, "get_db_connection", _stub_get_db_connection)

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    _assert_safe_generated_request_id(response.headers.get("X-Request-ID"))


def test_valid_incoming_request_id_is_preserved_after_trimming(monkeypatch):
    app = create_app()
    monkeypatch.setattr(health_routes, "get_db_connection", _stub_get_db_connection)

    with app.test_client() as client:
        response = client.get("/api/health", headers={"X-Request-ID": "   phase1-request-123   "})

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "phase1-request-123"


def test_blank_request_id_is_replaced(monkeypatch):
    app = create_app()
    monkeypatch.setattr(health_routes, "get_db_connection", _stub_get_db_connection)

    with app.test_client() as client:
        response = client.get("/api/health", headers={"X-Request-ID": "   "})

    assert response.status_code == 200
    generated = response.headers.get("X-Request-ID")
    assert generated != ""
    _assert_safe_generated_request_id(generated)


def test_overlong_request_id_is_replaced(monkeypatch):
    app = create_app()
    monkeypatch.setattr(health_routes, "get_db_connection", _stub_get_db_connection)
    overlong_value = "a" * 129

    with app.test_client() as client:
        response = client.get("/api/health", headers={"X-Request-ID": overlong_value})

    assert response.status_code == 200
    generated = response.headers.get("X-Request-ID")
    assert generated != overlong_value
    _assert_safe_generated_request_id(generated)


def test_request_id_with_control_character_is_replaced(monkeypatch):
    app = create_app()
    monkeypatch.setattr(health_routes, "get_db_connection", _stub_get_db_connection)
    invalid_value = "unsafe\x7frequest-id"

    with app.test_client() as client:
        response = client.get("/api/health", headers={"X-Request-ID": invalid_value})

    assert response.status_code == 200
    generated = response.headers.get("X-Request-ID")
    assert generated != invalid_value
    _assert_safe_generated_request_id(generated)


def test_request_logging_has_metadata_and_excludes_sensitive_values(monkeypatch, caplog):
    app = create_app()
    monkeypatch.setattr(health_routes, "get_db_connection", _stub_get_db_connection)
    caplog.set_level(logging.INFO)

    headers = {
        "Authorization": "Bearer do-not-log-this-token",
        "Cookie": "session=do-not-log-this-cookie",
        "X-Request-ID": "req-safe-1",
    }

    with app.test_client() as client:
        response = client.get(
            "/api/health?password=do-not-log-this-password&token=do-not-log-this-token",
            headers=headers,
        )

    assert response.status_code == 200

    request_logs = [
        record.getMessage()
        for record in caplog.records
        if "method=GET" in record.getMessage() and "path=/api/health" in record.getMessage()
    ]
    assert len(request_logs) == 1

    log_message = request_logs[0]
    assert "request_id=req-safe-1" in log_message
    assert "method=GET" in log_message
    assert "path=/api/health" in log_message
    assert "status=200" in log_message
    assert "duration_ms=" in log_message

    assert "do-not-log-this-token" not in caplog.text
    assert "do-not-log-this-cookie" not in caplog.text
    assert "do-not-log-this-password" not in caplog.text