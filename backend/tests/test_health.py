from app import create_app


def test_health_endpoint_returns_expected_payload():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.is_json is True

    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["message"] == "ALE Ticket Management API is running"
