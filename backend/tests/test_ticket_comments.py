import uuid

import psycopg
import pytest

from app import create_app
from conftest import csrf_headers


def _create_user(db_config, role, name, email):
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


def _create_ticket(db_config, requester_id, title="Sample ticket"):
    with psycopg.connect(**db_config, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tickets (title, description, setup_snapshot, requester_id)
                VALUES (
                    %s,
                    'Detailed description of the issue.',
                    '{"server_name": "lab-1", "server_ip": "10.0.0.1", "platform": "ALE", "dut": "router"}'::jsonb,
                    %s
                )
                RETURNING id;
                """,
                (title, requester_id),
            )
            row = cur.fetchone()
            assert row is not None
            return str(row[0])


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id


def _fetch_comment_row(db_config, comment_id):
    with psycopg.connect(**db_config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ticket_id, author_id, comment_text, comment_type FROM ticket_comments WHERE id = %s;",
                (comment_id,),
            )
            return cur.fetchone()


def _create_comment(db_config, ticket_id, author_id, comment_text, created_at=None):
    with psycopg.connect(**db_config, autocommit=True) as conn:
        with conn.cursor() as cur:
            if created_at is None:
                cur.execute(
                    """
                    INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
                    VALUES (%s, %s, %s, 'public')
                    RETURNING id;
                    """,
                    (ticket_id, author_id, comment_text),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type, created_at)
                    VALUES (%s, %s, %s, 'public', %s)
                    RETURNING id;
                    """,
                    (ticket_id, author_id, comment_text, created_at),
                )
            row = cur.fetchone()
            assert row is not None
            return str(row[0])


def test_requester_can_comment_on_own_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    requester_id = test_db["user_id"]
    ticket_id = _create_ticket(test_db["config"], requester_id)

    app = create_app()
    with app.test_client() as client:
        _login(client, requester_id)
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"comment": "Hello, this is my ticket."},
            headers=csrf_headers(client),
        )

    assert response.status_code == 201
    comment = response.get_json()["data"]["comment"]
    assert comment["ticket_id"] == ticket_id
    assert comment["user_id"] == requester_id
    assert comment["comment"] == "Hello, this is my ticket."
    assert comment["comment_type"] == "public"

    row = _fetch_comment_row(test_db["config"], comment["id"])
    assert row is not None
    assert row[3] == "public"


def test_requester_cannot_comment_on_another_requesters_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    other_requester_id = _create_user(
        test_db["config"], "requester", "Other Requester", "other.requester@example.com"
    )
    ticket_id = _create_ticket(test_db["config"], other_requester_id)

    app = create_app()
    with app.test_client() as client:
        _login(client, test_db["user_id"])
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"comment": "I should not be able to see this ticket."},
            headers=csrf_headers(client),
        )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TICKET_NOT_FOUND"


def test_support_engineer_can_comment_without_assignment(postgres_disposable_db):
    test_db = postgres_disposable_db
    engineer_id = _create_user(
        test_db["config"], "support_engineer", "Support Engineer", "engineer@example.com"
    )
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])

    app = create_app()
    with app.test_client() as client:
        _login(client, engineer_id)
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"comment": "Looking into this now."},
            headers=csrf_headers(client),
        )

    assert response.status_code == 201
    comment = response.get_json()["data"]["comment"]
    assert comment["user_id"] == engineer_id


def test_manager_can_comment(postgres_disposable_db):
    test_db = postgres_disposable_db
    manager_id = _create_user(test_db["config"], "manager", "Manager", "manager@example.com")
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])

    app = create_app()
    with app.test_client() as client:
        _login(client, manager_id)
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"comment": "Manager checking in."},
            headers=csrf_headers(client),
        )

    assert response.status_code == 201
    comment = response.get_json()["data"]["comment"]
    assert comment["user_id"] == manager_id


