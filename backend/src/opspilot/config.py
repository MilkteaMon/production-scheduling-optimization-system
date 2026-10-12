from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", case_sensitive=False)
    database_url: str = f"sqlite:///{(ROOT / 'runtime' / 'opspilot.db').as_posix()}"
    ai_enabled: bool = False
    ai_provider: Literal["openai_api", "codex_subscription"] = "openai_api"
    codex_path: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    cbc_path: str = ""
    openai_agents_disable_tracing: bool = True
    queue_limit: int = 10
    frontend_dist: Path = ROOT / "frontend" / "dist"

    @property
    def ai_available(self):
        if self.ai_provider == "codex_subscription":
            from opspilot.agents.codex_subscription import codex_executable, subscription_signed_in

            executable = codex_executable(self.codex_path)
            return bool(
                self.ai_enabled
                and self.openai_model
                and executable
                and subscription_signed_in(executable)
            )
        return self.ai_enabled and bool(self.openai_api_key and self.openai_model)
