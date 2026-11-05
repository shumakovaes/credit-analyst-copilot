from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class Chart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["none", "bar", "line"]
    x: str | None
    y: str | None


class Plan(BaseModel):
    """Only the requested query and a short description; no private reasoning."""
    model_config = ConfigDict(extra="forbid")
    action: Literal["query", "clarify", "refuse"]
    sql: str | None
    message: str
    chart: Chart


class Ask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None
