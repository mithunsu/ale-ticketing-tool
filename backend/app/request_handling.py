import logging
import time
import uuid

from flask import current_app, g, jsonify, request
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import InternalServerError, MethodNotAllowed, NotFound

from app.responses import error_response

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128


def _has_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _is_valid_request_id(value: str) -> bool:
    return bool(value) and len(value) <= MAX_REQUEST_ID_LENGTH and not _has_control_characters(value)


def _resolve_request_id() -> str:
    incoming_request_id = request.headers.get(REQUEST_ID_HEADER)

    if incoming_request_id is not None:
        candidate = incoming_request_id.strip()
        if _is_valid_request_id(candidate):
            return candidate

    return str(uuid.uuid4())


def _error_payload(code: str, message: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
        }
    }


def register_request_handling(app):
    if app.logger.getEffectiveLevel() > logging.INFO:
        app.logger.setLevel(logging.INFO)

    @app.before_request
    def _before_request():
        g.request_start_time = time.perf_counter()
        g.request_id = _resolve_request_id()

    @app.after_request
    def _after_request(response):
        request_id = getattr(g, "request_id", str(uuid.uuid4()))
        response.headers[REQUEST_ID_HEADER] = request_id

        start = getattr(g, "request_start_time", None)
        if start is None:
            duration_ms = 0.0
        else:
            duration_ms = (time.perf_counter() - start) * 1000

        remote_ip = request.remote_addr
        if remote_ip:
            current_app.logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%.2f ip=%s",
                request_id,
                request.method,
                request.path,
                response.status_code,
                duration_ms,
                remote_ip,
            )
        else:
            current_app.logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
                request_id,
                request.method,
                request.path,
                response.status_code,
                duration_ms,
            )

        return response

    @app.errorhandler(NotFound)
    def _handle_not_found(_error):
        return jsonify(
            _error_payload(
                "ROUTE_NOT_FOUND",
                "The requested resource does not exist.",
            )
        ), 404

    @app.errorhandler(CSRFError)
    def _handle_csrf_error(_error):
        return error_response(
            code="CSRF_TOKEN_INVALID",
            message="The CSRF token is missing or invalid.",
            status_code=403,
        )

    @app.errorhandler(MethodNotAllowed)
    def _handle_method_not_allowed(_error):
        return jsonify(
            _error_payload(
                "METHOD_NOT_ALLOWED",
                "The requested HTTP method is not allowed for this resource.",
            )
        ), 405

    @app.errorhandler(InternalServerError)
    def _handle_internal_server_error(error):
        original_exception = getattr(error, "original_exception", None)

        if original_exception is not None:
            current_app.logger.error(
                "Unhandled exception while processing request",
                exc_info=(
                    type(original_exception),
                    original_exception,
                    original_exception.__traceback__,
                ),
            )
        else:
            current_app.logger.error("Unhandled internal server error without original exception")

        return jsonify(
            _error_payload(
                "INTERNAL_SERVER_ERROR",
                "An unexpected server error occurred.",
            )
        ), 500