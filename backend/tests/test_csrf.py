import logging

from flask import jsonify

from app import create_app
from conftest import csrf_headers, get_csrf_token


def test_csrf_token_endpoint_returns_session_token_and_request_id():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/api/auth/csrf")

    assert response.status_code == 200
    assert response.get_json()["data"]["csrf_token"]
    assert response.headers.get("X-Request-ID")


def test_safe_requests_do_not_require_csrf(monkeypatch):
    app = create_app()

    from app.routes import health as health_routes

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self

        def __iter__(self):
            return iter(())

        def execute(self, _query):
            return None

        def fetchone(self):
            return (1,)

    monkeypatch.setattr(health_routes, "get_db_connection", lambda: _Connection())

    with app.test_client() as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/auth/csrf").status_code == 200
        assert client.head("/api/health").status_code == 200


def test_login_without_csrf_is_rejected_before_database_access(monkeypatch):
    app = create_app()
    from app.routes import auth as auth_routes

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("login database lookup should not run")

    monkeypatch.setattr(auth_routes, "_user_lookup_by_email", fail_if_called)

    with app.test_client() as client:
        response = client.post("/api/auth/login", json={"email": "x@example.com", "password": "password"})

    assert response.status_code == 403
    assert response.get_json()["error"] == {
        "code": "CSRF_TOKEN_INVALID",
        "message": "The CSRF token is missing or invalid.",
    }
    assert response.headers.get("X-Request-ID")


def test_auth_and_admin_mutations_without_csrf_are_rejected():
    app = create_app()

    with app.test_client() as client:
        requests = [
            client.post("/api/auth/logout"),
            client.post(
                "/api/auth/change-password",
                json={"current_password": "current", "new_password": "new-password"},
            ),
            client.post(
                "/api/admin/users",
                json={"name": "User", "email": "user@example.com", "role": "requester"},
            ),
        ]

    assert [response.status_code for response in requests] == [403, 403, 403]
    assert all(response.get_json()["error"]["code"] == "CSRF_TOKEN_INVALID" for response in requests)


def test_put_patch_and_delete_require_csrf():
    app = create_app()

    @app.route("/api/_test/mutation", methods=["PUT", "PATCH", "DELETE"])
    def mutation():
        return jsonify({"ok": True})

    with app.test_client() as client:
        for method in ("put", "patch", "delete"):
            response = getattr(client, method)("/api/_test/mutation")
            assert response.status_code == 403
            assert response.get_json()["error"]["code"] == "CSRF_TOKEN_INVALID"

        token = get_csrf_token(client)
        for method in ("put", "patch", "delete"):
            response = getattr(client, method)("/api/_test/mutation", headers={"X-CSRF-Token": token})
            assert response.status_code == 200


def test_options_preflight_allows_csrf_header():
    app = create_app()

    with app.test_client() as client:
        response = client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,X-CSRF-Token",
            },
        )

    assert response.status_code in (200, 204)
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert "X-CSRF-Token" in response.headers.get("Access-Control-Allow-Headers", "")


def test_csrf_token_is_not_logged(caplog):
    app = create_app()
    caplog.set_level(logging.INFO)

    with app.test_client() as client:
        token = get_csrf_token(client)
        response = client.post("/api/auth/login", headers={"X-CSRF-Token": "definitely-invalid"}, json={})

    assert response.status_code == 403
    assert token not in caplog.text
    assert "definitely-invalid" not in caplog.text