"""Pydantic-схемы для входных запросов API и GUI."""
from typing import Any, Literal

from pydantic import BaseModel, Field


# ============================================================
# Chat completions (OpenAI-совместимый)
# ============================================================
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[Any] | None = None
    name: str | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any | None = None
    temperature: float | None = None
    max_tokens: int | None = None

    model_config = {"extra": "allow"}


# ============================================================
# GUI: аккаунты
# ============================================================
class AccountCreate(BaseModel):
    label: str = ""
    authorization: str = Field(min_length=8)
    cookie: str = ""


class AccountLabelUpdate(BaseModel):
    label: str = ""
