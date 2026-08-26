import pytest

from app import create_app, parse_allowed_origins
from app.routes import health as health_routes


class _StubCursor:
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return None

    def execute(self, query):
        return None

    def fetchone(self):
        return (1,)


class _StubConnection:
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return None

    def cursor(self):
        return _StubCursor()


@pytest.fixture
def healthy_app(monkeypatch):
    monkeypatch.setattr(health_routes, "get_db_connection", lambda: _StubConnection())
    return create_app()


def test_allowed_frontend_origin_on_health_request(healthy_app):
    with healthy_app.test_client() as client:
        response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"
    assert response.headers.get("X-Request-ID")
    assert response.get_json()["status"] == "healthy"


def test_unconfigured_origin_is_not_allowed(healthy_app):
    with healthy_app.test_client() as client:
        response = client.get("/api/health", headers={"Origin": "http://malicious.example"})

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") is None
    assert response.headers.get("Access-Control-Allow-Credentials") is None


def test_request_without_origin_still_works(healthy_app):
    with healthy_app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"
    assert response.headers.get("Access-Control-Allow-Origin") is None


def test_allowed_preflight_request_has_expected_policy(healthy_app):
    with healthy_app.test_client() as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type,Authorization,X-Request-ID",
            },
        )

    assert response.status_code in (200, 204)
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"
    allow_methods = response.headers.get("Access-Control-Allow-Methods", "")
    allow_headers = response.headers.get("Access-Control-Allow-Headers", "")
    assert "GET" in allow_methods
    assert "POST" in allow_methods
    assert "PATCH" in allow_methods
    assert "DELETE" in allow_methods
    assert "OPTIONS" in allow_methods
    assert "Content-Type" in allow_headers
    assert "Authorization" in allow_headers
    assert "X-Request-ID" in allow_headers


def test_unconfigured_preflight_request_is_not_granted_access(healthy_app):
    with healthy_app.test_client() as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://malicious.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,Authorization",
            },
        )

    assert response.status_code in (200, 204)
    assert response.headers.get("Access-Control-Allow-Origin") is None
    assert response.headers.get("Access-Control-Allow-Credentials") is None


def test_parse_allowed_origins_handles_csv_and_whitespace(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173")
    assert parse_allowed_origins() == ["http://localhost:5173", "http://localhost:4173"]

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", " http://localhost:5173 , http://localhost:4173 ")
    assert parse_allowed_origins() == ["http://localhost:5173", "http://localhost:4173"]


def test_parse_allowed_origins_uses_local_dev_default_when_unset(monkeypatch):
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    assert parse_allowed_origins() == ["http://localhost:5173"]
