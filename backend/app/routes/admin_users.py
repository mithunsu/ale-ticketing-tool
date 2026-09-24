import re
import secrets
import uuid

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
ALLOWED_STATUSES = ("active", "inactive")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@admin_users_bp.route("/api/admin/users", methods=["GET"])
@require_auth
def list_users():
    # Server-side role check: React hiding the admin UI is not a substitute for this.
    if g.current_user["role"] != "admin":
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        name,
                        email,
                        role,
                        department,
                        status,
                        must_change_password,
                        created_at,
                        updated_at,
                        last_login_at
                    FROM users
                    ORDER BY name ASC, email ASC;
                    """
                )
                rows = cursor.fetchall()
    except psycopg.Error:
        current_app.logger.error("Unable to list users.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    users = [
        {
            "id": str(user_id),
            "name": name,
            "email": email,
            "role": role,
            "department": department,
            "status": status,
            "must_change_password": bool(must_change_password),
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
            "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at),
            "last_login_at": last_login_at.isoformat() if hasattr(last_login_at, "isoformat") else last_login_at,
        }
        for (
            user_id,
            name,
            email,
            role,
            department,
            status,
            must_change_password,
            created_at,
            updated_at,
            last_login_at,
        ) in rows
    ]
    return success_response({"data": {"users": users}}, status_code=200)


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


def _is_valid_uuid(value: str) -> bool:
    try:
        parsed = uuid.UUID(str(value))
        return str(parsed) == str(value).lower()
    except (ValueError, AttributeError, TypeError):
        return False


def _serialize_admin_user_row(row):
    (
        user_id,
        name,
        email,
        role,
        department,
        status,
        must_change_password,
        created_at,
        updated_at,
        last_login_at,
    ) = row
    return {
        "id": str(user_id),
        "name": name,
        "email": email,
        "role": role,
        "department": department,
        "status": status,
        "must_change_password": bool(must_change_password),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at),
        "last_login_at": last_login_at.isoformat() if hasattr(last_login_at, "isoformat") else last_login_at,
    }


def _lock_target_and_active_admins(cursor, user_id):
    """Lock the target row together with every currently-active admin row, id-ordered.

    Shared by the role-change and status-change endpoints so that any operation which could
    shrink the active-admin set contends for the exact same lock set, in the same order,
    regardless of which endpoint issues it -- this is what makes the two endpoints serialize
    against each other instead of racing.
    """
    cursor.execute(
        """
        SELECT
            id, name, email, role, department, status,
            must_change_password, created_at, updated_at, last_login_at
        FROM users
        WHERE id = %s OR (role = 'admin' AND status = 'active')
        ORDER BY id
        FOR UPDATE;
        """,
        (user_id,),
    )
    locked_rows = cursor.fetchall()
    target_row = next((row for row in locked_rows if str(row[0]) == user_id), None)
    return locked_rows, target_row


def _other_active_admins_remain(locked_rows, user_id):
    return any(str(row[0]) != user_id and row[3] == "admin" and row[5] == "active" for row in locked_rows)


@admin_users_bp.route("/api/admin/users/<user_id>/role", methods=["PATCH"])
@require_auth
def update_user_role(user_id):
    current_user = g.current_user
    # Server-side role check: React hiding the admin UI is not a substitute for this.
    if current_user["role"] != "admin":
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    if not _is_valid_uuid(user_id):
        return validation_error_response(details={"user_id": "Must be a valid UUID."})

    payload, parse_error = parse_json_request(request)
    if parse_error is not None:
        return parse_error

    normalized, errors = validate_object(
        payload,
        {"role": {"required": True, "type": str, "allowed": ALLOWED_ROLES}},
    )
    if errors is not None:
        return validation_error_response(details=errors)

    new_role = normalized["role"]
    current_user_id = str(current_user["id"])

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # Lock the target row together with every currently-active admin row, in a
                # fixed id order, in one statement. Any concurrent role change touching an
                # overlapping row acquires locks in the same deterministic order, so two
                # transactions can never hold conflicting locks and wait on each other
                # (no deadlock), and the active-admin count below can't go stale mid-transaction.
                locked_rows, target_row = _lock_target_and_active_admins(cursor, user_id)
                if target_row is None:
                    return error_response(
                        code="USER_NOT_FOUND",
                        message="The requested user does not exist.",
                        status_code=404,
                    )

                current_role = target_row[3]
                current_status = target_row[5]

                if str(target_row[0]) == current_user_id and current_role == "admin" and new_role != "admin":
                    return error_response(
                        code="SELF_DEMOTION_FORBIDDEN",
                        message="Admins cannot remove their own admin role.",
                        status_code=403,
                    )

                if current_role == new_role:
                    return success_response(
                        {"data": {"user": _serialize_admin_user_row(target_row)}},
                        status_code=200,
                    )

                if current_role == "admin" and current_status == "active" and new_role != "admin":
                    if not _other_active_admins_remain(locked_rows, user_id):
                        return error_response(
                            code="LAST_ACTIVE_ADMIN",
                            message="At least one active admin must remain.",
                            status_code=403,
                        )

                cursor.execute(
                    """
                    UPDATE users
                    SET role = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING
                        id, name, email, role, department, status,
                        must_change_password, created_at, updated_at, last_login_at;
                    """,
                    (new_role, user_id),
                )
                updated_row = cursor.fetchone()
            connection.commit()
    except psycopg.Error:
        current_app.logger.error("Unable to update user role.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    return success_response(
        {"data": {"user": _serialize_admin_user_row(updated_row)}},
        status_code=200,
    )


@admin_users_bp.route("/api/admin/users/<user_id>/status", methods=["PATCH"])
@require_auth
def update_user_status(user_id):
    current_user = g.current_user
    # Server-side role check: React hiding the admin UI is not a substitute for this.
    if current_user["role"] != "admin":
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    if not _is_valid_uuid(user_id):
        return validation_error_response(details={"user_id": "Must be a valid UUID."})

    payload, parse_error = parse_json_request(request)
    if parse_error is not None:
        return parse_error

    normalized, errors = validate_object(
        payload,
        {"status": {"required": True, "type": str, "allowed": ALLOWED_STATUSES}},
    )
    if errors is not None:
        return validation_error_response(details=errors)

    new_status = normalized["status"]
    current_user_id = str(current_user["id"])

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # Same cross-endpoint lock set/order as update_user_role: a concurrent role
                # demotion and a concurrent deactivation of a different admin contend for the
                # same rows, so they always serialize instead of both observing a stale count.
                locked_rows, target_row = _lock_target_and_active_admins(cursor, user_id)
                if target_row is None:
                    return error_response(
                        code="USER_NOT_FOUND",
                        message="The requested user does not exist.",
                        status_code=404,
                    )

                current_role = target_row[3]
                current_status = target_row[5]

                if str(target_row[0]) == current_user_id and new_status != "active":
                    return error_response(
                        code="SELF_DEACTIVATION_FORBIDDEN",
                        message="Admins cannot deactivate their own account.",
                        status_code=403,
                    )

                if current_status == new_status:
                    return success_response(
                        {"data": {"user": _serialize_admin_user_row(target_row)}},
                        status_code=200,
                    )

                if current_role == "admin" and current_status == "active" and new_status != "active":
                    if not _other_active_admins_remain(locked_rows, user_id):
                        return error_response(
                            code="LAST_ACTIVE_ADMIN",
                            message="At least one active admin must remain.",
                            status_code=403,
                        )

                cursor.execute(
                    """
                    UPDATE users
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING
                        id, name, email, role, department, status,
                        must_change_password, created_at, updated_at, last_login_at;
                    """,
                    (new_status, user_id),
                )
                updated_row = cursor.fetchone()
            connection.commit()
    except psycopg.Error:
        current_app.logger.error("Unable to update user status.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    return success_response(
        {"data": {"user": _serialize_admin_user_row(updated_row)}},
        status_code=200,
    )


@admin_users_bp.route("/api/admin/users/<user_id>/reset-password", methods=["POST"])
@require_auth
def reset_user_password(user_id):
    current_user = g.current_user
    # Server-side role check: React hiding the admin UI is not a substitute for this.
    if current_user["role"] != "admin":
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    if not _is_valid_uuid(user_id):
        return validation_error_response(details={"user_id": "Must be a valid UUID."})

    if str(current_user["id"]) == user_id:
        return error_response(
            code="SELF_PASSWORD_RESET_FORBIDDEN",
            message="Use the password-change flow to update your own password.",
            status_code=403,
        )

    # No request body is required; the server always generates the temporary password.
    # If a body is sent anyway, reject anything the client tries to smuggle in (e.g. its
    # own chosen password) rather than silently ignoring it.
    payload = request.get_json(silent=True)
    if payload:
        _normalized, errors = validate_object(payload, {})
        if errors is not None:
            return validation_error_response(details=errors)

    temporary_password = secrets.token_urlsafe(24)
    password_hash = generate_password_hash(temporary_password)

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE users
                    SET password_hash = %s, must_change_password = true, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING
                        id, name, email, role, department, status,
                        must_change_password, created_at, updated_at, last_login_at;
                    """,
                    (password_hash, user_id),
                )
                updated_row = cursor.fetchone()
                if updated_row is None:
                    return error_response(
                        code="USER_NOT_FOUND",
                        message="The requested user does not exist.",
                        status_code=404,
                    )
            connection.commit()
    except psycopg.Error:
        current_app.logger.error("Unable to reset user password.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    # This is the only response that exposes the generated temporary password.
    return success_response(
        {"data": {"user": _serialize_admin_user_row(updated_row), "temporary_password": temporary_password}},
        status_code=200,
    )