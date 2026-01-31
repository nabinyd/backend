import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    flask_env: str = os.getenv("FLASK_ENV", "development")
    secret_key: str = os.getenv("SECRET_KEY", "change-me")
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "5000"))
    telemetry_rate_limit_hz: int = int(os.getenv("TELEMETRY_RATE_LIMIT_HZ", "10"))

settings = Settings()
