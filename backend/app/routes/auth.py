from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash

from app.db import get_db_connection
from app.responses import error_response, success_response, validation_error_response
from app.validation import parse_json_request, validate_object

auth_bp = Blueprint("auth", __name__)


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


def require_auth(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        current_user = load_current_user()
        if current_user is None:
            return error_response(
                code="AUTHENTICATION_REQUIRED",
                message="Authentication is required.",
                status_code=401,
            )
        return view_func(*args, **kwargs)

    return wrapped


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
@require_auth
def current_user():
    safe_user = load_current_user()
    if safe_user is None:
        return error_response(
            code="AUTHENTICATION_REQUIRED",
            message="Authentication is required.",
            status_code=401,
        )
    return success_response({"data": {"user": safe_user}}, status_code=200)


@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return success_response({"data": {"message": "Logged out successfully."}}, status_code=200)
