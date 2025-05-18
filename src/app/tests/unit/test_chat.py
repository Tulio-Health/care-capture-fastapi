import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from ..conftest import mock_redis

@pytest.fixture
def mock_intent_identifier():
    with patch("src.app.routes.chat.IntendIdentifierChain") as mock:
        instance = mock.return_value
        instance.identify_intent.return_value = "medical_inquiry"
        yield instance

@pytest.fixture
def mock_intent_router():
    with patch("src.app.routes.chat.IntentRouter") as mock:
        instance = mock.return_value
        instance.route.return_value = {
            "intent": "medical_inquiry",
            "response": "This is a test response",
            "confidence": 0.95
        }
        yield instance

def test_chat_endpoint_success(
    test_client: TestClient,
    mock_redis,
    mock_intent_identifier,
    mock_intent_router
):
    """Test successful chat endpoint call"""
    # Mock Redis response
    mock_redis.lrange.return_value = [
        "Previous message 1",
        "Previous message 2",
        "Visit summary"
    ]
    
    # Test request
    response = test_client.post(
        "/care-capture/ai-chat/",
        json={
            "conversation_id": "test-conv-123",
            "message": "What are my test results?"
        }
    )
    
    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "medical_inquiry"
    assert "response" in data
    assert "confidence" in data

def test_chat_endpoint_conversation_not_found(
    test_client: TestClient,
    mock_redis
):
    """Test chat endpoint with non-existent conversation"""
    # Mock Redis empty response
    mock_redis.lrange.return_value = []
    
    response = test_client.post(
        "/care-capture/ai-chat/",
        json={
            "conversation_id": "non-existent",
            "message": "Test message"
        }
    )
    
    assert response.status_code == 404
    assert "Conversation not found" in response.json()["detail"]

def test_chat_endpoint_invalid_request(test_client: TestClient):
    """Test chat endpoint with invalid request"""
    response = test_client.post(
        "/care-capture/ai-chat/",
        json={
            "message": "Missing conversation_id"
        }
    )
    
    assert response.status_code == 422  # Validation error 