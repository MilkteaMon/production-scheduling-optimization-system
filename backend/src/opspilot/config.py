from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", case_sensitive=False)
    database_url: str = f"sqlite:///{(ROOT / 'runtime' / 'opspilot.db').as_posix()}"
    ai_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = ""
    cbc_path: str = ""
    openai_agents_disable_tracing: bool = True
    queue_limit: int = 10
    frontend_dist: Path = ROOT / "frontend" / "dist"

    @property
    def ai_available(self):
        return self.ai_enabled and bool(self.openai_api_key and self.openai_model)
