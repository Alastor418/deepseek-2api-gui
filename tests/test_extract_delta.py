"""Тесты парсера JSON-Patch стрима Deepseek.

Фикстуры чанков взяты из реального трафика chat.deepseek.com (см. docs/ARCHITECTURE.md).
"""
from app.providers.deepseek import DeepseekProvider, _StreamState


def _d(chunk, state):
    return DeepseekProvider._extract_delta(chunk, state)


def test_fragments_array_with_think_and_response():
    state = _StreamState()
    chunk = {
        "p": "response/fragments",
        "o": "APPEND",
        "v": [
            {"type": "THINK", "content": "думаю"},
            {"type": "RESPONSE", "content": "ответ"},
        ],
    }
    d = _d(chunk, state)
    assert d["reasoning"] == "думаю"
    assert d["content"] == "ответ"


def test_append_to_last_fragment():
    state = _StreamState()
    _d(
        {
            "p": "response/fragments",
            "o": "APPEND",
            "v": [
                {"type": "THINK", "content": "T"},
                {"type": "RESPONSE", "content": "R"},
            ],
        },
        state,
    )
    # -1 → последний фрагмент (RESPONSE)
    d = _d(
        {"p": "response/fragments/-1/content", "o": "APPEND", "v": "!"},
        state,
    )
    assert d["content"] == "!"
    assert d["reasoning"] is None

    # -2 → предпоследний (THINK)
    d = _d(
        {"p": "response/fragments/-2/content", "o": "APPEND", "v": "?"},
        state,
    )
    assert d["reasoning"] == "?"
    assert d["content"] is None


def test_plain_string_goes_to_response_by_default():
    state = _StreamState()
    d = _d({"v": "текст"}, state)
    assert d == {"content": "текст", "reasoning": None}


def test_plain_string_goes_to_reasoning_after_think():
    state = _StreamState()
    _d(
        {
            "p": "response/fragments",
            "o": "APPEND",
            "v": [{"type": "THINK", "content": "x"}],
        },
        state,
    )
    d = _d({"v": "y"}, state)
    assert d == {"content": None, "reasoning": "y"}


def test_full_object_first_chunk():
    state = _StreamState()
    chunk = {
        "v": {
            "response": {
                "fragments": [
                    {"type": "RESPONSE", "content": "hello"},
                ]
            }
        }
    }
    d = _d(chunk, state)
    assert d["content"] == "hello"
    assert d["reasoning"] is None


def test_empty_chunk_returns_none_none():
    state = _StreamState()
    d = _d({}, state)
    assert d == {"content": None, "reasoning": None}


def test_non_dict_fragment_in_array_is_skipped():
    state = _StreamState()
    chunk = {
        "p": "response/fragments",
        "o": "APPEND",
        "v": ["garbage", {"type": "RESPONSE", "content": "ok"}],
    }
    d = _d(chunk, state)
    assert d["content"] == "ok"


def test_missing_content_field_ignored():
    state = _StreamState()
    chunk = {
        "p": "response/fragments",
        "o": "APPEND",
        "v": [{"type": "RESPONSE"}],
    }
    d = _d(chunk, state)
    assert d == {"content": None, "reasoning": None}


def test_resolve_index_negative_without_fragments():
    state = _StreamState()
    # Нет зарегистрированных фрагментов, -1 разрешается в -1 → нет типа → RESPONSE
    d = _d(
        {"p": "response/fragments/-1/content", "o": "APPEND", "v": "x"},
        state,
    )
    # fallback — RESPONSE
    assert d["content"] == "x"
