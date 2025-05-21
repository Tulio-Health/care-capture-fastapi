import pytest
from fastapi.testclient import TestClient

def test_health_check(test_client: TestClient):
    """Test the health check endpoint"""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "message" in data
    assert "version" in data["data"] 