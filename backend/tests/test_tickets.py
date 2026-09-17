from datetime import datetime, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app import create_app
from conftest import csrf_headers


class _StubCursor:
    def __init__(
        self,
        ticket=None,
        tickets=None,
        history=None,
        count=None,
        error_on_history=None,
        fetchone_results=None,
    ):
        self.ticket = ticket
        self.tickets = tickets if tickets is not None else []
        self.history = history if history is not None else []
        self.count = count if count is not None else len(self.tickets)
        self.error_on_history = error_on_history
        self.fetchone_results = list(fetchone_results or [])
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
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
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


def test_status_not_closed_is_accepted(monkeypatch):
    row = _sample_ticket_row()
    cursor = _StubCursor(tickets=[row], count=1)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="admin", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?status_not=Closed")

    assert response.status_code == 200
    assert response.get_json()["data"]["pagination"]["total"] == 1


def test_status_not_added_to_count_and_select_queries(monkeypatch):
    cursor = _StubCursor(tickets=[], count=0)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="admin", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?status_not=Closed")

    assert response.status_code == 200
    count_query, count_params = cursor.executed[0]
    data_query, data_params = cursor.executed[1]
    assert "status <> %s" in count_query
    assert "t.status <> %s" in data_query
    assert count_params == ("Closed",)
    assert data_params == ("Closed", 10, 0)


def test_status_not_is_bound_parameter_not_interpolated(monkeypatch):
    cursor = _StubCursor(tickets=[], count=0)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="admin", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?status_not=Closed")

    assert response.status_code == 200
    count_query, count_params = cursor.executed[0]
    data_query, data_params = cursor.executed[1]
    assert "Closed" not in count_query and "Closed" not in data_query
    assert "Closed" in count_params and "Closed" in data_params


def test_requester_visibility_combines_with_status_not(monkeypatch):
    cursor = _StubCursor(tickets=[], count=0)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="requester", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?status_not=Closed")

    assert response.status_code == 200
    count_query, count_params = cursor.executed[0]
    data_query, data_params = cursor.executed[1]
    assert "WHERE requester_id = %s AND status <> %s" in count_query
    assert count_params == ("user-1", "Closed")
    assert "WHERE t.requester_id = %s AND t.status <> %s" in data_query
    assert data_params == ("user-1", "Closed", 10, 0)


@pytest.mark.parametrize("role", ["support_engineer", "manager", "admin"])
def test_privileged_roles_combine_with_status_not(monkeypatch, role):
    cursor = _StubCursor(tickets=[], count=0)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role=role, cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?status_not=Closed")

    assert response.status_code == 200
    count_query, count_params = cursor.executed[0]
    data_query, data_params = cursor.executed[1]
    assert "requester_id" not in count_query
    assert count_params == ("Closed",)
    assert "WHERE t.requester_id" not in data_query
    assert data_params == ("Closed", 10, 0)


def test_invalid_status_not_returns_400(monkeypatch):
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="admin")

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?status_not=NotAStatus")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert "status_not" in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_status_not_absent_preserves_existing_query_behavior(monkeypatch):
    cursor = _StubCursor(tickets=[], count=0)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="admin", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets")

    assert response.status_code == 200
    count_query, count_params = cursor.executed[0]
    data_query, data_params = cursor.executed[1]
    assert count_query == "SELECT COUNT(*) FROM tickets;"
    assert count_params is None
    assert "WHERE" not in data_query
    assert data_params == (10, 0)


def test_status_not_with_pagination_parameters(monkeypatch):
    cursor = _StubCursor(tickets=[], count=35)
    app, cursor, _connection = _app_with_current_user(monkeypatch, role="admin", cursor=cursor)

    with app.test_client() as client:
        _authenticate(client)
        response = client.get("/api/tickets?page=2&limit=10&status_not=Closed")

    assert response.status_code == 200
    pagination = response.get_json()["data"]["pagination"]
    assert pagination == {"page": 2, "limit": 10, "total": 35, "total_pages": 4}
    _count_query, count_params = cursor.executed[0]
    _data_query, data_params = cursor.executed[1]
    assert count_params == ("Closed",)
    assert data_params == ("Closed", 10, 10)


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


