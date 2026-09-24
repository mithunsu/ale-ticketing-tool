import uuid

import psycopg
from flask import Blueprint, current_app, g, request
from psycopg.types.json import Jsonb

from app.db import get_db_connection
from app.responses import error_response, success_response, validation_error_response
from app.routes.auth import require_auth
from app.validation import parse_json_request, validate_object


tickets_bp = Blueprint("tickets", __name__)

ALLOWED_ROLES = ("requester", "support_engineer", "manager", "admin")
VALID_TICKET_STATUS_VALUES = ("New", "Open", "In Progress", "Resolved", "Closed")
ALLOWED_STATUS_TRANSITIONS = {
    ("New", "Open"),
    ("Open", "In Progress"),
    ("In Progress", "Resolved"),
    ("Resolved", "In Progress"),
    ("Resolved", "Closed"),
    ("Closed", "In Progress"),
}
PRIORITY_VALUES = ("Low", "Medium", "High", "Critical")
PRIORITY_TO_DATABASE_VALUE = {priority: priority.lower() for priority in PRIORITY_VALUES}
SETUP_SNAPSHOT_SCHEMA = {
    "server_name": {"required": True, "type": str, "max_length": 255},
    "server_ip": {"required": True, "type": str, "max_length": 255},
    "platform": {"required": True, "type": str, "max_length": 255},
    "dut": {"required": True, "type": str, "max_length": 255},
    "aos_image_build": {"required": True, "type": str, "max_length": 255},
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


def _is_valid_uuid(value: str) -> bool:
    try:
        parsed = uuid.UUID(str(value))
        return str(parsed) == str(value).lower()
    except (ValueError, AttributeError, TypeError):
        return False


def _serialize_assignment(ticket_id, assigned_to, updated_at):
    return {
        "id": str(ticket_id),
        "assigned_to": str(assigned_to) if assigned_to is not None else None,
        "updated_at": _serialize_timestamp(updated_at),
    }


def _serialize_status_ticket(ticket_id, status, assigned_to, updated_at, closed_at=None):
    return {
        "id": str(ticket_id),
        "status": status,
        "assigned_to": str(assigned_to) if assigned_to is not None else None,
        "updated_at": _serialize_timestamp(updated_at),
        "closed_at": _serialize_timestamp(closed_at) if closed_at is not None else None,
    }


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
        current_app.logger.error("Unable to create ticket.", exc_info=True)
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


@tickets_bp.route("/api/tickets", methods=["GET"])
@require_auth
def list_tickets():
    current_user_role = g.current_user["role"]
    if current_user_role not in ALLOWED_ROLES:
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    errors = {}
    raw_page = request.args.get("page")
    raw_limit = request.args.get("limit")

    page = 1
    if raw_page is not None:
        try:
            page = int(raw_page)
            if page < 1:
                errors["page"] = "Must be an integer greater than or equal to 1."
        except (ValueError, TypeError):
            errors["page"] = "Must be an integer."

    limit = 10
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
            if limit < 1 or limit > 20:
                errors["limit"] = "Must be an integer between 1 and 20."
        except (ValueError, TypeError):
            errors["limit"] = "Must be an integer."

    raw_status_not = request.args.get("status_not")
    status_not = None
    if raw_status_not is not None:
        if raw_status_not not in VALID_TICKET_STATUS_VALUES:
            errors["status_not"] = f"Must be one of: {', '.join(VALID_TICKET_STATUS_VALUES)}."
        else:
            status_not = raw_status_not

    raw_status = request.args.get("status")
    status = None
    if raw_status is not None:
        if raw_status not in VALID_TICKET_STATUS_VALUES:
            errors["status"] = f"Must be one of: {', '.join(VALID_TICKET_STATUS_VALUES)}."
        else:
            status = raw_status

    if raw_status is not None and raw_status_not is not None:
        errors["status"] = "Cannot be combined with status_not."

    raw_priority = request.args.get("priority")
    priority = None
    if raw_priority is not None:
        if raw_priority not in PRIORITY_VALUES:
            errors["priority"] = f"Must be one of: {', '.join(PRIORITY_VALUES)}."
        else:
            priority = PRIORITY_TO_DATABASE_VALUE[raw_priority]

    raw_assigned_to = request.args.get("assigned_to")
    assigned_to = None
    if raw_assigned_to is not None:
        if raw_assigned_to == "me":
            assigned_to = "me"
        else:
            errors["assigned_to"] = "Must be 'me' or omitted."

    if errors:
        return validation_error_response(details=errors)

    offset = (page - 1) * limit

    base_query = """
        SELECT
            t.id,
            t.ticket_number,
            t.title,
            t.description,
            t.priority,
            t.status,
            t.requester_id,
            u.name AS requester_name,
            u.email AS requester_email,
            t.assigned_to,
            assignee.name AS assignee_name,
            t.setup_snapshot,
            t.due_date,
            t.resolution,
            t.created_at,
            t.updated_at,
            t.closed_at
        FROM tickets t
        INNER JOIN users u ON t.requester_id = u.id
        LEFT JOIN users assignee ON t.assigned_to = assignee.id
    """

    # Build WHERE conditions dynamically.
    # Two condition lists are kept because the count query selects from
    # "tickets" (no alias) while the data query selects from "tickets t".
    data_conditions = []
    count_conditions = []
    where_params = []

    if current_user_role == "requester":
        data_conditions.append("t.requester_id = %s")
        count_conditions.append("requester_id = %s")
        where_params.append(str(g.current_user["id"]))

    if status_not is not None:
        data_conditions.append("t.status <> %s")
        count_conditions.append("status <> %s")
        where_params.append(status_not)
    elif status is not None:
        data_conditions.append("t.status = %s")
        count_conditions.append("status = %s")
        where_params.append(status)

    if priority is not None:
        data_conditions.append("t.priority = %s")
        count_conditions.append("priority = %s")
        where_params.append(priority)

    if assigned_to == "me":
        data_conditions.append("t.assigned_to = %s")
        count_conditions.append("assigned_to = %s")
        where_params.append(str(g.current_user["id"]))

    # Build the WHERE clauses
    if data_conditions:
        where_clause = " WHERE " + " AND ".join(data_conditions)
        count_where_clause = " WHERE " + " AND ".join(count_conditions)
    else:
        where_clause = ""
        count_where_clause = ""

    # Build count query
    count_query = "SELECT COUNT(*) FROM tickets" + count_where_clause + ";"
    count_params = tuple(where_params) if where_params else None

    # Build main query
    query = (
        base_query
        + where_clause
        + "\n        ORDER BY t.created_at DESC, t.id DESC\n        LIMIT %s OFFSET %s;"
    )
    params = tuple(where_params) + (limit, offset)

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                if count_params is not None:
                    cursor.execute(count_query, count_params)
                else:
                    cursor.execute(count_query)
                count_row = cursor.fetchone()
                total = count_row[0] if count_row is not None else 0

                cursor.execute(query, params)
                rows = cursor.fetchall()
    except psycopg.Error:
        current_app.logger.error("Unable to list tickets.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    total_pages = 0 if total == 0 else (total + limit - 1) // limit

    tickets_list = []
    for row in rows:
        (
            ticket_id,
            ticket_number,
            title,
            description,
            priority,
            status,
            requester_id,
            requester_name,
            requester_email,
            assigned_to,
            assignee_name,
            setup_snapshot,
            due_date,
            resolution,
            created_at,
            updated_at,
            closed_at,
        ) = row

        tickets_list.append(
            {
                "id": str(ticket_id),
                "ticket_number": ticket_number,
                "title": title,
                "description": description,
                "priority": priority.title() if priority else priority,
                "status": status,
                "requester_id": str(requester_id),
                "requester_name": requester_name,
                "requester_email": requester_email,
                "assigned_to": str(assigned_to) if assigned_to is not None else None,
                "assignee_name": assignee_name,
                "setup_snapshot": setup_snapshot,
                "due_date": _serialize_timestamp(due_date) if due_date is not None else None,
                "resolution": resolution,
                "created_at": _serialize_timestamp(created_at),
                "updated_at": _serialize_timestamp(updated_at),
                "closed_at": _serialize_timestamp(closed_at) if closed_at is not None else None,
            }
        )

    return success_response(
        {
            "data": {
                "tickets": tickets_list,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "total_pages": total_pages,
                },
            }
        },
        status_code=200,
    )


@tickets_bp.route("/api/tickets/<ticket_id>", methods=["GET"])
@require_auth
def get_ticket(ticket_id):
    current_user_role = g.current_user["role"]
    if current_user_role not in ALLOWED_ROLES:
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    if not _is_valid_uuid(ticket_id):
        return validation_error_response(details={"ticket_id": "Must be a valid UUID."})

    ticket_query = """
        SELECT
            t.id,
            t.ticket_number,
            t.title,
            t.description,
            t.priority,
            t.status,
            t.requester_id,
            u.name AS requester_name,
            u.email AS requester_email,
            t.assigned_to,
            t.setup_snapshot,
            t.due_date,
            t.resolution,
            t.created_at,
            t.updated_at,
            t.closed_at
        FROM tickets t
        INNER JOIN users u ON t.requester_id = u.id
    """

    if current_user_role == "requester":
        ticket_query += "\n        WHERE t.id = %s AND t.requester_id = %s;"
        ticket_params = (ticket_id, str(g.current_user["id"]))
    else:
        ticket_query += "\n        WHERE t.id = %s;"
        ticket_params = (ticket_id,)

    history_query = """
        SELECT
            th.id,
            th.action,
            th.old_status,
            th.new_status,
            th.changed_by,
            u.name AS actor_name,
            u.email AS actor_email,
            th.created_at
        FROM ticket_history th
        LEFT JOIN users u ON th.changed_by = u.id
        WHERE th.ticket_id = %s
        ORDER BY th.created_at ASC, th.id ASC;
    """

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(ticket_query, ticket_params)
                ticket_row = cursor.fetchone()

                if ticket_row is None:
                    return error_response(
                        code="TICKET_NOT_FOUND",
                        message="The requested ticket does not exist.",
                        status_code=404,
                    )

                cursor.execute(history_query, (ticket_id,))
                history_rows = cursor.fetchall()
    except psycopg.Error:
        current_app.logger.error("Unable to get ticket.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    (
        t_id,
        ticket_number,
        title,
        description,
        priority,
        status,
        requester_id,
        requester_name,
        requester_email,
        assigned_to,
        setup_snapshot,
        due_date,
        resolution,
        created_at,
        updated_at,
        closed_at,
    ) = ticket_row

    ticket_data = {
        "id": str(t_id),
        "ticket_number": ticket_number,
        "title": title,
        "description": description,
        "priority": priority.title() if priority else priority,
        "status": status,
        "requester_id": str(requester_id),
        "requester_name": requester_name,
        "requester_email": requester_email,
        "assigned_to": str(assigned_to) if assigned_to is not None else None,
        "setup_snapshot": setup_snapshot,
        "due_date": _serialize_timestamp(due_date) if due_date is not None else None,
        "resolution": resolution,
        "created_at": _serialize_timestamp(created_at),
        "updated_at": _serialize_timestamp(updated_at),
        "closed_at": _serialize_timestamp(closed_at) if closed_at is not None else None,
    }

    history_data = []
    for h_row in history_rows:
        (
            h_id,
            action,
            old_status,
            new_status,
            changed_by,
            actor_name,
            actor_email,
            h_created_at,
        ) = h_row
        history_data.append(
            {
                "id": str(h_id),
                "action": action,
                "old_status": old_status,
                "new_status": new_status,
                "changed_by": str(changed_by) if changed_by is not None else None,
                "actor_name": actor_name,
                "actor_email": actor_email,
                "created_at": _serialize_timestamp(h_created_at),
            }
        )

    return success_response(
        {
            "data": {
                "ticket": ticket_data,
                "history": history_data,
            }
        },
        status_code=200,
    )


@tickets_bp.route("/api/tickets/<ticket_id>/comments", methods=["POST"])
@require_auth
def create_ticket_comment(ticket_id):
    current_user = g.current_user
    if current_user["role"] not in ALLOWED_ROLES:
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    if not _is_valid_uuid(ticket_id):
        return validation_error_response(details={"ticket_id": "Must be a valid UUID."})

    payload, parse_error = parse_json_request(request)
    if parse_error is not None:
        return parse_error
    assert payload is not None

    normalized, errors = validate_object(payload, {"comment": {"required": True, "type": str}})
    if errors is not None:
        return validation_error_response(details=errors)
    assert normalized is not None

    comment_text = normalized["comment"]
    current_user_id = str(current_user["id"])

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # requester ownership check mirrors GET /api/tickets/<ticket_id> anti-enumeration behavior
                if current_user["role"] == "requester":
                    cursor.execute(
                        "SELECT id FROM tickets WHERE id = %s AND requester_id = %s;",
                        (ticket_id, current_user_id),
                    )
                else:
                    cursor.execute("SELECT id FROM tickets WHERE id = %s;", (ticket_id,))

                if cursor.fetchone() is None:
                    return error_response(
                        code="TICKET_NOT_FOUND",
                        message="The requested ticket does not exist.",
                        status_code=404,
                    )

                cursor.execute(
                    """
                    INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
                    VALUES (%s, %s, %s, 'public')
                    RETURNING id, ticket_id, author_id, comment_text, comment_type, created_at;
                    """,
                    (ticket_id, current_user_id, comment_text),
                )
                created_comment = cursor.fetchone()
                assert created_comment is not None
            connection.commit()
    except psycopg.Error:
        current_app.logger.error("Unable to create ticket comment.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    (
        comment_id,
        comment_ticket_id,
        author_id,
        comment_text_value,
        comment_type,
        created_at,
    ) = created_comment

    comment = {
        "id": str(comment_id),
        "ticket_id": str(comment_ticket_id),
        "user_id": str(author_id),
        "comment": comment_text_value,
        "comment_type": comment_type,
        "created_at": _serialize_timestamp(created_at),
        "author_name": current_user.get("name"),
        "author_email": current_user.get("email"),
    }
    return success_response({"data": {"comment": comment}}, status_code=201)


@tickets_bp.route("/api/tickets/<ticket_id>/comments", methods=["GET"])
@require_auth
def list_ticket_comments(ticket_id):
    current_user = g.current_user
    if current_user["role"] not in ALLOWED_ROLES:
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    if not _is_valid_uuid(ticket_id):
        return validation_error_response(details={"ticket_id": "Must be a valid UUID."})

    comments_query = """
        SELECT
            c.id,
            c.ticket_id,
            c.author_id,
            c.comment_text,
            c.comment_type,
            c.created_at,
            u.name AS author_name,
            u.email AS author_email
        FROM ticket_comments c
        LEFT JOIN users u ON c.author_id = u.id
        WHERE c.ticket_id = %s
        ORDER BY c.created_at ASC, c.id ASC;
    """

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # ticket access check mirrors GET /api/tickets/<ticket_id> anti-enumeration behavior
                if current_user["role"] == "requester":
                    cursor.execute(
                        "SELECT id FROM tickets WHERE id = %s AND requester_id = %s;",
                        (ticket_id, str(current_user["id"])),
                    )
                else:
                    cursor.execute("SELECT id FROM tickets WHERE id = %s;", (ticket_id,))

                if cursor.fetchone() is None:
                    return error_response(
                        code="TICKET_NOT_FOUND",
                        message="The requested ticket does not exist.",
                        status_code=404,
                    )

                cursor.execute(comments_query, (ticket_id,))
                comment_rows = cursor.fetchall()
    except psycopg.Error:
        current_app.logger.error("Unable to list ticket comments.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    comments = []
    for row in comment_rows:
        (
            comment_id,
            comment_ticket_id,
            author_id,
            comment_text_value,
            comment_type,
            created_at,
            author_name,
            author_email,
        ) = row
        comments.append(
            {
                "id": str(comment_id),
                "ticket_id": str(comment_ticket_id),
                "user_id": str(author_id) if author_id is not None else None,
                "comment": comment_text_value,
                "comment_type": comment_type,
                "created_at": _serialize_timestamp(created_at),
                "author_name": author_name,
                "author_email": author_email,
            }
        )

    return success_response({"data": {"comments": comments}}, status_code=200)


@tickets_bp.route("/api/tickets/<ticket_id>/status", methods=["PATCH"])
@require_auth
def update_ticket_status(ticket_id):
    current_user = g.current_user
    if current_user["role"] not in ALLOWED_ROLES:
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    if not _is_valid_uuid(ticket_id):
        return validation_error_response(details={"ticket_id": "Must be a valid UUID."})

    payload, parse_error = parse_json_request(request)
    if parse_error is not None:
        return parse_error
    assert payload is not None

    normalized, errors = validate_object(
        payload,
        {
            "status": {"required": True, "type": str},
            "resolution": {"type": str},
        },
    )
    if errors is not None:
        return validation_error_response(details=errors)
    assert normalized is not None

    target_status = normalized["status"]
    if target_status not in VALID_TICKET_STATUS_VALUES:
        return validation_error_response(details={"status": "Unsupported ticket status."})

    # resolution is only required when resolving; validate_object already trims whitespace for us
    resolution = normalized.get("resolution")

    current_user_id = str(current_user["id"])

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # requester ownership filter doubles as the anti-enumeration check for reopen requests
                if current_user["role"] == "requester":
                    cursor.execute(
                        "SELECT id, status, assigned_to, updated_at, closed_at FROM tickets WHERE id = %s AND requester_id = %s;",
                        (ticket_id, current_user_id),
                    )
                else:
                    cursor.execute(
                        "SELECT id, status, assigned_to, updated_at, closed_at FROM tickets WHERE id = %s;",
                        (ticket_id,),
                    )
                ticket_row = cursor.fetchone()
                if ticket_row is None:
                    return error_response(
                        code="TICKET_NOT_FOUND",
                        message="The requested ticket does not exist.",
                        status_code=404,
                    )

                ticket_id_db, current_status, assigned_to, updated_at, closed_at = ticket_row
                if current_user["role"] == "support_engineer":
                    if assigned_to is None or str(assigned_to) != current_user_id:
                        return error_response(
                            code="FORBIDDEN",
                            message="You do not have permission to perform this action.",
                            status_code=403,
                        )

                # requester's only permitted transition is the manual Closed -> In Progress reopen
                if current_user["role"] == "requester" and not (
                    current_status == "Closed" and target_status == "In Progress"
                ):
                    return error_response(
                        code="FORBIDDEN",
                        message="You do not have permission to perform this action.",
                        status_code=403,
                    )

                if target_status == current_status:
                    return success_response(
                        {
                            "data": {
                                "ticket": _serialize_status_ticket(
                                    ticket_id_db, current_status, assigned_to, updated_at, closed_at
                                )
                            }
                        },
                        status_code=200,
                    )

                if (current_status, target_status) not in ALLOWED_STATUS_TRANSITIONS:
                    return validation_error_response(details={"status": "Invalid status transition."})

                if target_status == "Resolved" and not resolution:
                    return validation_error_response(details={"resolution": "This field is required."})

                # closed_at is derived server-side only; the client cannot set or override it.
                if target_status == "Closed":
                    closed_at_assignment = "CURRENT_TIMESTAMP"
                elif current_status == "Closed" and target_status == "In Progress":
                    closed_at_assignment = "NULL"
                else:
                    closed_at_assignment = "closed_at"

                # resolution is written only when resolving; other transitions leave the existing value untouched.
                if target_status == "Resolved":
                    resolution_assignment = "%s"
                    resolution_params = (resolution,)
                else:
                    resolution_assignment = "resolution"
                    resolution_params = ()

                update_sql = (
                    f"UPDATE tickets SET status = %s, resolution = {resolution_assignment}, "
                    f"closed_at = {closed_at_assignment}, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = %s AND status = %s"
                )
                if current_user["role"] == "support_engineer":
                    update_sql += " AND assigned_to = %s"
                    update_params = (target_status, *resolution_params, ticket_id, current_status, current_user_id)
                else:
                    update_params = (target_status, *resolution_params, ticket_id, current_status)
                update_sql += " RETURNING id, status, assigned_to, updated_at, closed_at;"

                cursor.execute(update_sql, update_params)

                updated_ticket = cursor.fetchone()
                if updated_ticket is None:
                    cursor.execute(
                        "SELECT id, status, assigned_to, updated_at, closed_at FROM tickets WHERE id = %s;",
                        (ticket_id,),
                    )
                    current_ticket = cursor.fetchone()
                    if current_ticket is None:
                        return error_response(
                            code="TICKET_NOT_FOUND",
                            message="The requested ticket does not exist.",
                            status_code=404,
                        )

                    if current_user["role"] == "support_engineer" and str(current_ticket[2]) != current_user_id:
                        return error_response(
                            code="FORBIDDEN",
                            message="You do not have permission to perform this action.",
                            status_code=403,
                        )

                    return error_response(
                        code="CONFLICT",
                        message="The ticket was updated by another request.",
                        status_code=409,
                    )

                cursor.execute(
                    """
                    INSERT INTO ticket_history (
                        ticket_id, changed_by, action, old_status, new_status
                    )
                    VALUES (%s, %s, 'STATUS_CHANGED', %s, %s);
                    """,
                    (str(updated_ticket[0]), current_user_id, current_status, target_status),
                )

                # the resolution is also recorded as a normal public comment so it shows up in the comment history
                if target_status == "Resolved":
                    cursor.execute(
                        """
                        INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
                        VALUES (%s, %s, %s, 'public');
                        """,
                        (str(updated_ticket[0]), current_user_id, resolution),
                    )
            connection.commit()
    except psycopg.Error:
        current_app.logger.error("Unable to update ticket status.", exc_info=True)
        try:
            connection.rollback()
        except Exception:
            pass
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    return success_response(
        {"data": {"ticket": _serialize_status_ticket(*updated_ticket)}},
        status_code=200,
    )


@tickets_bp.route("/api/tickets/<ticket_id>/assignment", methods=["PATCH"])
@require_auth
def update_ticket_assignment(ticket_id):
    current_user = g.current_user
    if current_user["role"] == "requester":
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    if not _is_valid_uuid(ticket_id):
        return validation_error_response(details={"ticket_id": "Must be a valid UUID."})

    payload, parse_error = parse_json_request(request)
    if parse_error is not None:
        return parse_error
    assert payload is not None

    normalized, errors = validate_object(payload, {"assigned_to": {"required": True}})
    if errors is not None:
        return validation_error_response(details=errors)
    assert normalized is not None

    assigned_to = normalized["assigned_to"]
    if assigned_to is not None and (not isinstance(assigned_to, str) or not _is_valid_uuid(assigned_to)):
        return validation_error_response(details={"assigned_to": "Must be a valid UUID or null."})

    current_user_id = str(current_user["id"])
    if current_user["role"] == "support_engineer" and assigned_to != current_user_id:
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, assigned_to, updated_at FROM tickets WHERE id = %s;",
                    (ticket_id,),
                )
                ticket_row = cursor.fetchone()
                if ticket_row is None:
                    return error_response(
                        code="TICKET_NOT_FOUND",
                        message="The requested ticket does not exist.",
                        status_code=404,
                    )

                current_assigned_to = str(ticket_row[1]) if ticket_row[1] is not None else None
                if assigned_to == current_assigned_to:
                    return success_response(
                        {"data": {"ticket": _serialize_assignment(*ticket_row)}},
                        status_code=200,
                    )

                if current_user["role"] == "support_engineer" and current_assigned_to is not None:
                    return error_response(
                        code="FORBIDDEN",
                        message="You do not have permission to perform this action.",
                        status_code=403,
                    )

                if assigned_to is not None:
                    cursor.execute(
                        "SELECT id, role, status FROM users WHERE id = %s;",
                        (assigned_to,),
                    )
                    target_user = cursor.fetchone()
                    if target_user is None:
                        return error_response(
                            code="ASSIGNEE_NOT_FOUND",
                            message="The requested assignee does not exist.",
                            status_code=404,
                        )

                    target_id, target_role, target_status = target_user
                    is_admin_self_assignment = (
                        current_user["role"] == "admin" and str(target_id) == current_user_id
                    )
                    if target_status != "active" or (
                        target_role not in ("support_engineer", "manager")
                        and not is_admin_self_assignment
                    ):
                        return validation_error_response(
                            details={"assigned_to": "Must identify an active support engineer or manager."}
                        )

                if current_user["role"] == "support_engineer":
                    cursor.execute(
                        """
                        UPDATE tickets
                        SET assigned_to = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND assigned_to IS NULL
                        RETURNING id, assigned_to, updated_at;
                        """,
                        (assigned_to, ticket_id),
                    )
                    updated_ticket = cursor.fetchone()
                    if updated_ticket is None:
                        cursor.execute(
                            "SELECT id, assigned_to, updated_at FROM tickets WHERE id = %s;",
                            (ticket_id,),
                        )
                        current_ticket = cursor.fetchone()
                        if current_ticket is None:
                            return error_response(
                                code="TICKET_NOT_FOUND",
                                message="The requested ticket does not exist.",
                                status_code=404,
                            )
                        if str(current_ticket[1]) == current_user_id:
                            return success_response(
                                {"data": {"ticket": _serialize_assignment(*current_ticket)}},
                                status_code=200,
                            )
                        return error_response(
                            code="FORBIDDEN",
                            message="You do not have permission to perform this action.",
                            status_code=403,
                        )
                else:
                    cursor.execute(
                        """
                        UPDATE tickets
                        SET assigned_to = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, assigned_to, updated_at;
                        """,
                        (assigned_to, ticket_id),
                    )
                    updated_ticket = cursor.fetchone()
                    assert updated_ticket is not None
            connection.commit()
    except psycopg.Error:
        current_app.logger.error("Unable to update ticket assignment.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    return success_response(
        {"data": {"ticket": _serialize_assignment(*updated_ticket)}},
        status_code=200,
    )
