from __future__ import annotations

from collections.abc import Mapping

from flask import Request
from werkzeug.exceptions import BadRequest

from app.responses import error_response


INVALID_CONTENT_TYPE_CODE = "INVALID_CONTENT_TYPE"
INVALID_JSON_CODE = "INVALID_JSON"
EMPTY_JSON_BODY_CODE = "EMPTY_JSON_BODY"
INVALID_JSON_OBJECT_CODE = "INVALID_JSON_OBJECT"


def parse_json_request(req: Request):
    if req.mimetype != "application/json":
        return None, error_response(
            code=INVALID_CONTENT_TYPE_CODE,
            message="Content-Type must be application/json.",
            status_code=400,
        )

    raw_body = req.get_data(cache=True)
    if raw_body.strip() == b"":
        return None, error_response(
            code=EMPTY_JSON_BODY_CODE,
            message="The request body must not be empty.",
            status_code=400,
        )

    try:
        payload = req.get_json(silent=False)
    except BadRequest:
        return None, error_response(
            code=INVALID_JSON_CODE,
            message="The request body contains invalid JSON.",
            status_code=400,
        )

    if not isinstance(payload, dict):
        return None, error_response(
            code=INVALID_JSON_OBJECT_CODE,
            message="The request body must be a JSON object.",
            status_code=400,
        )

    return payload, None


def _type_name(value_type) -> str:
    return getattr(value_type, "__name__", str(value_type))


def validate_object(data: Mapping, schema: Mapping, strict: bool = True):
    errors = {}
    normalized = {}

    for field_name, rules in schema.items():
        required = rules.get("required", False)
        has_value = field_name in data

        if not has_value:
            if required:
                errors[field_name] = "This field is required."
            continue

        value = data[field_name]
        expected_type = rules.get("type")

        if expected_type is not None and not isinstance(value, expected_type):
            errors[field_name] = f"Expected type: {_type_name(expected_type)}."
            continue

        if isinstance(value, str) and rules.get("strip", True):
            value = value.strip()

        if required and isinstance(value, str) and value == "":
            errors[field_name] = "This field is required."
            continue

        min_length = rules.get("min_length")
        if min_length is not None and isinstance(value, str) and len(value) < min_length:
            errors[field_name] = f"Must be at least {min_length} characters."
            continue

        max_length = rules.get("max_length")
        if max_length is not None and isinstance(value, str) and len(value) > max_length:
            errors[field_name] = f"Must be at most {max_length} characters."
            continue

        allowed_values = rules.get("allowed")
        if allowed_values is not None and value not in allowed_values:
            allowed = ", ".join(str(item) for item in allowed_values)
            errors[field_name] = f"Value must be one of: {allowed}."
            continue

        normalized[field_name] = value

    if strict:
        for field_name in data:
            if field_name not in schema:
                errors[field_name] = "Unknown field."
    else:
        for field_name, value in data.items():
            if field_name not in schema:
                normalized[field_name] = value

    if errors:
        return None, errors

    return normalized, None
