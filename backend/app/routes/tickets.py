import psycopg
from flask import Blueprint, current_app, g, request
from psycopg.types.json import Jsonb

from app.db import get_db_connection
from app.responses import error_response, success_response, validation_error_response
from app.routes.auth import require_auth
from app.validation import parse_json_request, validate_object


tickets_bp = Blueprint("tickets", __name__)

ALLOWED_ROLES = ("requester", "support_engineer", "manager", "admin")
PRIORITY_VALUES = ("Low", "Medium", "High", "Critical")
PRIORITY_TO_DATABASE_VALUE = {priority: priority.lower() for priority in PRIORITY_VALUES}
SETUP_SNAPSHOT_SCHEMA = {
    "server_name": {"required": True, "type": str, "max_length": 255},
    "server_ip": {"required": True, "type": str, "max_length": 255},
    "platform": {"required": True, "type": str, "max_length": 255},
    "dut": {"required": True, "type": str, "max_length": 255},
    "pal_server": {"type": str, "max_length": 255},
    "emp": {"type": str, "max_length": 255},
    "console": {"type": str, "max_length": 255},
    "console_port": {"type": str, "max_length": 20},
    "rps": {"type": str, "max_length": 255},
    "rps_port": {"type": str, "max_length": 20},
    "gateway": {"type": str, "max_length": 255},
    "gateway_port": {"type": str, "max_length": 20},
    "ixia": {"type": str, "max_length": 255},
    "ixia_port": {"type": str, "max_length": 20},
    "full_model": {"type": str, "max_length": 255},
    "notes": {"type": str, "max_length": 4000},
}


def _serialize_timestamp(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


@tickets_bp.route("/api/tickets", methods=["POST"])
@require_auth
def create_ticket():
    if g.current_user["role"] not in ALLOWED_ROLES:
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    payload, parse_error = parse_json_request(request)
    if parse_error is not None:
        return parse_error
    assert payload is not None

    normalized, errors = validate_object(
        payload,
        {
            "title": {"required": True, "type": str, "max_length": 200},
            "description": {"required": True, "type": str},
            "priority": {"required": True, "type": str, "allowed": PRIORITY_VALUES},
            "setup_snapshot": {"required": True, "type": dict},
        },
    )
    if errors is not None:
        return validation_error_response(details=errors)
    assert normalized is not None

    setup_snapshot, setup_errors = validate_object(
        normalized["setup_snapshot"], SETUP_SNAPSHOT_SCHEMA
    )
    if setup_errors is not None:
        return validation_error_response(details={"setup_snapshot": setup_errors})
    assert setup_snapshot is not None

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tickets (
                        title, description, priority, setup_snapshot, requester_id,
                        status, assigned_to, resolution, closed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 'New', NULL, NULL, NULL)
                    RETURNING
                        id, ticket_number, title, description, priority, status,
                        requester_id, assigned_to, setup_snapshot, created_at, updated_at;
                    """,
                    (
                        normalized["title"],
                        normalized["description"],
                        PRIORITY_TO_DATABASE_VALUE[normalized["priority"]],
                        Jsonb(setup_snapshot),
                        g.current_user["id"],
                    ),
                )
                created_ticket = cursor.fetchone()
                assert created_ticket is not None
                cursor.execute(
                    """
                    INSERT INTO ticket_history (
                        ticket_id, changed_by, action, old_status, new_status
                    )
                    VALUES (%s, %s, 'TICKET_CREATED', NULL, 'New');
                    """,
                    (str(created_ticket[0]), g.current_user["id"]),
                )
            connection.commit()
    except psycopg.Error:
        current_app.logger.error("Unable to create ticket.")
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    (
        ticket_id,
        ticket_number,
        title,
        description,
        priority,
        status,
        requester_id,
        assigned_to,
        returned_setup_snapshot,
        created_at,
        updated_at,
    ) = created_ticket
    ticket = {
        "id": str(ticket_id),
        "ticket_number": ticket_number,
        "title": title,
        "description": description,
        "priority": priority.title(),
        "status": status,
        "requester_id": str(requester_id),
        "assigned_to": str(assigned_to) if assigned_to is not None else None,
        "setup_snapshot": returned_setup_snapshot,
        "created_at": _serialize_timestamp(created_at),
        "updated_at": _serialize_timestamp(updated_at),
    }
    return success_response({"data": {"ticket": ticket}}, status_code=201)