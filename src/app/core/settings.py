from pydantic_settings import BaseSettings
from pydantic import PostgresDsn, ValidationError
from functools import lru_cache
import os
import logging

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    
    # API Configuration
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    
    # Database Configuration
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432  # Hardcoded port number
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str = "care-capture-app"
    DB_SSL: bool = False
    
    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ''
    
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
            
            # Construct the URL string directly
            url_str = f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:5432/{self.DB_NAME}"
            
            # Validate the URL
            url = PostgresDsn(url_str)
            
            logger.info(f"Constructed DATABASE_URL: {url}")
            return url
            
        except ValidationError as e:
            logger.error(f"Database URL validation error: {str(e)}")
            raise ValueError(f"Invalid database URL configuration: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error constructing database URL: {str(e)}")
            raise
    
    # API Keys
    OPENAI_API_KEY: str
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()