TICKET_ID = "c1f7b022-7772-4d2a-a92c-0e9e110d9f01"
CURRENT_USER_ID = "d2f7b022-7772-4d2a-a92c-0e9e110d9f01"
OTHER_USER_ID = "e3f7b022-7772-4d2a-a92c-0e9e110d9f01"
STATUS_TRANSITIONS = {
    ("New", "Open"),
    ("Open", "In Progress"),
    ("In Progress", "Resolved"),
    ("Resolved", "In Progress"),
}


def _status_ticket(status="New", assigned_to=None, updated_at=None, closed_at=None):
    return (
        TICKET_ID,
        status,
        assigned_to,
        updated_at or datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
        closed_at,
    )


def _status_history_row(ticket_id=TICKET_ID, old_status="New", new_status="Open", changed_by=CURRENT_USER_ID):
    return (
        "history-1",
        "STATUS_CHANGED",
        old_status,
        new_status,
        changed_by,
        "Actor",
        "actor@example.com",
        datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc),
    )


def _status_user(role="requester", user_id=CURRENT_USER_ID):
    return (user_id, "Actor", "actor@example.com", role, "active", "hash", False)


def _assignment_ticket(assigned_to=None, updated_at=None):
    return (
        TICKET_ID,
        assigned_to,
        updated_at or datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
    )


def _app_with_assignment_user(monkeypatch, role, cursor):
    app, cursor, connection = _app_with_current_user(monkeypatch, role=role, cursor=cursor)
    import app.routes.auth as auth

    monkeypatch.setattr(
        auth,
        "_user_lookup_by_id",
        lambda _user_id: (CURRENT_USER_ID, "Actor", "actor@example.com", role, "active", "hash", False),
    )
    return app, cursor, connection


def _authenticate_assignment_user(client):
    with client.session_transaction() as session:
        session["user_id"] = CURRENT_USER_ID


def _assignment_headers(client):
    return csrf_headers(client)


def test_unauthenticated_user_cannot_update_status():
    app = create_app()

    with app.test_client() as client:
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": "Open"},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_requester_cannot_perform_other_status_transitions(monkeypatch):
    cursor = _StubCursor(fetchone_results=[_status_ticket(status="New")])
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "requester", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": "Open"},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 403
    # requester's only permitted transition is Closed -> In Progress, so the ownership SELECT runs but nothing is mutated
    assert len(cursor.executed) == 1
    assert "AND requester_id = %s" in cursor.executed[0][0]


@pytest.mark.parametrize("ticket_id", ["invalid", "123", "c1f7b022-7772-4d2a-a92c"])
def test_malformed_status_ticket_id_is_rejected(monkeypatch, ticket_id):
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "manager", _StubCursor())

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{ticket_id}/status",
            json={"status": "Open"},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 400
    assert "ticket_id" in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_nonexistent_ticket_status_returns_404(monkeypatch):
    cursor = _StubCursor(fetchone_results=[None])
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "manager", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": "Open"},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TICKET_NOT_FOUND"
    assert len(cursor.executed) == 1


@pytest.mark.parametrize("body", [{}, {"status": None}, {"status": 42}, {"status": "Cancelled"}, {"status": "invalid"}, {"status": "Open", "extra": True}])
def test_invalid_status_request_body_is_rejected(monkeypatch, body):
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "manager", _StubCursor())

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json=body,
            headers=_assignment_headers(client),
        )

    assert response.status_code == 400
    details = response.get_json()["error"]["details"]
    assert "status" in details or "extra" in details
    assert cursor.executed == []


