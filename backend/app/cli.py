import re

import click
import psycopg
from werkzeug.security import generate_password_hash

from app.db import get_db_connection


MAX_NAME_LENGTH = 255
MAX_EMAIL_LENGTH = 255
MAX_DEPARTMENT_LENGTH = 255
MIN_PASSWORD_LENGTH = 12
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_name(name: str) -> str:
    normalized_name = name.strip()
    if not normalized_name:
        raise click.UsageError("Name must not be empty.")
    if len(normalized_name) > MAX_NAME_LENGTH:
        raise click.UsageError(f"Name must be at most {MAX_NAME_LENGTH} characters.")
    return normalized_name


def _validate_email(email: str) -> str:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise click.UsageError("Email must not be empty.")
    if len(normalized_email) > MAX_EMAIL_LENGTH:
        raise click.UsageError(f"Email must be at most {MAX_EMAIL_LENGTH} characters.")
    if not EMAIL_PATTERN.fullmatch(normalized_email):
        raise click.UsageError("Email must be a valid email address.")
    return normalized_email


def _validate_department(department: str) -> str | None:
    normalized_department = department.strip()
    if len(normalized_department) > MAX_DEPARTMENT_LENGTH:
        raise click.UsageError(f"Department must be at most {MAX_DEPARTMENT_LENGTH} characters.")
    return normalized_department or None


def _validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise click.UsageError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return password


def register_cli(app):
    @app.cli.command("create-admin")
    def create_admin():
        """Create a local administrator account."""
        name = _validate_name(click.prompt("Name", type=str))
        email = _validate_email(click.prompt("Email", type=str))
        department = _validate_department(click.prompt("Department (optional)", default="", show_default=False, type=str))
        password = _validate_password(
            click.prompt("Password", hide_input=True, confirmation_prompt=True, type=str)
        )

        try:
            with get_db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM users WHERE email = %s LIMIT 1;",
                        (email,),
                    )
                    if cursor.fetchone() is not None:
                        raise click.ClickException("An account with this email already exists.")

                    password_hash = generate_password_hash(password)
                    cursor.execute(
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
                        VALUES (%s, %s, 'admin', %s, 'active', %s, false)
                        RETURNING id, name, email, role, status;
                        """,
                        (name, email, department, password_hash),
                    )
                    created_admin = cursor.fetchone()
                    if created_admin is None:
                        raise click.ClickException("Unable to create the administrator account.")
                connection.commit()
        except click.ClickException:
            raise
        except psycopg.Error:
            raise click.ClickException("Unable to create the administrator account.") from None

        click.echo("Admin account created successfully.")
        click.echo(f"Email: {created_admin[2]}")
