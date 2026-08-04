from flask import Blueprint, current_app, jsonify
from psycopg import Error as PsycopgError

from app.db import get_db_connection

health_bp = Blueprint('health', __name__)


class _UnexpectedHealthCheckResultError(Exception):
    """Raised when SELECT 1 returns an unexpected value."""


@health_bp.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify backend and PostgreSQL are reachable."""
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                row = cursor.fetchone()

        if not row or row[0] != 1:
            raise _UnexpectedHealthCheckResultError(f"Unexpected health check result: {row!r}")

        return jsonify(
            {
                "status": "healthy",
                "backend": "active",
                "database": "connected",
            }
        ), 200
    except _UnexpectedHealthCheckResultError as exc:
        current_app.logger.error("Database health check failed: %s", exc)
        return jsonify(
            {
                "status": "unhealthy",
                "backend": "active",
                "database": "unavailable",
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "The database connection is unavailable.",
                },
            }
        ), 503
    except PsycopgError as exc:
        current_app.logger.exception("Database health check failed: %s", exc)
        return jsonify(
            {
                "status": "unhealthy",
                "backend": "active",
                "database": "unavailable",
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "The database connection is unavailable.",
                },
            }
        ), 503
