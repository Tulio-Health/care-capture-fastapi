import pytest
from fastapi.testclient import TestClient
from typing import Generator
from ..main import app
from ..db.config.database import engine
from ..db.objects.entities.users import Base

@pytest.fixture(scope="session")
def test_client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI application"""
    with TestClient(app) as client:
        yield client

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Set up test database and clean up after tests"""
    # Create test database tables
    Base.metadata.create_all(bind=engine)
    
    yield
    
    # Clean up after tests
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def mock_redis():
    """Mock Redis client for testing"""
    class MockRedis:
        def __init__(self):
            self.cache = {}
        
        async def get(self, key: str) -> str:
            return self.cache.get(key)
        
        async def set(self, key: str, value: str, ex: int = None) -> bool:
            self.cache[key] = value
            return True
        
        async def delete(self, key: str) -> bool:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
        
        async def close(self):
            self.cache.clear()
    
    return MockRedis() 