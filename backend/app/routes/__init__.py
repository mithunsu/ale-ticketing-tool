from app.routes.auth import auth_bp
from app.routes.admin_users import admin_users_bp
from app.routes.health import health_bp
from app.routes.tickets import tickets_bp

__all__ = ["admin_users_bp", "auth_bp", "health_bp", "tickets_bp"]
