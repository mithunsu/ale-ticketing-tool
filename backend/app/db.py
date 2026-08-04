import os

import psycopg


def get_db_connection():
    """Open a PostgreSQL connection from DB_* environment settings."""
    host = os.getenv("DB_HOST")
    port_raw = os.getenv("DB_PORT")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not all([host, port_raw, database, user, password]):
        raise psycopg.OperationalError("Database configuration is incomplete")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise psycopg.OperationalError("DB_PORT must be an integer") from exc

    return psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
        connect_timeout=5,
    )