@pytest.mark.parametrize(("current_status", "target_status"), [("New", "Open"), ("Open", "In Progress"), ("In Progress", "Resolved"), ("Resolved", "In Progress")])
def test_allowed_status_transitions_succeed(monkeypatch, current_status, target_status):
    current_updated_at = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    cursor = _StubCursor(
        fetchone_results=[
            _status_ticket(status=current_status, assigned_to=CURRENT_USER_ID, updated_at=current_updated_at),
            (TICKET_ID, target_status, CURRENT_USER_ID, updated_at, None),
        ]
    )
    app, cursor, connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": target_status},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["ticket"]["status"] == target_status
    assert connection.committed is True
    assert len(cursor.executed) == 3
    assert "UPDATE tickets" in cursor.executed[1][0]
    assert "WHERE id = %s AND status = %s" in cursor.executed[1][0]
    assert cursor.executed[1][1] == (target_status, TICKET_ID, current_status, CURRENT_USER_ID)
    assert "INSERT INTO ticket_history" in cursor.executed[2][0]


@pytest.mark.parametrize(("current_status", "target_status"), [("New", "In Progress"), ("New", "Resolved"), ("Open", "Resolved"), ("Open", "New"), ("In Progress", "Open"), ("Resolved", "New"), ("Resolved", "Open")])
def test_invalid_status_transitions_are_rejected(monkeypatch, current_status, target_status):
    cursor = _StubCursor(fetchone_results=[_status_ticket(status=current_status, assigned_to=CURRENT_USER_ID)])
    app, cursor, connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": target_status},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 400
    assert "status" in response.get_json()["error"]["details"]
    assert connection.committed is False
    assert cursor.executed == [
        (
            "SELECT id, status, assigned_to, updated_at, closed_at FROM tickets WHERE id = %s;",
            (TICKET_ID,),
        )
    ]


def test_same_status_is_idempotent_without_update_or_history(monkeypatch):
    current_updated_at = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    cursor = _StubCursor(fetchone_results=[_status_ticket(status="In Progress", assigned_to=CURRENT_USER_ID, updated_at=current_updated_at)])
    app, cursor, connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": "In Progress"},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["ticket"] == {
        "id": TICKET_ID,
        "status": "In Progress",
        "assigned_to": CURRENT_USER_ID,
        "updated_at": current_updated_at.isoformat(),
        "closed_at": None,
    }
    assert connection.committed is False
    assert cursor.executed == [
        ("SELECT id, status, assigned_to, updated_at, closed_at FROM tickets WHERE id = %s;", (TICKET_ID,))
    ]


@pytest.mark.parametrize("role", ["support_engineer", "manager", "admin"])
def test_privileged_roles_can_change_status(monkeypatch, role):
    current_updated_at = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    cursor = _StubCursor(
        fetchone_results=[
            _status_ticket(status="New", assigned_to=CURRENT_USER_ID if role == "support_engineer" else None, updated_at=current_updated_at),
            (TICKET_ID, "Open", (CURRENT_USER_ID if role == "support_engineer" else None), updated_at, None),
        ]
    )
    app, cursor, connection = _app_with_assignment_user(monkeypatch, role, cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": "Open"},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["ticket"]["status"] == "Open"
    assert connection.committed is True
    assert "INSERT INTO ticket_history" in cursor.executed[-1][0]


def test_support_engineer_cannot_change_unassigned_or_other_users_ticket(monkeypatch):
    cursor = _StubCursor(
        fetchone_results=[
            _status_ticket(status="New", assigned_to=None),
            _status_ticket(status="New", assigned_to=OTHER_USER_ID),
        ]
    )
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)

        unassigned = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": "Open"},
            headers=_assignment_headers(client),
        )
        other_user = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": "Open"},
            headers=_assignment_headers(client),
        )

    assert unassigned.status_code == 403
    assert other_user.status_code == 403
    assert len(cursor.executed) == 2


