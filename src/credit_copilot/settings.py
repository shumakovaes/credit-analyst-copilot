from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COPILOT_", env_file=".env", extra="ignore")
    database_url: SecretStr = SecretStr("postgresql://credit_copilot_reader:reader_local@localhost:5434/copilot")
    provider: Literal["demo", "live"] = "demo"
    llm_api_style: Literal["chat_completions", "responses"] = "chat_completions"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_seconds: float = Field(20, ge=1, le=30)
    audit_path: str = "runtime/audit.sqlite3"
    max_rows: int = Field(200, ge=1, le=500)
    max_attempts: int = Field(3, ge=1, le=3)
    statement_timeout_ms: int = Field(1500, ge=100, le=5000)
    max_plan_cost: float = Field(100000, gt=0, le=1_000_000)
    max_result_bytes: int = Field(200000, ge=1000, le=1000000)