def test_admin_can_comment(postgres_disposable_db):
    test_db = postgres_disposable_db
    admin_id = _create_user(test_db["config"], "admin", "Admin", "admin@example.com")
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])

    app = create_app()
    with app.test_client() as client:
        _login(client, admin_id)
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"comment": "Admin note."},
            headers=csrf_headers(client),
        )

    assert response.status_code == 201
    comment = response.get_json()["data"]["comment"]
    assert comment["user_id"] == admin_id


def test_missing_comment_is_rejected(postgres_disposable_db):
    test_db = postgres_disposable_db
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])

    app = create_app()
    with app.test_client() as client:
        _login(client, test_db["user_id"])
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={},
            headers=csrf_headers(client),
        )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_whitespace_only_comment_is_rejected(postgres_disposable_db):
    test_db = postgres_disposable_db
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])

    app = create_app()
    with app.test_client() as client:
        _login(client, test_db["user_id"])
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"comment": "   "},
            headers=csrf_headers(client),
        )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_supplied_user_id_is_ignored(postgres_disposable_db):
    test_db = postgres_disposable_db
    other_user_id = _create_user(
        test_db["config"], "support_engineer", "Impersonation Target", "impersonated@example.com"
    )
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])

    app = create_app()
    with app.test_client() as client:
        _login(client, test_db["user_id"])
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"comment": "Trying to impersonate.", "user_id": other_user_id},
            headers=csrf_headers(client),
        )

    # Unknown field is rejected outright, so it can never be used to impersonate another user.
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_supplied_comment_type_cannot_create_internal_comment(postgres_disposable_db):
    test_db = postgres_disposable_db
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])

    app = create_app()
    with app.test_client() as client:
        _login(client, test_db["user_id"])
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"comment": "Trying to sneak an internal note.", "comment_type": "internal"},
            headers=csrf_headers(client),
        )

    # Unknown field is rejected outright, so comment_type can never be client-controlled.
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_successful_comment_row_has_public_comment_type(postgres_disposable_db):
    test_db = postgres_disposable_db
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])

    app = create_app()
    with app.test_client() as client:
        _login(client, test_db["user_id"])
        response = client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"comment": "Final check."},
            headers=csrf_headers(client),
        )

    assert response.status_code == 201
    comment_id = response.get_json()["data"]["comment"]["id"]

    row = _fetch_comment_row(test_db["config"], comment_id)
    assert row is not None
    _ticket_id_db, author_id, comment_text, comment_type = row
    assert comment_type == "public"
    assert comment_text == "Final check."
    assert author_id is not None


def test_requester_can_list_comments_on_own_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    requester_id = test_db["user_id"]
    ticket_id = _create_ticket(test_db["config"], requester_id)
    _create_comment(test_db["config"], ticket_id, requester_id, "First comment.")

    app = create_app()
    with app.test_client() as client:
        _login(client, requester_id)
        response = client.get(f"/api/tickets/{ticket_id}/comments")

    assert response.status_code == 200
    comments = response.get_json()["data"]["comments"]
    assert len(comments) == 1
    assert comments[0]["comment"] == "First comment."
    assert comments[0]["ticket_id"] == ticket_id


def test_requester_cannot_list_comments_on_another_requesters_ticket(postgres_disposable_db):
    test_db = postgres_disposable_db
    other_requester_id = _create_user(
        test_db["config"], "requester", "Other Requester", "other.requester.get@example.com"
    )
    ticket_id = _create_ticket(test_db["config"], other_requester_id)
    _create_comment(test_db["config"], ticket_id, other_requester_id, "Not visible.")

    app = create_app()
    with app.test_client() as client:
        _login(client, test_db["user_id"])
        response = client.get(f"/api/tickets/{ticket_id}/comments")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TICKET_NOT_FOUND"


def test_support_engineer_can_list_comments_without_assignment(postgres_disposable_db):
    test_db = postgres_disposable_db
    engineer_id = _create_user(
        test_db["config"], "support_engineer", "Support Engineer Get", "engineer.get@example.com"
    )
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])
    _create_comment(test_db["config"], ticket_id, test_db["user_id"], "Requester comment.")

    app = create_app()
    with app.test_client() as client:
        _login(client, engineer_id)
        response = client.get(f"/api/tickets/{ticket_id}/comments")

    assert response.status_code == 200
    comments = response.get_json()["data"]["comments"]
    assert len(comments) == 1


