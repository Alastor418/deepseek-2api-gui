"""Тесты Pydantic-схем для API и GUI."""
import pytest
from pydantic import ValidationError

from app.schemas import AccountCreate, ChatCompletionRequest


def test_chat_request_requires_messages():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="deepseek-chat", messages=[])


def test_chat_request_rejects_bad_role():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            model="x",
            messages=[{"role": "boss", "content": "hi"}],
        )


def test_chat_request_accepts_allowed_roles():
    req = ChatCompletionRequest(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "tool", "content": "t", "tool_call_id": "1"},
        ],
    )
    assert len(req.messages) == 4
    assert req.stream is False


def test_chat_request_allows_extra_fields():
    req = ChatCompletionRequest.model_validate(
        {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "hi"}],
            "top_p": 0.9,
            "presence_penalty": 0.1,
        }
    )
    # extra=allow, значит поля доступны
    assert req.model_extra.get("top_p") == 0.9


def test_account_create_requires_min_length():
    with pytest.raises(ValidationError):
        AccountCreate(authorization="short")


def test_account_create_ok():
    a = AccountCreate(
        label="main",
        authorization="Bearer eyJ...",
        cookie="x=y",
    )
    assert a.label == "main"
