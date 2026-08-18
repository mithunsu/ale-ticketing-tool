from pathlib import Path

from dotenv import load_dotenv
from flask import Flask


BACKEND_DIR = Path(__file__).resolve().parent.parent
LOCAL_ENV_FILE = BACKEND_DIR / ".env"


def create_app():
    """Application factory for creating Flask app instance."""
    # Load local backend env defaults while preserving existing process env.
    load_dotenv(LOCAL_ENV_FILE, override=False)

    app = Flask(__name__)

    from app.request_handling import register_request_handling

    register_request_handling(app)

    # Register blueprints
    from app.routes import health_bp

    app.register_blueprint(health_bp)

    return app
