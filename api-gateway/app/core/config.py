"""
Core configuration for VAPT Platform API Gateway
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "VAPT Platform API"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    
    # Security
    SECRET_KEY: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database
    DATABASE_URL: str
    DB_ECHO: bool = False
    
    # Redis
    REDIS_URL: str
    
    # RabbitMQ / Celery
    RABBITMQ_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str = "rpc://"
    
    # Elasticsearch
    ELASTICSEARCH_URL: str
    
    # MinIO / Object Storage
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_SECURE: bool = False
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"
    
    @validator("CORS_ORIGINS")
    def parse_cors_origins(cls, v: str) -> List[str]:
        """Parse comma-separated CORS origins"""
        return [origin.strip() for origin in v.split(",")]
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_PER_MINUTE_UNAUTH: int = 20
    
    # Multi-tenancy
    MULTI_TENANT_ENABLED: bool = True
    TENANT_ISOLATION_STRATEGY: str = "schema"  # schema, database, discriminator
    DEFAULT_TENANT_ID: str = "default"
    
    # LLM Configuration (for AI agents)
    LLM_PROVIDER: str = "ollama"
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    LLM_FALLBACK_ENABLED: bool = True
    
    # Feature Flags
    FEATURE_AI_AGENTS_ENABLED: bool = True
    FEATURE_AUTO_EXPLOITATION_ENABLED: bool = False
    FEATURE_CLOUD_SCANNING_ENABLED: bool = True
    FEATURE_API_RATE_LIMITING_ENABLED: bool = True
    FEATURE_AUDIT_LOGGING_ENABLED: bool = True
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Scan Configuration
    MAX_CONCURRENT_SCANS_PER_TENANT: int = 5
    SCAN_RESULT_RETENTION_DAYS: int = 90
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
