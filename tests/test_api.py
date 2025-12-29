"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client: TestClient):
        """Test health endpoint returns correct data."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["app_name"] == "Alima"
        assert data["version"] == "2.0.0"
        assert "environment" in data
        assert "replication_mode" in data


@pytest.mark.integration
class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint redirects to login page."""
        response = client.get("/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login"


@pytest.mark.integration
class TestDocumentation:
    """Test API documentation endpoints."""

    def test_openapi_schema(self, client: TestClient):
        """Test OpenAPI schema is accessible."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert schema["info"]["title"] == "Alima"

    def test_docs_endpoint(self, client: TestClient):
        """Test Swagger UI is accessible."""
        response = client.get("/docs")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_redoc_endpoint(self, client: TestClient):
        """Test ReDoc is accessible."""
        response = client.get("/redoc")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
