import uuid

from app import create_app


class _StubCursor:
    def __init__(self, select_result=None):
        self.select_result = select_result
        self.executed = []
        self.fetchone_result = select_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if query.strip().upper().startswith("SELECT"):
            self.fetchone_result = self.select_result
        else:
            self.fetchone_result = None

    def fetchone(self):
        result = self.fetchone_result
        self.fetchone_result = None
        return result


class _StubConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True


def _app_with_secret(monkeypatch, **config_overrides):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key-1234567890")
    for key, value in config_overrides.items():
        monkeypatch.setenv(key, value)
    return create_app()


def test_login_success_sets_session_updates_last_login_and_returns_safe_user(monkeypatch):
    app = _app_with_secret(monkeypatch, SESSION_COOKIE_SECURE="false")
    user_id = str(uuid.uuid4())
    cursor = _StubCursor(
        select_result=(
            user_id,
            "Test User",
            "test@example.com",
            "requester",
            "active",
            "argon2$fakehash",
            True,
        )
    )
    connection = _StubConnection(cursor)

    import app.routes.auth as auth_routes

    monkeypatch.setattr(auth_routes, "get_db_connection", lambda: connection)
    monkeypatch.setattr(auth_routes, "check_password_hash", lambda hash_value, password: password == "CorrectPassword!" and hash_value == "argon2$fakehash")

    with app.test_client() as client:
        response = client.post(
            "/api/auth/login",
            json={"email": " Test@Example.com ", "password": "CorrectPassword!"},
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["data"]["user"]["id"] == user_id
        assert payload["data"]["user"]["email"] == "test@example.com"
        assert payload["data"]["user"]["role"] == "requester"
        assert payload["data"]["user"]["must_change_password"] is True
        assert "password_hash" not in payload["data"]["user"]
        assert "password_hash" not in str(payload)
        assert "CorrectPassword!" not in response.get_data(as_text=True)

        with client.session_transaction() as session:
            assert session["user_id"] == user_id

        assert connection.committed is True
        assert any("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = %s" in query for query, _ in cursor.executed)
        assert any("%s" in query for query, _ in cursor.executed)


def test_login_bad_credentials_returns_same_401_and_no_session(monkeypatch):
    app = _app_with_secret(monkeypatch)

    import app.routes.auth as auth_routes

    def _fake_get_db_connection():
        cursor = _StubCursor(select_result=None)
        return _StubConnection(cursor)

    monkeypatch.setattr(auth_routes, "get_db_connection", _fake_get_db_connection)

    with app.test_client() as client:
        unknown_response = client.post("/api/auth/login", json={"email": "missing@example.com", "password": "wrongpass"})
        assert unknown_response.status_code == 401
        assert unknown_response.get_json()["error"] == {
            "code": "INVALID_CREDENTIALS",
            "message": "Invalid email or password.",
        }
        with client.session_transaction() as session:
            assert "user_id" not in session

        incorrect_password_response = client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrongpass"})
        assert incorrect_password_response.status_code == 401
        assert incorrect_password_response.get_json()["error"] == {
            "code": "INVALID_CREDENTIALS",
            "message": "Invalid email or password.",
        }
        with client.session_transaction() as session:
            assert "user_id" not in session


def test_login_inactive_account_returns_403_and_no_session(monkeypatch):
    app = _app_with_secret(monkeypatch)
    user_id = str(uuid.uuid4())
    cursor = _StubCursor(
        select_result=(
            user_id,
            "Inactive User",
            "inactive@example.com",
            "requester",
            "inactive",
            "argon2$fakehash",
            False,
        )
    )
    connection = _StubConnection(cursor)

    import app.routes.auth as auth_routes

    monkeypatch.setattr(auth_routes, "get_db_connection", lambda: connection)
    monkeypatch.setattr(auth_routes, "check_password_hash", lambda hash_value, password: password == "CorrectPassword!" and hash_value == "argon2$fakehash")

    with app.test_client() as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "inactive@example.com", "password": "CorrectPassword!"},
        )

    assert response.status_code == 403
    assert response.get_json()["error"] == {
        "code": "ACCOUNT_INACTIVE",
        "message": "This account is inactive.",
    }
    with app.test_client() as client:
        with client.session_transaction() as session:
            assert "user_id" not in session


def test_login_validation_errors_use_reusable_patterns(monkeypatch):
    app = _app_with_secret(monkeypatch)

    with app.test_client() as client:
        response = client.post("/api/auth/login", data='{"password": "secret"}', content_type="application/json")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
        assert response.get_json()["error"]["details"]["email"] == "This field is required."

        response = client.post("/api/auth/login", json={"email": "user@example.com"})
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
        assert response.get_json()["error"]["details"]["password"] == "This field is required."

        response = client.post("/api/auth/login", data="{broken json}", content_type="application/json")
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "INVALID_JSON"


def test_me_requires_auth_and_reloads_user_from_db(monkeypatch):
    app = _app_with_secret(monkeypatch)
    user_id = str(uuid.uuid4())

    import app.routes.auth as auth_routes

    class _UserLookupConnection:
        def __init__(self, select_result):
            self.select_result = select_result
            self.cursor_instance = _StubCursor(select_result)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return self.cursor_instance

    def _lookup_for_session(_user_id):
        if _user_id == user_id:
            return _UserLookupConnection((user_id, "Active User", "active@example.com", "manager", "active", "hash", False))
        return _UserLookupConnection(None)

    monkeypatch.setattr(auth_routes, "get_db_connection", lambda: _UserLookupConnection(None))

    with app.test_client() as client:
        response = client.get("/api/auth/me")
        assert response.status_code == 401
        assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

        with client.session_transaction() as session:
            session["user_id"] = user_id

        def _db_for_session():
            return _lookup_for_session(user_id)

        monkeypatch.setattr(auth_routes, "get_db_connection", _db_for_session)
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        assert response.get_json()["data"]["user"]["email"] == "active@example.com"
        assert "password_hash" not in str(response.get_json())

        with client.session_transaction() as session:
            assert session["user_id"] == user_id


def test_logout_clears_session_idempotently(monkeypatch):
    app = _app_with_secret(monkeypatch)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = str(uuid.uuid4())

        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.get_json()["data"]["message"] == "Logged out successfully."

        with client.session_transaction() as session:
            assert "user_id" not in session

        second_response = client.post("/api/auth/logout")
        assert second_response.status_code == 200
        assert second_response.get_json()["data"]["message"] == "Logged out successfully."


def test_session_cookie_configuration_is_secure_per_environment(monkeypatch):
    app = _app_with_secret(monkeypatch, SESSION_COOKIE_SECURE="false")
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_SECURE"] is False

    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    second_app = create_app()
    assert second_app.config["SESSION_COOKIE_SECURE"] is True
