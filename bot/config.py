from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def _parse_admin_ids(value: str) -> list[int]:
    if not value:
        return []
    result = []
    for part in str(value).replace(" ", "").split(","):
        if part.isdigit():
            result.append(int(part))
    return result


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str = ""
    admin_ids_raw: str = ""
    mini_app_url: str = "https://cryptopassapp.github.io/CryptoPassApp/"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "change_me"

    # TonAPI
    ton_api_key: str = ""

    # Database
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'cryptopass.db'}"

    # Demo Mode
    demo_mode: bool = False

    # Dev: отключает проверку initData для локальных тестов.
    # НИКОГДА не включай в проде — API станет доступен без авторизации.
    dev_bypass_auth: bool = False

    @property
    def admin_ids(self) -> list[int]:
        return _parse_admin_ids(self.admin_ids_raw)


settings = Settings()

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