def test_manager_can_list_comments(postgres_disposable_db):
    test_db = postgres_disposable_db
    manager_id = _create_user(test_db["config"], "manager", "Manager Get", "manager.get@example.com")
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])
    _create_comment(test_db["config"], ticket_id, test_db["user_id"], "Manager visibility check.")

    app = create_app()
    with app.test_client() as client:
        _login(client, manager_id)
        response = client.get(f"/api/tickets/{ticket_id}/comments")

    assert response.status_code == 200
    comments = response.get_json()["data"]["comments"]
    assert len(comments) == 1


def test_admin_can_list_comments(postgres_disposable_db):
    test_db = postgres_disposable_db
    admin_id = _create_user(test_db["config"], "admin", "Admin Get", "admin.get@example.com")
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])
    _create_comment(test_db["config"], ticket_id, test_db["user_id"], "Admin visibility check.")

    app = create_app()
    with app.test_client() as client:
        _login(client, admin_id)
        response = client.get(f"/api/tickets/{ticket_id}/comments")

    assert response.status_code == 200
    comments = response.get_json()["data"]["comments"]
    assert len(comments) == 1


def test_comments_are_returned_oldest_to_newest(postgres_disposable_db):
    test_db = postgres_disposable_db
    requester_id = test_db["user_id"]
    ticket_id = _create_ticket(test_db["config"], requester_id)

    _create_comment(
        test_db["config"], ticket_id, requester_id, "Second comment.", created_at="2026-09-15 10:00:00+00"
    )
    _create_comment(
        test_db["config"], ticket_id, requester_id, "First comment.", created_at="2026-09-15 09:00:00+00"
    )
    _create_comment(
        test_db["config"], ticket_id, requester_id, "Third comment.", created_at="2026-09-15 11:00:00+00"
    )

    app = create_app()
    with app.test_client() as client:
        _login(client, requester_id)
        response = client.get(f"/api/tickets/{ticket_id}/comments")

    assert response.status_code == 200
    comments = response.get_json()["data"]["comments"]
    assert [c["comment"] for c in comments] == [
        "First comment.",
        "Second comment.",
        "Third comment.",
    ]


def test_author_information_is_returned(postgres_disposable_db):
    test_db = postgres_disposable_db
    requester_id = test_db["user_id"]
    ticket_id = _create_ticket(test_db["config"], requester_id)
    _create_comment(test_db["config"], ticket_id, requester_id, "Author check.")

    app = create_app()
    with app.test_client() as client:
        _login(client, requester_id)
        response = client.get(f"/api/tickets/{ticket_id}/comments")

    assert response.status_code == 200
    comment = response.get_json()["data"]["comments"][0]
    assert comment["author_name"] == "Integration Test User"
    assert comment["author_email"] == "integration.test@example.com"
    assert comment["user_id"] == requester_id


def test_accessible_ticket_with_no_comments_returns_empty_collection(postgres_disposable_db):
    test_db = postgres_disposable_db
    ticket_id = _create_ticket(test_db["config"], test_db["user_id"])

    app = create_app()
    with app.test_client() as client:
        _login(client, test_db["user_id"])
        response = client.get(f"/api/tickets/{ticket_id}/comments")

    assert response.status_code == 200
    assert response.get_json()["data"]["comments"] == []


def test_nonexistent_ticket_returns_404(postgres_disposable_db):
    test_db = postgres_disposable_db
    missing_ticket_id = str(uuid.uuid4())

    app = create_app()
    with app.test_client() as client:
        _login(client, test_db["user_id"])
        response = client.get(f"/api/tickets/{missing_ticket_id}/comments")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TICKET_NOT_FOUND"
