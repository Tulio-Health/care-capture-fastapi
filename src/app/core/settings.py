import urllib.parse
from pydantic_settings import BaseSettings
from pydantic import PostgresDsn, ValidationError, Field, validator
from functools import lru_cache
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    
    # API Configuration
    APP_ENV: str = Field(default="development", pattern="^(development|production)$")
    DEBUG: bool = True
    PORT: int = Field(default=8000, ge=1, le=65535)
    
    # Environment Detection
    AWS_REGION: str = Field(default="us-east-2", min_length=1)
    
    # Database Configuration
    DB_HOST: str = Field(default="localhost", min_length=1)
    DB_PORT: int = Field(default=5432, ge=1, le=65535)
    DB_USER: str = Field(default="", min_length=0)
    DB_PASSWORD: str = Field(default="", min_length=0)
    DB_NAME: str = Field(default="care-capture-app", min_length=1)
    DB_SSL: bool = False
    
    # Redis Configuration
    REDIS_HOST: str = Field(default="localhost", min_length=1)
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535)
    REDIS_PASSWORD: str = ""
    
    # External Services
    OPENAI_API_KEY: str = ""
    
    # Clerk Authentication
    CLERK_PUBLIC_JWT_KEY: str = ""
    CLERK_SECRET_KEY: str = ""
    CLERK_PUBLISHABLE_KEY: str = ""
    
    @validator('OPENAI_API_KEY')
    def validate_openai_key(cls, v):
        if v and not v.startswith('sk-'):
            logger.warning("⚠️ OpenAI API key format may be invalid (should start with 'sk-')")
        return v
    
    @validator('DB_HOST')
    def validate_db_host(cls, v):
        if not v and os.getenv('APP_ENV') == 'production':
            raise ValueError('DB_HOST is required in production')
        return v
    
    @validator('DB_USER')
    def validate_db_user(cls, v):
        if not v and os.getenv('APP_ENV') == 'production':
            raise ValueError('DB_USER is required in production')
        return v
    
    @validator('DB_PASSWORD')
    def validate_db_password(cls, v):
        if not v and os.getenv('APP_ENV') == 'production':
            raise ValueError('DB_PASSWORD is required in production')
        return v
    
    # LangSmith (optional)
    LANGSMITH_TRACING: str = ""
    LANGSMITH_ENDPOINT: str = ""
    LANGSMITH_PROJECT: str = ""
    LANGSMITH_API_KEY: str = ""
    
    @property
    def DATABASE_URL(self) -> PostgresDsn:
        try:
            # First try to get from environment variable
            if db_url := os.getenv("DATABASE_URL"):
                logger.info("Using DATABASE_URL from environment variable")
                return PostgresDsn(db_url)
            
            # If not in env, construct from components
            logger.info("Constructing DATABASE_URL from components")
            logger.info(f"DB_HOST: {self.DB_HOST}")
            logger.info(f"DB_PORT: {self.DB_PORT}")
            logger.info(f"DB_USER: {self.DB_USER}")
            logger.info(f"DB_NAME: {self.DB_NAME}")

            encoded_password = urllib.parse.quote_plus(self.DB_PASSWORD)
            
            # Construct the URL string directly
            # url_str = f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:5432/{self.DB_NAME}"
            url_str = f"postgresql+asyncpg://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            
            # Validate the URL
            url = PostgresDsn(url_str)
            
            logger.info("Database URL constructed successfully")
            return url
            
        except ValidationError as e:
            logger.error(f"Database URL validation error: {str(e)}")
            raise ValueError(f"Invalid database URL configuration: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error constructing database URL: {str(e)}")
            raise
    
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()