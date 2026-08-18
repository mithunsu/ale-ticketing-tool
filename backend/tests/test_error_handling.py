import logging

from app import create_app


def test_unknown_route_returns_centralized_404_json_error():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.is_json is True
    assert response.headers.get("Content-Type", "").startswith("application/json")
    assert response.headers.get("X-Request-ID")

    payload = response.get_json()
    assert payload == {
        "error": {
            "code": "ROUTE_NOT_FOUND",
            "message": "The requested resource does not exist.",
        }
    }


def test_wrong_method_returns_centralized_405_json_error():
    app = create_app()

    with app.test_client() as client:
        response = client.post("/api/health")

    assert response.status_code == 405
    assert response.is_json is True
    assert response.headers.get("X-Request-ID")

    payload = response.get_json()
    assert payload == {
        "error": {
            "code": "METHOD_NOT_ALLOWED",
            "message": "The requested HTTP method is not allowed for this resource.",
        }
    }


def test_unexpected_exception_returns_sanitized_500_and_logs_details(caplog):
    app = create_app()
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/api/_test/unhandled-error")
    def _raise_unhandled_error():
        raise RuntimeError("simulated sensitive runtime error with token=do-not-return")

    caplog.set_level(logging.ERROR)

    with app.test_client() as client:
        response = client.get("/api/_test/unhandled-error")

    assert response.status_code == 500
    assert response.is_json is True
    assert response.headers.get("X-Request-ID")

    payload = response.get_json()
    assert payload == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred.",
        }
    }

    response_text = response.get_data(as_text=True)
    assert "simulated sensitive runtime error" not in response_text
    assert "RuntimeError" not in response_text
    assert "Traceback" not in response_text
    assert ".py" not in response_text

    assert "Unhandled exception while processing request" in caplog.text
    assert "RuntimeError: simulated sensitive runtime error with token=do-not-return" in caplog.text
    assert "Traceback (most recent call last)" in caplog.text