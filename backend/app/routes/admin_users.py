import re
import secrets

import psycopg
from flask import Blueprint, current_app, g, request
from psycopg.errors import UniqueViolation
from werkzeug.security import generate_password_hash

from app.db import get_db_connection
from app.responses import error_response, success_response, validation_error_response
from app.routes.auth import require_auth
from app.validation import parse_json_request, validate_object


admin_users_bp = Blueprint("admin_users", __name__)

ALLOWED_ROLES = ("requester", "support_engineer", "manager", "admin")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@admin_users_bp.route("/api/admin/users", methods=["POST"])
@require_auth
def create_user():
    if g.current_user["must_change_password"]:
        return error_response(
            code="PASSWORD_CHANGE_REQUIRED",
            message="You must change your temporary password before continuing.",
            status_code=403,
        )

    if g.current_user["role"] != "admin":
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    payload, parse_error = parse_json_request(request)
    if parse_error is not None:
        return parse_error

    normalized, errors = validate_object(
        payload,
        {
            "name": {"required": True, "type": str, "min_length": 1, "max_length": 255},
            "email": {"required": True, "type": str, "min_length": 1, "max_length": 255},
            "role": {"required": True, "type": str, "allowed": ALLOWED_ROLES},
            "department": {"type": str, "max_length": 255},
        },
    )
    if errors is not None:
        return validation_error_response(details=errors)

    email = normalized["email"].lower()
    if not EMAIL_PATTERN.fullmatch(email):
        return validation_error_response(details={"email": "Must be a valid email address."})

    department = normalized.get("department") or None
    temporary_password = secrets.token_urlsafe(24)
    password_hash = generate_password_hash(temporary_password)

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (
                        name,
                        email,
                        role,
                        department,
                        status,
                        password_hash,
                        must_change_password,
                        sso_id
                    )
                    VALUES (%s, %s, %s, %s, 'active', %s, true, NULL)
                    RETURNING id, name, email, role, department, status, must_change_password, created_at;
                    """,
                    (
                        normalized["name"],
                        email,
                        normalized["role"],
                        department,
                        password_hash,
                    ),
                )
                created_user = cursor.fetchone()
            connection.commit()
    except UniqueViolation:
        return error_response(
            code="USER_ALREADY_EXISTS",
            message="An account with this email already exists.",
            status_code=409,
        )
    except psycopg.Error:
        current_app.logger.error("Unable to provision user account.")
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    user_id, name, email, role, department, status, must_change_password, created_at = created_user
    user = {
        "id": str(user_id),
        "name": name,
        "email": email,
        "role": role,
        "department": department,
        "status": status,
        "must_change_password": bool(must_change_password),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
    }
    # This is the only response that exposes the generated temporary password.
    return success_response(
        {"data": {"user": user, "temporary_password": temporary_password}},
        status_code=201,
    )