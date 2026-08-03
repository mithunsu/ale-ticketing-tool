import os

import psycopg


def get_db_connection():
    """Open a PostgreSQL connection using environment-based configuration."""
    host = os.getenv("POSTGRES_HOST")
    port_raw = os.getenv("POSTGRES_PORT")
    database = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")

    if not all([host, port_raw, database, user, password]):
        raise psycopg.OperationalError("Database configuration is incomplete")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise psycopg.OperationalError("POSTGRES_PORT must be an integer") from exc

    return psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
        connect_timeout=5
    )