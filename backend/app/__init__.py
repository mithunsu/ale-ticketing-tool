import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS


BACKEND_DIR = Path(__file__).resolve().parent.parent
LOCAL_ENV_FILE = BACKEND_DIR / ".env"
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5173"]


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

    app = Flask(__name__)
    allowed_origins = parse_allowed_origins()

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": allowed_origins,
                "supports_credentials": True,
                "allow_headers": ["Content-Type", "Authorization", "X-Request-ID"],
                "methods": ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                "expose_headers": ["X-Request-ID"],
                "always_send": False,
            }
        },
    )

    from app.request_handling import register_request_handling

    register_request_handling(app)

    # Register blueprints
    from app.routes import health_bp

    app.register_blueprint(health_bp)

    return app
