"""
Orchestrator configuration
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Orchestrator service configuration"""
    
    # Service
    APP_NAME: str = "VAPT Orchestrator"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    
    # RabbitMQ / Celery
    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "admin"
    RABBITMQ_PASSWORD: str = "admin123"
    RABBITMQ_VHOST: str = "/"
    
    @property
    def CELERY_BROKER_URL(self) -> str:
        """Construct Celery broker URL"""
        return f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/{self.RABBITMQ_VHOST}"
    
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        """Construct Celery result backend URL"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    
    # PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "vapt_user"
    POSTGRES_PASSWORD: str = "vapt_password"
    POSTGRES_DB: str = "vapt_platform"
    
    @property
    def DATABASE_URL(self) -> str:
        """Construct database URL"""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Scan Configuration
    MAX_CONCURRENT_SCANS: int = 10
    SCAN_TIMEOUT_SECONDS: int = 3600  # 1 hour
    SCAN_RETRY_ATTEMPTS: int = 3
    SCAN_RESULT_RETENTION_DAYS: int = 90
    
    # Worker Configuration
    WORKER_TIMEOUT_SECONDS: int = 1800  # 30 minutes
    WORKER_HEALTH_CHECK_INTERVAL: int = 60
    WORKER_MAX_RETRIES: int = 3
    
    # Workflow Configuration
    WORKFLOW_STATE_PERSISTENCE: bool = True
    WORKFLOW_HISTORY_ENABLED: bool = True
    
    # Result Aggregation
    DEDUPLICATION_ENABLED: bool = True
    VULNERABILITY_SCORING_ENABLED: bool = True
    AUTO_TRIAGE_ENABLED: bool = False  # Requires AI engine
    
    # Feature Flags
    PARALLEL_SCAN_ENABLED: bool = True
    AI_ENHANCED_SCANNING: bool = False  # Phase 5
    REAL_TIME_UPDATES_ENABLED: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
