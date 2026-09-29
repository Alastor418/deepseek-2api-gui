from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DATA_DIR = Path.home() / ".deepseek-2api"
DATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Deepseek-2api GUI"
    APP_VERSION: str = "3.3.1"

    GUI_HOST: str = "127.0.0.1"
    GUI_PORT: int = 8080

    API_MASTER_KEY: str | None = None

    SUPPORTED_MODELS: list[str] = ["deepseek-chat", "deepseek-reasoner"]

    MODEL_ALIASES: dict[str, dict[str, object]] = {}

    REQUEST_TIMEOUT: float = 300.0
    POW_TIMEOUT: float = 60.0

    AUTO_RELOGIN: bool = True
    MAX_RETRIES: int = 2
    AUTO_RELOGIN_TIMEOUT: int = 180

    # Если клиент (например, Harness) посылает tools с именем web_search —
    # автоматически включать search_enabled у Deepseek. Отключи, если
    # хочешь, чтобы модель отвечала из своего знания.
    AUTO_WEB_SEARCH: bool = True

    # Жёстко включить глубокое мышление (reasoning_content) ВСЕГДА,
    # независимо от того, что просит клиент. Медленнее, но всегда
    # с цепочкой размышлений.
    FORCE_THINKING: bool = False

    # Жёстко включить веб-поиск DeepSeek ВСЕГДА. Каждый запрос идёт
    # через поиск, даже простой «привет». Медленнее, но всегда
    # с актуальной информацией.
    FORCE_SEARCH: bool = False

    LOG_TO_FILE: bool = True
    LOG_ROTATION_MB: int = 10
    LOG_RETENTION: int = 5


settings = Settings()


class RuntimeState:
    """Мутабельное состояние процесса."""

    def __init__(self) -> None:
        self.login_in_progress: bool = False


state = RuntimeState()