def test_concurrent_status_change_returns_conflict_and_no_history(monkeypatch):
    current_updated_at = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    cursor = _StubCursor(
        fetchone_results=[
            _status_ticket(status="New", assigned_to=CURRENT_USER_ID, updated_at=current_updated_at),
            None,
            _status_ticket(status="Open", assigned_to=CURRENT_USER_ID, updated_at=current_updated_at),
        ]
    )
    app, cursor, connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/status",
            json={"status": "Open"},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 409
    assert connection.committed is False
    assert len(cursor.executed) >= 3
    assert all("INSERT INTO ticket_history" not in query.lower() for query, _ in cursor.executed)


def test_status_history_insert_rollback_reverts_status_in_real_postgres(postgres_disposable_db):
    test_db = postgres_disposable_db
    user_id = test_db["user_id"]
    db_config = test_db["config"]

    with psycopg.connect(**db_config, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (name, email, role, department, status, password_hash, must_change_password) VALUES (%s, %s, %s, %s, 'active', 'hash', false) RETURNING id;",
                ("Engineer", "engineer@example.com", "support_engineer", "Ops"),
            )
            engineer_id = str(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO tickets (title, description, setup_snapshot, requester_id, status, assigned_to) VALUES (%s, %s, %s, %s, 'New', %s) RETURNING id;",
                (
                    "Status rollback test",
                    "Description",
                    Jsonb({"server_name": "lab-1", "server_ip": "10.0.0.1", "platform": "ALE", "dut": "router"}),
                    user_id,
                    engineer_id,
                ),
            )
            ticket_id = str(cur.fetchone()[0])

    trigger_sql = """
    CREATE OR REPLACE FUNCTION _test_fail_status_history()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.action = 'STATUS_CHANGED' THEN
            RAISE EXCEPTION 'Simulated status history insert failure';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER _test_reject_status_history_trigger
    BEFORE INSERT ON ticket_history
    FOR EACH ROW
    EXECUTE FUNCTION _test_fail_status_history();
    """
    with psycopg.connect(**db_config, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(trigger_sql)

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = engineer_id

        response = client.patch(
            f"/api/tickets/{ticket_id}/status",
            json={"status": "Open"},
            headers=csrf_headers(client),
        )

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    with psycopg.connect(**db_config) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM tickets WHERE id = %s;", (ticket_id,))
            assert cur.fetchone()[0] == "New"
            cur.execute("SELECT COUNT(*) FROM ticket_history WHERE ticket_id = %s AND action = 'STATUS_CHANGED';", (ticket_id,))
            assert cur.fetchone()[0] == 0


def _create_status_user(db_config, role, name, email):
    with psycopg.connect(**db_config, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, role, department, status, password_hash, must_change_password)
                VALUES (%s, %s, %s, 'QA', 'active', 'placeholder_hash', false)
                RETURNING id;
                """,
                (name, email, role),
            )
            row = cur.fetchone()
            assert row is not None
            return str(row[0])


def _create_status_ticket(db_config, requester_id, status="New", assigned_to=None, resolution=None):
    closed_at_clause = "CURRENT_TIMESTAMP" if status == "Closed" else "NULL"
    with psycopg.connect(**db_config, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO tickets (
                    title, description, setup_snapshot, requester_id, status, assigned_to, resolution, closed_at
                )
                VALUES (
                    'Close/reopen test ticket',
                    'Detailed description of the issue.',
                    '{{"server_name": "lab-1", "server_ip": "10.0.0.1", "platform": "ALE", "dut": "router"}}'::jsonb,
                    %s, %s, %s, %s, {closed_at_clause}
                )
                RETURNING id;
                """,
                (requester_id, status, assigned_to, resolution),
            )
            row = cur.fetchone()
            assert row is not None
            return str(row[0])


