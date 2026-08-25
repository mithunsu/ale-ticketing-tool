from copy import deepcopy

from flask import jsonify


VALIDATION_ERROR_MESSAGE = "The request contains invalid data."


def _error_payload(code: str, message: str, details=None) -> dict:
    payload = {
        "error": {
            "code": code,
            "message": message,
        }
    }

    if details is not None:
        payload["error"]["details"] = deepcopy(details)

    return payload


def error_response(code: str, message: str, status_code: int, details=None):
    return jsonify(_error_payload(code=code, message=message, details=details)), status_code


def validation_error_response(details=None):
    return error_response(
        code="VALIDATION_ERROR",
        message=VALIDATION_ERROR_MESSAGE,
        status_code=400,
        details=details,
    )


def success_response(payload: dict, status_code: int = 200):
    return jsonify(payload), status_code
