import psycopg
from flask import Blueprint, current_app, g

from app.db import get_db_connection
from app.responses import error_response, success_response
from app.routes.auth import require_auth

users_bp = Blueprint("users", __name__)


@users_bp.route("/api/users/assignable", methods=["GET"])
@require_auth
def list_assignable_users():
    current_user = g.current_user
    if current_user["role"] not in ("manager", "admin"):
        return error_response(
            code="FORBIDDEN",
            message="You do not have permission to perform this action.",
            status_code=403,
        )

    # Admins may additionally see themselves, mirroring the PATCH assignment self-assignment rule.
    if current_user["role"] == "admin":
        query = """
            SELECT id, name, role
            FROM users
            WHERE status = 'active' AND (role IN ('support_engineer', 'manager') OR id = %s)
            ORDER BY name ASC, id ASC;
        """
        params = (str(current_user["id"]),)
    else:
        query = """
            SELECT id, name, role
            FROM users
            WHERE status = 'active' AND role IN ('support_engineer', 'manager')
            ORDER BY name ASC, id ASC;
        """
        params = None

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                if params is not None:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                rows = cursor.fetchall()
    except psycopg.Error:
        current_app.logger.error("Unable to list assignable users.", exc_info=True)
        return error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            status_code=500,
        )

    users = [{"id": str(user_id), "name": name, "role": role} for user_id, name, role in rows]
    return success_response({"data": {"users": users}}, status_code=200)
