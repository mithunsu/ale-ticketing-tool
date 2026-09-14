from datetime import datetime, timezone

import psycopg
import pytest

from app import create_app
from conftest import csrf_headers


class _StubCursor:
    def __init__(self, ticket=None, tickets=None, history=None, count=None, error_on_history=None):
        self.ticket = ticket
        self.tickets = tickets if tickets is not None else []
        self.history = history if history is not None else []
        self.count = count if count is not None else len(self.tickets)
        self.error_on_history = error_on_history
        self.executed = []
        self._last_query = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        self._last_query = query
        if len(self.executed) == 2 and self.error_on_history is not None:
            raise self.error_on_history

    def fetchone(self):
        if "COUNT(*)" in self._last_query.upper():
            return (self.count,)
        return self.ticket

    def fetchall(self):
        if "TICKET_HISTORY" in self._last_query.upper():
            return self.history
        return self.tickets



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
            res_ticket = cur.fetchone()
            assert res_ticket is not None
            ticket_count = res_ticket[0]

            cur.execute("SELECT COUNT(*) FROM ticket_history WHERE action = 'TICKET_CREATED';")
            res_history = cur.fetchone()
            assert res_history is not None
            history_count = res_history[0]

    assert ticket_count == 0
    assert history_count == 0


def _sample_ticket_row(
    ticket_id="ticket-1",
    ticket_number=101,
    title="Router issue",
    requester_id="user-1",
    requester_name="Alice Requester",
    requester_email="alice@example.com",
    created_at=None,
):
    ts = created_at or datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)
    return (
        ticket_id,
        ticket_number,
        title,
        "Detailed problem description",
        "high",
        "New",
        requester_id,
        requester_name,
        requester_email,
        None,
        {"server_name": "srv1", "server_ip": "10.0.0.1", "platform": "ALE", "dut": "switch"},
        None,
        None,
        ts,
        ts,
        None,
    )


def _sample_history_row(
    history_id="h1f7b022-7772-4d2a-a92c-0e9e110d9f01",
    action="TICKET_CREATED",
    old_status=None,
    new_status="New",
    changed_by="user-1",
    actor_name="Alice Requester",
    actor_email="alice@example.com",
    created_at=None,
):
    ts = created_at or datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)
    return (
        history_id,
        action,
        old_status,
        new_status,
        changed_by,
        actor_name,
        actor_email,
        ts,
    )



def test_unauthenticated_get_tickets_is_rejected():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/api/tickets")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_requester_sees_only_own_tickets_with_display_info(monkeypatch):
    row_user1 = _sample_ticket_row(ticket_id="t-1", requester_id="user-1", requester_name="Alice", requester_email="alice@example.com")
    cursor = _StubCursor(tickets=[row_user1], count=1)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "tickets" in data
    assert len(data["tickets"]) == 1
    assert data["pagination"] == {
        "page": 1,
        "limit": 10,
        "total": 1,
        "total_pages": 1,
    }
    ticket = data["tickets"][0]
    assert ticket["id"] == "t-1"
    assert ticket["requester_id"] == "user-1"
    assert ticket["requester_name"] == "Alice"
    assert ticket["requester_email"] == "alice@example.com"
    assert ticket["title"] == "Router issue"
    assert ticket["priority"] == "High"
    assert ticket["status"] == "New"
    assert ticket["assigned_to"] is None
    assert ticket["due_date"] is None
    assert ticket["resolution"] is None
    assert ticket["closed_at"] is None

    # Verify count query and data query
    assert len(cursor.executed) == 2
    count_query, count_params = cursor.executed[0]
    assert "SELECT COUNT(*) FROM tickets WHERE requester_id = %s" in count_query
    assert count_params == ("user-1",)

    data_query, data_params = cursor.executed[1]
    assert "INNER JOIN users u ON t.requester_id = u.id" in data_query
    assert "WHERE t.requester_id = %s" in data_query
    assert "LIMIT %s OFFSET %s" in data_query
    assert data_params == ("user-1", 10, 0)


def test_requester_authorization_is_id_based_and_ignores_query_params(monkeypatch):
    cursor = _StubCursor(tickets=[], count=0)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        # Attempt to supply another user's ID via query params
        response = client.get("/api/tickets?requester_id=user-999&requester_email=other@example.com")

    assert response.status_code == 200
    count_query, count_params = cursor.executed[0]
    data_query, data_params = cursor.executed[1]
    # Backend-enforced ID must be current user's ID 'user-1'
    assert count_params == ("user-1",)
    assert data_params == ("user-1", 10, 0)
    assert "user-999" not in count_query and "user-999" not in data_query
    assert "other@example.com" not in count_query and "other@example.com" not in data_query


