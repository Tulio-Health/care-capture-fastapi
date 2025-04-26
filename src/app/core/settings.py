from pydantic_settings import BaseSettings
from pydantic import PostgresDsn
from functools import lru_cache

class Settings(BaseSettings):
    
    # API Configuration
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    
    # Database Configuration
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
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
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            path=self.DB_NAME,
            
        )
    
    # API Keys
    OPENAI_API_KEY: str
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()