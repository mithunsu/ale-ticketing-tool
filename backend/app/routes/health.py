from flask import Blueprint, current_app, jsonify
from psycopg import Error as PsycopgError

from app.database import get_db_connection

health_bp = Blueprint('health', __name__)


@health_bp.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify backend is running."""
    return jsonify({
        "status": "ok",
        "message": "ALE Ticket Management API is running"
    }), 200


@health_bp.route('/health/database', methods=['GET'])
def database_health_check():
    """Database health endpoint to validate PostgreSQL connectivity."""
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()

        if row and row[0] == 1:
            return jsonify({
                "status": "healthy",
                "database": "connected",
            }), 200

        current_app.logger.error("Database health check returned unexpected result")
    except PsycopgError:
        current_app.logger.error("Database health check failed")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return jsonify({
        "status": "unhealthy",
        "database": "unavailable",
    }), 503