def _fetch_status_ticket_row(db_config, ticket_id):
    with psycopg.connect(**db_config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, closed_at FROM tickets WHERE id = %s;",
                (ticket_id,),
            )
            return cur.fetchone()


def _count_status_history(db_config, ticket_id, old_status, new_status):
    with psycopg.connect(**db_config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM ticket_history
                WHERE ticket_id = %s AND action = 'STATUS_CHANGED' AND old_status = %s AND new_status = %s;
                """,
                (ticket_id, old_status, new_status),
            )
            row = cur.fetchone()
            assert row is not None
            return row[0]


def test_assigned_support_engineer_can_close_resolved_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    engineer_id = _create_status_user(test_db["config"], "support_engineer", "Close Engineer", "close.engineer@example.com")
    ticket_id = _create_status_ticket(
        test_db["config"], test_db["user_id"], status="Resolved", assigned_to=engineer_id, resolution="Fixed the issue."
    )

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = engineer_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "Closed"}, headers=csrf_headers(client)
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["ticket"]["status"] == "Closed"

    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "Closed"
    assert closed_at is not None
    assert _count_status_history(test_db["config"], ticket_id, "Resolved", "Closed") == 1


def test_unassigned_support_engineer_cannot_close_resolved_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    other_engineer_id = _create_status_user(test_db["config"], "support_engineer", "Owner Engineer", "owner.engineer@example.com")
    outside_engineer_id = _create_status_user(test_db["config"], "support_engineer", "Outside Engineer", "outside.engineer@example.com")
    ticket_id = _create_status_ticket(
        test_db["config"], test_db["user_id"], status="Resolved", assigned_to=other_engineer_id, resolution="Fixed the issue."
    )

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = outside_engineer_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "Closed"}, headers=csrf_headers(client)
        )

    assert response.status_code == 403

    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "Resolved"
    assert closed_at is None


def test_manager_can_close_resolved_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    manager_id = _create_status_user(test_db["config"], "manager", "Close Manager", "close.manager@example.com")
    ticket_id = _create_status_ticket(test_db["config"], test_db["user_id"], status="Resolved", resolution="Fixed the issue.")

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = manager_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "Closed"}, headers=csrf_headers(client)
        )

    assert response.status_code == 200
    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "Closed"
    assert closed_at is not None


def test_admin_can_close_resolved_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    admin_id = _create_status_user(test_db["config"], "admin", "Close Admin", "close.admin@example.com")
    ticket_id = _create_status_ticket(test_db["config"], test_db["user_id"], status="Resolved", resolution="Fixed the issue.")

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "Closed"}, headers=csrf_headers(client)
        )

    assert response.status_code == 200
    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "Closed"
    assert closed_at is not None


def test_requester_cannot_close_resolved_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    requester_id = test_db["user_id"]
    ticket_id = _create_status_ticket(test_db["config"], requester_id, status="Resolved", resolution="Fixed the issue.")

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = requester_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "Closed"}, headers=csrf_headers(client)
        )

    assert response.status_code == 403
    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "Resolved"
    assert closed_at is None


def test_requester_can_reopen_own_closed_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    requester_id = test_db["user_id"]
    ticket_id = _create_status_ticket(test_db["config"], requester_id, status="Closed", resolution="Fixed the issue.")

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = requester_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "In Progress"}, headers=csrf_headers(client)
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["ticket"]["status"] == "In Progress"

    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "In Progress"
    assert closed_at is None
    assert _count_status_history(test_db["config"], ticket_id, "Closed", "In Progress") == 1


def test_requester_cannot_reopen_another_requesters_closed_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    other_requester_id = _create_status_user(test_db["config"], "requester", "Other Requester Close", "other.requester.close@example.com")
    ticket_id = _create_status_ticket(test_db["config"], other_requester_id, status="Closed", resolution="Fixed the issue.")

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = test_db["user_id"]
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "In Progress"}, headers=csrf_headers(client)
        )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TICKET_NOT_FOUND"

    status, _closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "Closed"


def test_assigned_support_engineer_can_reopen_closed_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    engineer_id = _create_status_user(test_db["config"], "support_engineer", "Reopen Engineer", "reopen.engineer@example.com")
    ticket_id = _create_status_ticket(
        test_db["config"], test_db["user_id"], status="Closed", assigned_to=engineer_id, resolution="Fixed the issue."
    )

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = engineer_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "In Progress"}, headers=csrf_headers(client)
        )

    assert response.status_code == 200
    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "In Progress"
    assert closed_at is None


def test_unassigned_support_engineer_cannot_reopen_closed_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    owner_engineer_id = _create_status_user(test_db["config"], "support_engineer", "Owner Engineer Reopen", "owner.engineer.reopen@example.com")
    outside_engineer_id = _create_status_user(test_db["config"], "support_engineer", "Outside Engineer Reopen", "outside.engineer.reopen@example.com")
    ticket_id = _create_status_ticket(
        test_db["config"], test_db["user_id"], status="Closed", assigned_to=owner_engineer_id, resolution="Fixed the issue."
    )

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = outside_engineer_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "In Progress"}, headers=csrf_headers(client)
        )

    assert response.status_code == 403
    status, _closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "Closed"


def test_manager_can_reopen_closed_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    manager_id = _create_status_user(test_db["config"], "manager", "Reopen Manager", "reopen.manager@example.com")
    ticket_id = _create_status_ticket(test_db["config"], test_db["user_id"], status="Closed", resolution="Fixed the issue.")

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = manager_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "In Progress"}, headers=csrf_headers(client)
        )

    assert response.status_code == 200
    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "In Progress"
    assert closed_at is None


def test_admin_can_reopen_closed_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    admin_id = _create_status_user(test_db["config"], "admin", "Reopen Admin", "reopen.admin@example.com")
    ticket_id = _create_status_ticket(test_db["config"], test_db["user_id"], status="Closed", resolution="Fixed the issue.")

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = admin_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "In Progress"}, headers=csrf_headers(client)
        )

    assert response.status_code == 200
    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "In Progress"
    assert closed_at is None
    assert _count_status_history(test_db["config"], ticket_id, "Closed", "In Progress") == 1


def test_reopen_history_insert_rollback_reverts_status_and_closed_at(postgres_disposable_db):
    test_db = postgres_disposable_db
    requester_id = test_db["user_id"]
    ticket_id = _create_status_ticket(test_db["config"], requester_id, status="Closed", resolution="Fixed the issue.")

    trigger_sql = """
    CREATE OR REPLACE FUNCTION _test_fail_reopen_history()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.action = 'STATUS_CHANGED' AND NEW.old_status = 'Closed' THEN
            RAISE EXCEPTION 'Simulated reopen history insert failure';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER _test_reject_reopen_history_trigger
    BEFORE INSERT ON ticket_history
    FOR EACH ROW
    EXECUTE FUNCTION _test_fail_reopen_history();
    """
    with psycopg.connect(**test_db["config"], autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(trigger_sql)

    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = requester_id
        response = client.patch(
            f"/api/tickets/{ticket_id}/status", json={"status": "In Progress"}, headers=csrf_headers(client)
        )

    assert response.status_code == 500
    status, closed_at = _fetch_status_ticket_row(test_db["config"], ticket_id)
    assert status == "Closed"
    assert closed_at is not None


# assignment tests follow below


@pytest.mark.parametrize("ticket_id", ["invalid", "123", "c1f7b022-7772-4d2a-a92c"])
def test_malformed_assignment_ticket_id_is_rejected(monkeypatch, ticket_id):
    cursor = _StubCursor()
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "manager", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{ticket_id}/assignment",
            json={"assigned_to": OTHER_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 400
    assert "ticket_id" in response.get_json()["error"]["details"]
    assert cursor.executed == []


@pytest.mark.parametrize("body", [{}, {"assigned_to": "invalid"}, {"assigned_to": 42}])
def test_invalid_assignment_request_body_is_rejected(monkeypatch, body):
    cursor = _StubCursor()
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "manager", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json=body,
            headers=_assignment_headers(client),
        )

    assert response.status_code == 400
    assert "assigned_to" in response.get_json()["error"]["details"]
    assert cursor.executed == []


def test_nonexistent_ticket_assignment_returns_404(monkeypatch):
    cursor = _StubCursor(fetchone_results=[None])
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "manager", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": OTHER_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TICKET_NOT_FOUND"
    assert len(cursor.executed) == 1


def test_support_engineer_can_self_assign_unassigned_ticket(monkeypatch):
    updated_at = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    cursor = _StubCursor(
        fetchone_results=[
            _assignment_ticket(),
            (CURRENT_USER_ID, "support_engineer", "active"),
            _assignment_ticket(CURRENT_USER_ID, updated_at),
        ]
    )
    app, cursor, connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": CURRENT_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["ticket"] == {
        "id": TICKET_ID,
        "assigned_to": CURRENT_USER_ID,
        "updated_at": updated_at.isoformat(),
    }
    assert connection.committed is True
    assert len(cursor.executed) == 3
    update_query, update_params = cursor.executed[-1]
    assert "UPDATE tickets" in update_query
    assert "WHERE id = %s AND assigned_to IS NULL" in update_query
    assert update_params == (CURRENT_USER_ID, TICKET_ID)
    assert all("ticket_history" not in query.lower() for query, _ in cursor.executed)


def test_support_engineer_cannot_overwrite_concurrent_assignment(monkeypatch):
    other_updated_at = datetime(2026, 9, 14, 11, 5, tzinfo=timezone.utc)
    cursor = _StubCursor(
        fetchone_results=[
            _assignment_ticket(),
            (CURRENT_USER_ID, "support_engineer", "active"),
            None,
            _assignment_ticket(OTHER_USER_ID, other_updated_at),
        ]
    )
    app, cursor, connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": CURRENT_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 403
    assert connection.committed is False
    assert len(cursor.executed) == 4
    conditional_update_query, conditional_update_params = cursor.executed[2]
    reload_query, reload_params = cursor.executed[3]
    assert "WHERE id = %s AND assigned_to IS NULL" in conditional_update_query
    assert conditional_update_params == (CURRENT_USER_ID, TICKET_ID)
    assert "SELECT id, assigned_to, updated_at FROM tickets WHERE id = %s" in reload_query
    assert reload_params == (TICKET_ID,)
    assert all("ticket_history" not in query.lower() for query, _ in cursor.executed)


def test_concurrent_self_assignment_is_idempotent(monkeypatch):
    current_updated_at = datetime(2026, 9, 14, 11, 5, tzinfo=timezone.utc)
    cursor = _StubCursor(
        fetchone_results=[
            _assignment_ticket(),
            (CURRENT_USER_ID, "support_engineer", "active"),
            None,
            _assignment_ticket(CURRENT_USER_ID, current_updated_at),
        ]
    )
    app, cursor, connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": CURRENT_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["ticket"]["updated_at"] == current_updated_at.isoformat()
    assert connection.committed is False
    assert len(cursor.executed) == 4
    assert all("ticket_history" not in query.lower() for query, _ in cursor.executed)


@pytest.mark.parametrize("target_role", ["support_engineer", "manager"])
def test_support_engineer_cannot_assign_another_user(monkeypatch, target_role):
    cursor = _StubCursor()
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": OTHER_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 403
    assert cursor.executed == []


def test_support_engineer_cannot_unassign_or_take_over(monkeypatch):
    cursor = _StubCursor(fetchone_results=[_assignment_ticket(OTHER_USER_ID)])
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        unassign_response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": None},
            headers=_assignment_headers(client),
        )
        take_over_response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": CURRENT_USER_ID},
            headers=_assignment_headers(client),
        )

    assert unassign_response.status_code == 403
    assert take_over_response.status_code == 403
    assert len(cursor.executed) == 1


def test_same_assignment_is_idempotent_without_update(monkeypatch):
    original_updated_at = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    cursor = _StubCursor(fetchone_results=[_assignment_ticket(CURRENT_USER_ID, original_updated_at)])
    app, cursor, connection = _app_with_assignment_user(monkeypatch, "support_engineer", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": CURRENT_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["ticket"]["updated_at"] == original_updated_at.isoformat()
    assert connection.committed is False
    assert len(cursor.executed) == 1


@pytest.mark.parametrize("actor_role", ["manager", "admin"])
@pytest.mark.parametrize("target_role", ["support_engineer", "manager"])
def test_manager_and_admin_can_assign_active_eligible_users(monkeypatch, actor_role, target_role):
    updated_at = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    cursor = _StubCursor(
        fetchone_results=[
            _assignment_ticket(),
            (OTHER_USER_ID, target_role, "active"),
            _assignment_ticket(OTHER_USER_ID, updated_at),
        ]
    )
    app, cursor, connection = _app_with_assignment_user(monkeypatch, actor_role, cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": OTHER_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["ticket"]["assigned_to"] == OTHER_USER_ID
    assert connection.committed is True
    assert len(cursor.executed) == 3
    update_query, update_params = cursor.executed[-1]
    assert "UPDATE tickets" in update_query
    assert "assigned_to IS NULL" not in update_query
    assert update_params == (OTHER_USER_ID, TICKET_ID)


@pytest.mark.parametrize("actor_role", ["manager", "admin"])
def test_manager_and_admin_can_self_assign_and_unassign(monkeypatch, actor_role):
    updated_at = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    cursor = _StubCursor(
        fetchone_results=[
            _assignment_ticket(),
            (CURRENT_USER_ID, actor_role, "active"),
            _assignment_ticket(CURRENT_USER_ID, updated_at),
            _assignment_ticket(CURRENT_USER_ID, updated_at),
            _assignment_ticket(None, updated_at),
        ]
    )
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, actor_role, cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        self_assign = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": CURRENT_USER_ID},
            headers=_assignment_headers(client),
        )
        unassign = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": None},
            headers=_assignment_headers(client),
        )

    assert self_assign.status_code == 200
    assert unassign.status_code == 200
    assert unassign.get_json()["data"]["ticket"]["assigned_to"] is None


def test_admin_cannot_assign_another_admin(monkeypatch):
    cursor = _StubCursor(
        fetchone_results=[_assignment_ticket(), (OTHER_USER_ID, "admin", "active")]
    )
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "admin", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": OTHER_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 400
    assert "assigned_to" in response.get_json()["error"]["details"]
    assert len(cursor.executed) == 2


@pytest.mark.parametrize("target_role,target_status", [("requester", "active"), ("manager", "inactive")])
def test_manager_cannot_assign_ineligible_user(monkeypatch, target_role, target_status):
    cursor = _StubCursor(
        fetchone_results=[_assignment_ticket(), (OTHER_USER_ID, target_role, target_status)]
    )
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "manager", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": OTHER_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 400
    assert len(cursor.executed) == 2


def test_manager_cannot_assign_nonexistent_user(monkeypatch):
    cursor = _StubCursor(fetchone_results=[_assignment_ticket(), None])
    app, cursor, _connection = _app_with_assignment_user(monkeypatch, "manager", cursor)

    with app.test_client() as client:
        _authenticate_assignment_user(client)
        response = client.patch(
            f"/api/tickets/{TICKET_ID}/assignment",
            json={"assigned_to": OTHER_USER_ID},
            headers=_assignment_headers(client),
        )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "ASSIGNEE_NOT_FOUND"
    assert len(cursor.executed) == 2
