"""Entry point to run the Flask application."""
import os

from app import create_app


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}

if __name__ == '__main__':
    app = create_app()
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = _to_bool(os.getenv("FLASK_DEBUG", "false"))

    app.run(host=host, port=port, debug=debug)
