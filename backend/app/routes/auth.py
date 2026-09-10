from functools import wraps

import psycopg
from flask import Blueprint, current_app, g, request, session
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db_connection
from app.responses import error_response, success_response, validation_error_response
from app.validation import parse_json_request, validate_object

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/auth/csrf", methods=["GET"])
def csrf_token():
    return success_response({"data": {"csrf_token": generate_csrf()}}, status_code=200)


def _safe_user_row(user_row):
    if user_row is None:
        return None

    user_id, name, email, role, status, _password_hash, must_change_password = user_row
    return {
        "id": str(user_id),
        "name": name,
        "email": email,
        "role": role,
        "status": status,
        "must_change_password": bool(must_change_password),
    }


def _user_lookup_by_id(user_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    email,
                    role,
                    status,
                    password_hash,
                    must_change_password
                FROM users
                WHERE id = %s
                LIMIT 1;
                """,
                (str(user_id),),
            )
            row = cursor.fetchone()
    return row


def _user_lookup_by_email(email):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    email,
                    role,
                    status,
                    password_hash,
                    must_change_password
                FROM users
                WHERE LOWER(email) = LOWER(%s)
                LIMIT 1;
                """,
                (email,),
            )
            row = cursor.fetchone()
    return row


def load_current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None

    user_row = _user_lookup_by_id(user_id)
    if user_row is None:
        session.clear()
        return None

    user = _safe_user_row(user_row)
    if user is None or user["status"] != "active":
        session.clear()
        return None

    g.current_user = user
    return user


def require_auth(view_func=None, *, allow_password_change_required=False):
    def decorator(actual_view_func):
        @wraps(actual_view_func)
        def wrapped(*args, **kwargs):
            current_user = load_current_user()
            if current_user is None:
                return error_response(
                    code="AUTHENTICATION_REQUIRED",
                    message="Authentication is required.",
                    status_code=401,
                )

            if current_user["must_change_password"] and not allow_password_change_required:
                return error_response(
                    code="PASSWORD_CHANGE_REQUIRED",
                    message="You must change your temporary password before continuing.",
                    status_code=403,
                )

            return actual_view_func(*args, **kwargs)

        return wrapped

    if view_func is None:
        return decorator
    return decorator(view_func)


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    payload, parse_error = parse_json_request(request)
    if parse_error is not None:
        return parse_error

    normalized, errors = validate_object(
        payload,
        {
            "email": {"required": True, "type": str, "max_length": 254},
            "password": {"required": True, "type": str, "strip": False},
        },
    )
    if errors is not None:
        return validation_error_response(details=errors)

    email = normalized["email"].strip().lower()
    submitted_password = normalized["password"]

    user_row = _user_lookup_by_email(email)
    if user_row is None:
        return error_response(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password.",
            status_code=401,
        )

    user_id, name, email_value, role, status, password_hash, must_change_password = user_row

    if password_hash is None or not check_password_hash(password_hash, submitted_password):
        return error_response(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password.",
            status_code=401,
        )

    if status != "active":
        return error_response(
            code="ACCOUNT_INACTIVE",
            message="This account is inactive.",
            status_code=403,
        )

    session.clear()
    session["user_id"] = str(user_id)

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = %s;",
                (str(user_id),),
            )
        connection.commit()

    user_payload = {
        "id": str(user_id),
        "name": name,
        "email": email_value,
        "role": role,
        "must_change_password": bool(must_change_password),
    }
    return success_response({"data": {"user": user_payload}}, status_code=200)


@auth_bp.route("/api/auth/me", methods=["GET"])
@require_auth(allow_password_change_required=True)
def current_user():
    safe_user = load_current_user()
    if safe_user is None:
        return error_response(
            code="AUTHENTICATION_REQUIRED",
            message="Authentication is required.",
            status_code=401,
        )
    return success_response({"data": {"user": safe_user}}, status_code=200)


@auth_bp.route("/api/auth/change-password", methods=["POST"])
@require_auth(allow_password_change_required=True)
def change_password():
    payload, parse_error = parse_json_request(request)
    if parse_error is not None:
        return parse_error

    normalized, errors = validate_object(
        payload,
        {
            "current_password": {"required": True, "type": str, "strip": False},
            "new_password": {
                "required": True,
                "type": str,
                "strip": False,
                "min_length": 12,
                "max_length": 128,
            },
        },
    )
    if errors is not None:
        return validation_error_response(details=errors)

    current_password = normalized["current_password"]
    new_password = normalized["new_password"]

    if new_password == current_password:
        return error_response(
            code="PASSWORD_REUSE_NOT_ALLOWED",
            message="The new password must be different from the current password.",
            status_code=400,
        )

    user_id = session.get("user_id")
    if user_id is None:
        return error_response(
            code="AUTHENTICATION_REQUIRED",
            message="Authentication is required.",
            status_code=401,
        )

    user_row = _user_lookup_by_id(user_id)
    if user_row is None:
        session.clear()
        return error_response(
            code="AUTHENTICATION_REQUIRED",
            message="Authentication is required.",
            status_code=401,
        )

    stored_password_hash = user_row[5]
    if stored_password_hash is None or not check_password_hash(stored_password_hash, current_password):
        return error_response(
            code="INVALID_CURRENT_PASSWORD",
            message="The current password is incorrect.",
            status_code=401,
        )

    new_password_hash = generate_password_hash(new_password)

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE users
                    SET
                        password_hash = %s,
                        must_change_password = false,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                    """,
                    (new_password_hash, str(user_id)),
                )
            connection.commit()
    except psycopg.Error:
        current_app.logger.exception("Password update failed for user_id=%s", user_id)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    session.clear()
    return success_response({"data": {"message": "Password changed successfully. Please log in again."}}, status_code=200)


@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return success_response({"data": {"message": "Logged out successfully."}}, status_code=200)