def test_authenticated_requester_with_no_tickets_receives_empty_list(monkeypatch):
    cursor = _StubCursor(tickets=[], count=0)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets")

    assert response.status_code == 200
    assert response.get_json() == {
        "data": {
            "tickets": [],
            "pagination": {
                "page": 1,
                "limit": 10,
                "total": 0,
                "total_pages": 0,
            },
        }
    }


@pytest.mark.parametrize("role", ["support_engineer", "manager", "admin"])
def test_privileged_roles_see_all_tickets_from_multiple_requesters(monkeypatch, role):
    row1 = _sample_ticket_row(ticket_id="t-1", requester_id="user-1", requester_name="Alice", requester_email="alice@example.com")
    row2 = _sample_ticket_row(ticket_id="t-2", requester_id="user-2", requester_name="Bob", requester_email="bob@example.com")
    cursor = _StubCursor(tickets=[row1, row2], count=2)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role=role, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets")

    assert response.status_code == 200
    data = response.get_json()["data"]
    tickets = data["tickets"]
    assert len(tickets) == 2
    assert tickets[0]["requester_id"] == "user-1"
    assert tickets[1]["requester_id"] == "user-2"
    assert data["pagination"] == {
        "page": 1,
        "limit": 10,
        "total": 2,
        "total_pages": 1,
    }

    count_query, count_params = cursor.executed[0]
    data_query, data_params = cursor.executed[1]
    assert "SELECT COUNT(*) FROM tickets;" in count_query
    assert count_params is None
    assert "INNER JOIN users u ON t.requester_id = u.id" in data_query
    assert "WHERE" not in data_query
    assert data_params == (10, 0)


def test_tickets_returned_ordered_newest_first(monkeypatch):
    t_newer = _sample_ticket_row(
        ticket_id="t-2",
        ticket_number=102,
        created_at=datetime(2026, 9, 11, 15, 0, tzinfo=timezone.utc),
    )
    t_older = _sample_ticket_row(
        ticket_id="t-1",
        ticket_number=101,
        created_at=datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc),
    )
    cursor = _StubCursor(tickets=[t_newer, t_older], count=2)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="support_engineer", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets")

    assert response.status_code == 200
    tickets = response.get_json()["data"]["tickets"]
    assert len(tickets) == 2
    assert tickets[0]["id"] == "t-2"
    assert tickets[1]["id"] == "t-1"

    data_query, _params = cursor.executed[1]
    assert "ORDER BY t.created_at DESC, t.id DESC" in data_query


def test_no_sensitive_user_fields_in_list_response(monkeypatch):
    row = _sample_ticket_row()
    cursor = _StubCursor(tickets=[row], count=1)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets")

    assert response.status_code == 200
    ticket = response.get_json()["data"]["tickets"][0]
    sensitive_keys = {
        "password_hash",
        "must_change_password",
        "sso_id",
        "last_login_at",
        "auth_provider",
    }
    for key in sensitive_keys:
        assert key not in ticket

    count_query, _params = cursor.executed[0]
    data_query, _params = cursor.executed[1]
    for key in sensitive_keys:
        assert key not in count_query
        assert key not in data_query


def test_default_pagination_parameters(monkeypatch):
    cursor = _StubCursor(tickets=[], count=0)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets")

    assert response.status_code == 200
    pagination = response.get_json()["data"]["pagination"]
    assert pagination["page"] == 1
    assert pagination["limit"] == 10
    _data_query, data_params = cursor.executed[1]
    assert data_params == ("user-1", 10, 0)


def test_explicit_valid_pagination_parameters(monkeypatch):
    cursor = _StubCursor(tickets=[], count=35)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="support_engineer", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?page=2&limit=10")

    assert response.status_code == 200
    pagination = response.get_json()["data"]["pagination"]
    assert pagination == {
        "page": 2,
        "limit": 10,
        "total": 35,
        "total_pages": 4,
    }
    _data_query, data_params = cursor.executed[1]
    assert data_params == (10, 10)


def test_pagination_returns_subset_and_metadata(monkeypatch):
    rows = [
        _sample_ticket_row(ticket_id=f"t-{i}", ticket_number=100 + i)
        for i in range(1, 6)
    ]
    cursor = _StubCursor(tickets=rows, count=12)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, role="support_engineer", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?page=3&limit=5")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data["tickets"]) == 5
    assert data["pagination"] == {
        "page": 3,
        "limit": 5,
        "total": 12,
        "total_pages": 3,
    }


@pytest.mark.parametrize(
    ("total", "limit", "expected_total_pages"),
    [
        (0, 10, 0),
        (1, 10, 1),
        (10, 10, 1),
        (11, 10, 2),
        (20, 10, 2),
        (21, 10, 3),
        (37, 10, 4),
    ],
)
def test_total_pages_calculation(monkeypatch, total, limit, expected_total_pages):
    cursor = _StubCursor(tickets=[], count=total)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, role="admin", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets?limit={limit}")

    assert response.status_code == 200
    pagination = response.get_json()["data"]["pagination"]
    assert pagination["total"] == total
    assert pagination["limit"] == limit
    assert pagination["total_pages"] == expected_total_pages


