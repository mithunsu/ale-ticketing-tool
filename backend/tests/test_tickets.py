from datetime import datetime, timezone

import psycopg
import pytest

from app import create_app
from conftest import csrf_headers


class _StubCursor:
    def __init__(self, ticket, error_on_history=None):
        self.ticket = ticket
        self.error_on_history = error_on_history
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if len(self.executed) == 2 and self.error_on_history is not None:
            raise self.error_on_history

    def fetchone(self):
        return self.ticket


class _StubConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.rollback()
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _app_with_current_user(monkeypatch, role="requester", cursor=None):
    ticket = (
        "ticket-1",
        42,
        "Router failure",
        "Packets are being dropped.",
        "high",
        "New",
        "user-1",
        None,
        {"server_name": "lab-1", "server_ip": "10.0.0.1", "platform": "ALE", "dut": "router"},
        datetime(2026, 9, 10, tzinfo=timezone.utc),
        datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    cursor = cursor or _StubCursor(ticket)
    connection = _StubConnection(cursor)
    app = create_app()

    import app.routes.auth as auth
    import app.routes.tickets as tickets

    monkeypatch.setattr(
        auth,
        "_user_lookup_by_id",
        lambda _user_id: ("user-1", "User", "user@example.com", role, "active", "hash", False),
    )
    monkeypatch.setattr(tickets, "get_db_connection", lambda: connection)
    return app, cursor, connection


def _authenticate(client):
    with client.session_transaction() as session:
        session["user_id"] = "user-1"


def _valid_payload(**overrides):
    payload = {
        "title": " Router failure ",
        "description": " Packets are being dropped. ",
        "priority": "High",
        "setup_snapshot": {
            "server_name": " lab-1 ",
            "server_ip": " 10.0.0.1 ",
            "platform": " ALE ",
            "dut": " router ",
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("role", ["requester", "support_engineer", "manager", "admin"])
def test_active_roles_create_tickets_with_history(monkeypatch, role):
    app, cursor, connection = _app_with_current_user(monkeypatch, role=role)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/tickets", json=_valid_payload(), headers=csrf_headers(client))

    assert response.status_code == 201
    ticket = response.get_json()["data"]["ticket"]
    assert ticket["requester_id"] == "user-1"
    assert ticket["status"] == "New"
    assert ticket["assigned_to"] is None
    assert ticket["priority"] == "High"
    assert connection.committed is True
    assert len(cursor.executed) == 2
    ticket_query, ticket_params = cursor.executed[0]
    history_query, history_params = cursor.executed[1]
    assert "%s" in ticket_query
    assert "Router failure" not in ticket_query
    assert ticket_params[0] == "Router failure"
    assert "TICKET_CREATED" in history_query
    assert history_params == ("ticket-1", "user-1")


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (_valid_payload(priority="Urgent"), "priority"),
        (_valid_payload(setup_snapshot={}), "setup_snapshot"),
        (_valid_payload(requester_id="other-user"), "requester_id"),
        (_valid_payload(status="Closed"), "status"),
        (_valid_payload(assigned_to="engineer-1"), "assigned_to"),
    ],
)
def test_invalid_or_backend_controlled_input_is_rejected(monkeypatch, payload, field):
    app, cursor, _connection = _app_with_current_user(monkeypatch)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/tickets", json=payload, headers=csrf_headers(client))

    assert response.status_code == 400
    assert field in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_unauthenticated_request_is_rejected():
    app = create_app()

    with app.test_client() as client:
        response = client.post("/api/tickets", json=_valid_payload(), headers=csrf_headers(client))

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize(
    ("payload_modifier", "expected_field"),
    [
        (lambda p: p.pop("title"), "title"),
        (lambda p: p.update({"title": ""}), "title"),
        (lambda p: p.update({"title": "   "}), "title"),
        (lambda p: p.pop("description"), "description"),
        (lambda p: p.update({"description": ""}), "description"),
        (lambda p: p.update({"description": "   "}), "description"),
        (lambda p: p.pop("priority"), "priority"),
        (lambda p: p.update({"priority": ""}), "priority"),
        (lambda p: p.pop("setup_snapshot"), "setup_snapshot"),
        (lambda p: p.update({"setup_snapshot": "not-a-dict"}), "setup_snapshot"),
        (lambda p: p.update({"setup_snapshot": []}), "setup_snapshot"),
    ],
)
def test_required_top_level_fields_are_enforced(monkeypatch, payload_modifier, expected_field):
    app, cursor, _connection = _app_with_current_user(monkeypatch)
    payload = _valid_payload()
    payload_modifier(payload)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/tickets", json=payload, headers=csrf_headers(client))

    assert response.status_code == 400
    assert expected_field in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_ticket_history_failure_rolls_back_ticket(monkeypatch):
    cursor = _StubCursor(
        ("ticket-1",), error_on_history=psycopg.OperationalError("database unavailable")
    )
    app, _cursor, connection = _app_with_current_user(monkeypatch, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.post("/api/tickets", json=_valid_payload(), headers=csrf_headers(client))

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert connection.committed is False
    assert connection.rolled_back is True


def test_real_postgres_rollback_when_history_insert_fails(postgres_disposable_db):
    test_db = postgres_disposable_db
    user_id = test_db["user_id"]
    db_config = test_db["config"]

    # Install test-only trigger on disposable DB rejecting TICKET_CREATED
    trigger_sql = """
    CREATE OR REPLACE FUNCTION _test_fail_ticket_created()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.action = 'TICKET_CREATED' THEN
            RAISE EXCEPTION 'Simulated history insert failure for rollback verification';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER _test_reject_ticket_created_trigger
    BEFORE INSERT ON ticket_history
    FOR EACH ROW
    EXECUTE FUNCTION _test_fail_ticket_created();
    """
    with psycopg.connect(**db_config, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(trigger_sql)

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = user_id

        payload = _valid_payload(title="Rollback Test Ticket")
        response = client.post("/api/tickets", json=payload, headers=csrf_headers(client))

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    # Query PostgreSQL directly to assert zero persisted tickets or history rows
    with psycopg.connect(**db_config) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tickets WHERE title = %s;", ("Rollback Test Ticket",))
            ticket_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ticket_history WHERE action = 'TICKET_CREATED';")
            history_count = cur.fetchone()[0]

    assert ticket_count == 0
    assert history_count == 0
