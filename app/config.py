"""Configuration settings for Admin Service"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Service info
    SERVICE_NAME: str = "htpi-admin-service"
    VERSION: str = "1.0.0"
    
    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    
    # NATS configuration
    NATS_URL: str = "nats://localhost:4222"
    NATS_USER: str = "admin_user"
    NATS_PASS: str = ""
    
    # JWT configuration
    JWT_SECRET: str = "your-secret-key-here"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_DELTA: int = 3600  # 1 hour
    
    # Service URLs (for direct communication if needed)
    GATEWAY_URL: str = "http://localhost:8000"
    
    # Admin settings
    SUPER_ADMIN_EMAIL: str = "admin@htpi.com"
    DEFAULT_ADMIN_PASSWORD: str = "changeme123"
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 200
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 300
    RATE_LIMIT_PER_HOUR: int = 10000
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()