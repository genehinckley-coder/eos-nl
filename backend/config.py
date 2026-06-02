from pydantic_settings import BaseSettings, SettingsConfigDict
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # EOS console connection
    eos_host: str = "127.0.0.1"
    eos_port: int = 3032

    # Ollama
    ollama_url: str = "http://localhost:11434"
    model_name: str = "eos-nl:v4"

    # Safety
    block_destructive: bool = True

    # Web server
    server_host: str = "127.0.0.1"
    server_port: int = 8080


settings = Settings()

if not settings.eos_host:
    logger.warning(
        "EOS_HOST is not configured. OSC sends will return sent=false. "
        "Set EOS_HOST in .env to enable console dispatch."
    )
