from app import create_app
from app.responses import (
    VALIDATION_ERROR_MESSAGE,
    error_response,
    success_response,
    validation_error_response,
)


def test_error_response_shape_and_status_code():
    app = create_app()

    with app.test_request_context():
        response, status_code = error_response(
            code="INVALID_JSON",
            message="The request body contains invalid JSON.",
            status_code=400,
        )

    assert status_code == 400
    assert response.is_json is True
    assert response.get_json() == {
        "error": {
            "code": "INVALID_JSON",
            "message": "The request body contains invalid JSON.",
        }
    }


def test_error_response_includes_optional_details_and_does_not_mutate_input():
    app = create_app()
    details = {
        "title": "This field is required.",
        "meta": {"source": "unit-test"},
    }

    with app.test_request_context():
        response, status_code = error_response(
            code="VALIDATION_ERROR",
            message=VALIDATION_ERROR_MESSAGE,
            status_code=400,
            details=details,
        )

    assert status_code == 400
    payload = response.get_json()
    assert payload == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": VALIDATION_ERROR_MESSAGE,
            "details": {
                "title": "This field is required.",
                "meta": {"source": "unit-test"},
            },
        }
    }

    assert details == {
        "title": "This field is required.",
        "meta": {"source": "unit-test"},
    }


def test_validation_error_response_defaults():
    app = create_app()

    with app.test_request_context():
        response, status_code = validation_error_response(details={"title": "This field is required."})

    assert status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": VALIDATION_ERROR_MESSAGE,
            "details": {"title": "This field is required."},
        }
    }


def test_success_response_shape_and_status_code():
    app = create_app()

    with app.test_request_context():
        response, status_code = success_response({"status": "ok"}, status_code=201)

    assert status_code == 201
    assert response.is_json is True
    assert response.get_json() == {"status": "ok"}
