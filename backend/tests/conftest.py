import os
from pathlib import Path
import sys
import uuid

import psycopg
import pytest


# Ensure backend package imports work regardless of where pytest is launched.
BACKEND_DIR = Path(__file__).resolve().parents[1]
backend_path = str(BACKEND_DIR)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


@pytest.fixture(autouse=True)
def _set_test_secret(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key-1234567890")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")


def get_csrf_token(client):
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    token = response.get_json()["data"]["csrf_token"]
    assert token
    return token


def csrf_headers(client, **extra_headers):
    headers = {"X-CSRF-Token": get_csrf_token(client)}
    headers.update(extra_headers)
    return headers


def get_postgres_test_config():
    host = os.getenv("DB_HOST", "127.0.0.1")
    port_str = os.getenv("DB_PORT", "5433")
    try:
        port = int(port_str)
    except ValueError:
        port = 5433
    user = os.getenv("DB_USER", "ale_ticket_user")
    password = os.getenv("DB_PASSWORD", "123")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
    }


def is_postgres_available(config):
    maintenance_db = os.getenv("POSTGRES_MAINTENANCE_DB", "postgres")
    try:
        with psycopg.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            dbname=maintenance_db,
            connect_timeout=2,
            autocommit=True,
        ):
            return True
    except Exception:
        return False


@pytest.fixture
def postgres_disposable_db(monkeypatch):
    config = get_postgres_test_config()
    if not is_postgres_available(config):
        pytest.skip("PostgreSQL service is not running or accessible for integration tests.")

    test_db_name = f"ale_ticketing_test_{uuid.uuid4().hex[:12]}"
    maintenance_db = os.getenv("POSTGRES_MAINTENANCE_DB", "postgres")
    admin_conn_kwargs = {
        "host": config["host"],
        "port": config["port"],
        "user": config["user"],
        "password": config["password"],
        "dbname": maintenance_db,
        "autocommit": True,
    }

    # 1. Create disposable test database
    with psycopg.connect(**admin_conn_kwargs) as admin_conn:
        with admin_conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{test_db_name}";')

    test_db_kwargs = {
        "host": config["host"],
        "port": config["port"],
        "user": config["user"],
        "password": config["password"],
        "dbname": test_db_name,
    }

    try:
        # 2. Apply database/schema.sql
        repo_root = BACKEND_DIR.parent
        schema_path = repo_root / "database" / "schema.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")

        with psycopg.connect(**test_db_kwargs, autocommit=True) as test_conn:
            with test_conn.cursor() as cur:
                cur.execute(schema_sql)
                # 3. Create active test user
                cur.execute(
                    """
                    INSERT INTO users (
                        name,
                        email,
                        role,
                        department,
                        status,
                        password_hash,
                        must_change_password
                    )
                    VALUES (
                        'Integration Test User',
                        'integration.test@example.com',
                        'requester',
                        'QA',
                        'active',
                        'placeholder_hash',
                        false
                    )
                    RETURNING id;
                    """
                )
                user_id = str(cur.fetchone()[0])

        # 4. Point Flask app to disposable DB
        monkeypatch.setenv("DB_HOST", config["host"])
        monkeypatch.setenv("DB_PORT", str(config["port"]))
        monkeypatch.setenv("DB_USER", config["user"])
        monkeypatch.setenv("DB_PASSWORD", config["password"])
        monkeypatch.setenv("DB_NAME", test_db_name)

        yield {
            "db_name": test_db_name,
            "user_id": user_id,
            "config": test_db_kwargs,
        }
    finally:
        # 5. Clean up: terminate active connections and drop test DB
        try:
            with psycopg.connect(**admin_conn_kwargs) as admin_conn:
                with admin_conn.cursor() as cur:
                    cur.execute(
                        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{test_db_name}' AND pid <> pg_backend_pid();"
                    )
                    cur.execute(f'DROP DATABASE IF EXISTS "{test_db_name}";')
        except Exception:
            pass