def test_limit_boundaries(monkeypatch):
    cursor = _StubCursor(tickets=[], count=0)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, role="admin", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        # limit=20 is accepted
        res20 = client.get("/api/tickets?limit=20")
        assert res20.status_code == 200
        assert res20.get_json()["data"]["pagination"]["limit"] == 20

        # limit=21 is rejected
        res21 = client.get("/api/tickets?limit=21")
        assert res21.status_code == 400
        assert "limit" in res21.get_json()["error"]["details"]


@pytest.mark.parametrize(
    ("query_string", "expected_error_field"),
    [
        ("page=0", "page"),
        ("page=-1", "page"),
        ("page=abc", "page"),
        ("page=1.5", "page"),
        ("limit=0", "limit"),
        ("limit=-1", "limit"),
        ("limit=abc", "limit"),
        ("limit=21", "limit"),
        ("limit=100", "limit"),
    ],
)
def test_invalid_pagination_parameters_rejected(monkeypatch, query_string, expected_error_field):
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester")

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets?{query_string}")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert expected_error_field in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_requester_count_query_scoped_to_requester(monkeypatch):
    cursor = _StubCursor(tickets=[], count=3)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets")

    assert response.status_code == 200
    assert response.get_json()["data"]["pagination"]["total"] == 3
    count_query, count_params = cursor.executed[0]
    assert "WHERE requester_id = %s" in count_query
    assert count_params == ("user-1",)


@pytest.mark.parametrize("role", ["support_engineer", "manager", "admin"])
def test_privileged_roles_count_all_tickets(monkeypatch, role):
    cursor = _StubCursor(tickets=[], count=10)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role=role, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets")

    assert response.status_code == 200
    assert response.get_json()["data"]["pagination"]["total"] == 10
    count_query, count_params = cursor.executed[0]
    assert "WHERE" not in count_query
    assert count_params is None


def test_requesting_valid_page_beyond_total_pages(monkeypatch):
    cursor = _StubCursor(tickets=[], count=15)
    app, _cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?page=5&limit=10")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tickets"] == []
    assert data["pagination"] == {
        "page": 5,
        "limit": 10,
        "total": 15,
        "total_pages": 2,
    }


def test_unauthenticated_get_ticket_by_id_is_rejected():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/api/tickets/c1f7b022-7772-4d2a-a92c-0e9e110d9f01")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize(
    "invalid_uuid",
    [
        "not-a-valid-uuid",
        "12345",
        "c1f7b022-7772-4d2a-a92c",
        "c1f7b022-7772-4d2a-a92c-0e9e110d9f01-extra",
    ],
)
def test_malformed_ticket_uuid_returns_400(monkeypatch, invalid_uuid):
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester")

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets/{invalid_uuid}")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert "ticket_id" in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_valid_uuid_nonexistent_ticket_returns_404(monkeypatch):
    cursor = _StubCursor(ticket=None)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets/c1f7b022-7772-4d2a-a92c-0e9e110d9f01")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TICKET_NOT_FOUND"
    assert len(cursor.executed) == 1


def test_requester_views_own_ticket_with_display_info_and_history(monkeypatch):
    ticket_id = "c1f7b022-7772-4d2a-a92c-0e9e110d9f01"
    row = _sample_ticket_row(
        ticket_id=ticket_id,
        requester_id="user-1",
        requester_name="Alice Requester",
        requester_email="alice@example.com",
    )
    h_row = _sample_history_row(
        history_id="h1f7b022-7772-4d2a-a92c-0e9e110d9f01",
        action="TICKET_CREATED",
        old_status=None,
        new_status="New",
        changed_by="user-1",
        actor_name="Alice Requester",
        actor_email="alice@example.com",
    )
    cursor = _StubCursor(ticket=row, history=[h_row])
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets/{ticket_id}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    ticket = data["ticket"]
    assert ticket["id"] == ticket_id
    assert ticket["requester_id"] == "user-1"
    assert ticket["requester_name"] == "Alice Requester"
    assert ticket["requester_email"] == "alice@example.com"
    assert ticket["title"] == "Router issue"
    assert ticket["priority"] == "High"
    assert ticket["status"] == "New"
    assert ticket["assigned_to"] is None

    history = data["history"]
    assert len(history) == 1
    assert history[0] == {
        "id": "h1f7b022-7772-4d2a-a92c-0e9e110d9f01",
        "action": "TICKET_CREATED",
        "old_status": None,
        "new_status": "New",
        "changed_by": "user-1",
        "actor_name": "Alice Requester",
        "actor_email": "alice@example.com",
        "created_at": "2026-09-11T10:00:00+00:00",
    }

    assert len(cursor.executed) == 2
    ticket_query, ticket_params = cursor.executed[0]
    assert "INNER JOIN users u ON t.requester_id = u.id" in ticket_query
    assert "WHERE t.id = %s AND t.requester_id = %s" in ticket_query
    assert ticket_params == (ticket_id, "user-1")

    history_query, history_params = cursor.executed[1]
    assert "FROM ticket_history th" in history_query
    assert "LEFT JOIN users u ON th.changed_by = u.id" in history_query
    assert "WHERE th.ticket_id = %s" in history_query
    assert history_params == (ticket_id,)


