from flask import Flask


def create_app():
    """Application factory for creating Flask app instance."""
    app = Flask(__name__)

    # Register blueprints
    from app.routes.health import health_bp
    app.register_blueprint(health_bp)

    return app
