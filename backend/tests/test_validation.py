import logging

from flask import jsonify, request

from app import create_app
from app.responses import validation_error_response
from app.validation import parse_json_request, validate_object


TICKET_SCHEMA = {
    "title": {
        "required": True,
        "type": str,
        "min_length": 1,
        "max_length": 150,
    },
    "description": {
        "required": True,
        "type": str,
        "min_length": 1,
        "max_length": 5000,
    },
    "priority": {
        "required": True,
        "type": str,
        "allowed": ["low", "medium", "high", "critical"],
    },
}


def _create_validation_test_app():
    app = create_app()

    @app.post("/api/_test/parse-json")
    def _parse_json_route():
        payload, error = parse_json_request(request)
        if error is not None:
            return error

        return jsonify({"ok": True, "payload": payload}), 200

    @app.post("/api/_test/validate")
    def _validate_route():
        payload, error = parse_json_request(request)
        if error is not None:
            return error

        strict = request.args.get("strict", "true").lower() != "false"
        normalized, errors = validate_object(payload, TICKET_SCHEMA, strict=strict)
        if errors is not None:
            return validation_error_response(details=errors)

        return jsonify({"ok": True, "payload": normalized}), 200

    return app


def test_missing_content_type_returns_invalid_content_type():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post("/api/_test/parse-json", data='{"title": "A"}')

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "INVALID_CONTENT_TYPE",
            "message": "Content-Type must be application/json.",
        }
    }


def test_malformed_json_returns_invalid_json():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/parse-json",
            data='{"title": ',
            content_type="application/json",
        )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "INVALID_JSON",
            "message": "The request body contains invalid JSON.",
        }
    }


def test_empty_json_body_returns_empty_json_body_error():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/parse-json",
            data="",
            content_type="application/json",
        )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "EMPTY_JSON_BODY",
            "message": "The request body must not be empty.",
        }
    }


def test_json_array_root_returns_invalid_json_object_error():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/parse-json",
            json=["not", "an", "object"],
        )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "INVALID_JSON_OBJECT",
            "message": "The request body must be a JSON object.",
        }
    }


def test_valid_json_object_parsing_succeeds():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/parse-json",
            json={"title": "A"},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "payload": {"title": "A"},
    }


def test_required_field_missing_returns_validation_error():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/validate",
            json={"description": "Desc", "priority": "low"},
        )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.get_json()["error"]["details"]["title"] == "This field is required."


def test_required_string_whitespace_only_is_rejected():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/validate",
            json={"title": "   ", "description": "Desc", "priority": "low"},
        )

    assert response.status_code == 400
    assert response.get_json()["error"]["details"]["title"] == "This field is required."


def test_wrong_python_type_is_rejected():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/validate",
            json={"title": 123, "description": "Desc", "priority": "low"},
        )

    assert response.status_code == 400
    assert response.get_json()["error"]["details"]["title"] == "Expected type: str."


def test_string_shorter_than_min_length_is_rejected():
    app = _create_validation_test_app()

    schema = {
        "title": {
            "required": True,
            "type": str,
            "min_length": 2,
        }
    }
    normalized, errors = validate_object({"title": "a"}, schema)

    assert normalized is None
    assert errors == {"title": "Must be at least 2 characters."}


def test_string_longer_than_max_length_is_rejected():
    app = _create_validation_test_app()

    schema = {
        "title": {
            "required": True,
            "type": str,
            "max_length": 3,
        }
    }
    normalized, errors = validate_object({"title": "abcd"}, schema)

    assert normalized is None
    assert errors == {"title": "Must be at most 3 characters."}


def test_invalid_allowed_value_is_rejected():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/validate",
            json={"title": "A", "description": "Desc", "priority": "urgent"},
        )

    assert response.status_code == 400
    assert response.get_json()["error"]["details"]["priority"] == (
        "Value must be one of: low, medium, high, critical."
    )


def test_optional_field_omitted_is_allowed():
    schema = {
        "title": {"required": True, "type": str, "min_length": 1},
        "description": {"required": False, "type": str, "min_length": 1},
    }

    normalized, errors = validate_object({"title": "A"}, schema)

    assert errors is None
    assert normalized == {"title": "A"}


def test_valid_input_succeeds_and_trims_strings():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response_ok = client.post(
            "/api/_test/validate",
            json={
                "title": "  Hello  ",
                "description": "  world with  internal spaces  ",
                "priority": " high ",
            },
        )

    assert response_ok.status_code == 200
    assert response_ok.get_json()["payload"] == {
        "title": "Hello",
        "description": "world with  internal spaces",
        "priority": "high",
    }


def test_multiple_invalid_fields_return_multiple_details_without_echoing_values():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/validate",
            json={
                "title": " ",
                "description": "",
                "priority": "super-secret-priority",
            },
        )

    assert response.status_code == 400
    payload = response.get_json()
    details = payload["error"]["details"]
    assert "title" in details
    assert "description" in details
    assert "priority" in details

    payload_text = str(payload)
    assert "super-secret-priority" not in payload_text


def test_strict_mode_rejects_unknown_field():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/validate",
            json={
                "title": "A",
                "description": "Desc",
                "priority": "low",
                "spoofed": "value",
            },
        )

    assert response.status_code == 400
    assert response.get_json()["error"]["details"]["spoofed"] == "Unknown field."


def test_strict_false_allows_unknown_field():
    app = _create_validation_test_app()

    with app.test_client() as client:
        response = client.post(
            "/api/_test/validate?strict=false",
            json={
                "title": "A",
                "description": "Desc",
                "priority": "low",
                "spoofed": "value",
            },
        )

    assert response.status_code == 200
    assert response.get_json()["payload"]["spoofed"] == "value"


def test_validation_error_responses_include_request_id_and_are_logged(caplog):
    app = _create_validation_test_app()
    caplog.set_level(logging.INFO)

    with app.test_client() as client:
        response = client.post(
            "/api/_test/validate",
            data="",
            content_type="application/json",
            headers={"X-Request-ID": "req-validation-1"},
        )

    assert response.status_code == 400
    assert response.headers.get("X-Request-ID") == "req-validation-1"

    request_logs = [
        record.getMessage()
        for record in caplog.records
        if "path=/api/_test/validate" in record.getMessage()
    ]

    assert len(request_logs) == 1
    assert "method=POST" in request_logs[0]
    assert "status=400" in request_logs[0]
    assert "request_id=req-validation-1" in request_logs[0]
    assert "duration_ms=" in request_logs[0]