def test_requester_viewing_another_requesters_ticket_returns_404_not_403(monkeypatch):
    ticket_id = "c1f7b022-7772-4d2a-a92c-0e9e110d9f01"
    # Query scoped to requester (t.id = %s AND t.requester_id = %s) returns None
    cursor = _StubCursor(ticket=None)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets/{ticket_id}")

    assert response.status_code == 404
    assert response.status_code != 403
    assert response.get_json()["error"]["code"] == "TICKET_NOT_FOUND"


def test_history_query_not_executed_when_ticket_lookup_fails(monkeypatch):
    ticket_id = "c1f7b022-7772-4d2a-a92c-0e9e110d9f01"
    cursor = _StubCursor(ticket=None)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets/{ticket_id}")

    assert response.status_code == 404
    assert len(cursor.executed) == 1
    assert "ticket_history" not in cursor.executed[0][0].lower()


@pytest.mark.parametrize("role", ["support_engineer", "manager", "admin"])
def test_privileged_roles_can_view_any_ticket_detail(monkeypatch, role):
    ticket_id = "c1f7b022-7772-4d2a-a92c-0e9e110d9f01"
    row = _sample_ticket_row(
        ticket_id=ticket_id,
        requester_id="other-user",
        requester_name="Other User",
        requester_email="other@example.com",
    )
    cursor = _StubCursor(ticket=row, history=[])
    app, cursor, _connection = _app_with_current_user(monkeypatch, role=role, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets/{ticket_id}")

    assert response.status_code == 200
    ticket = response.get_json()["data"]["ticket"]
    assert ticket["id"] == ticket_id
    assert ticket["requester_id"] == "other-user"

    ticket_query, ticket_params = cursor.executed[0]
    assert "WHERE t.id = %s;" in ticket_query
    assert "t.requester_id = %s" not in ticket_query
    assert ticket_params == (ticket_id,)


def test_ticket_history_ordered_chronologically_asc(monkeypatch):
    ticket_id = "c1f7b022-7772-4d2a-a92c-0e9e110d9f01"
    h1 = _sample_history_row(
        history_id="h-1",
        action="TICKET_CREATED",
        created_at=datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc),
    )
    h2 = _sample_history_row(
        history_id="h-2",
        action="STATUS_CHANGED",
        old_status="New",
        new_status="Open",
        created_at=datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc),
    )
    cursor = _StubCursor(
        ticket=_sample_ticket_row(ticket_id=ticket_id),
        history=[h1, h2],
    )
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="support_engineer", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets/{ticket_id}")

    assert response.status_code == 200
    history = response.get_json()["data"]["history"]
    assert len(history) == 2
    assert history[0]["id"] == "h-1"
    assert history[1]["id"] == "h-2"

    history_query, _history_params = cursor.executed[1]
    assert "ORDER BY th.created_at ASC, th.id ASC" in history_query


def test_empty_ticket_history_returns_empty_list(monkeypatch):
    ticket_id = "c1f7b022-7772-4d2a-a92c-0e9e110d9f01"
    cursor = _StubCursor(
        ticket=_sample_ticket_row(ticket_id=ticket_id),
        history=[],
    )
    app, _cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets/{ticket_id}")

    assert response.status_code == 200
    assert response.get_json()["data"]["history"] == []


def test_no_sensitive_user_fields_in_ticket_detail_or_history(monkeypatch):
    ticket_id = "c1f7b022-7772-4d2a-a92c-0e9e110d9f01"
    cursor = _StubCursor(
        ticket=_sample_ticket_row(ticket_id=ticket_id),
        history=[_sample_history_row()],
    )
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get(f"/api/tickets/{ticket_id}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    sensitive_keys = {
        "password_hash",
        "must_change_password",
        "sso_id",
        "last_login_at",
        "auth_provider",
    }
    for key in sensitive_keys:
        assert key not in data["ticket"]
        assert key not in data["history"][0]

    for execution in cursor.executed:
        query = execution[0]
        for key in sensitive_keys:
            assert key not in query
