import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect


BACKEND_DIR = Path(__file__).resolve().parent.parent
LOCAL_ENV_FILE = BACKEND_DIR / ".env"
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5173"]
csrf = CSRFProtect()


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_allowed_origins():
    """Return a sanitized list of trusted frontend origins from the environment."""
    configured_value = os.getenv("CORS_ALLOWED_ORIGINS")
    if configured_value is None or not configured_value.strip():
        return list(DEFAULT_ALLOWED_ORIGINS)

    origins = []
    for value in configured_value.split(","):
        candidate = value.strip()
        if candidate:
            origins.append(candidate)

    return origins if origins else list(DEFAULT_ALLOWED_ORIGINS)


def create_app():
    """Application factory for creating Flask app instance."""
    # Load local backend env defaults while preserving existing process env.
    load_dotenv(LOCAL_ENV_FILE, override=False)

    secret_key = os.getenv("FLASK_SECRET_KEY")
    if not secret_key or not secret_key.strip():
        raise RuntimeError(
            "FLASK_SECRET_KEY is required. Set it in backend/.env or the environment before starting the app."
        )

    app = Flask(__name__)
    app.config["SECRET_KEY"] = secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = _parse_bool(os.getenv("SESSION_COOKIE_SECURE"), default=False)
    app.config["WTF_CSRF_HEADERS"] = ["X-CSRF-Token"]
    allowed_origins = parse_allowed_origins()

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": allowed_origins,
                "supports_credentials": True,
                "allow_headers": ["Content-Type", "Authorization", "X-Request-ID", "X-CSRF-Token"],
                "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                "expose_headers": ["X-Request-ID"],
                "always_send": False,
            }
        },
    )

    from app.request_handling import register_request_handling

    register_request_handling(app)
    csrf.init_app(app)

    from app.cli import register_cli

    register_cli(app)

    # Register blueprints
    from app.routes import admin_users_bp, auth_bp, health_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_users_bp)

    return app
