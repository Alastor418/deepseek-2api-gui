"""Мост между OpenAI tool_calls и текстовой имитацией DeepSeek."""
import json
import re
import uuid
from typing import Any

# ---------------------------------------------------------------
# Regex-парсеры. Работают с СЫРЫМ текстом, включая DSML-маркеры.
# ---------------------------------------------------------------

# OpenAI-стиль: <tool_call>{"name": ...}</tool_call>
_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)

# Anthropic-стиль с любыми префиксами (|DSML|, | |DSML| |, ничего):
#   <| |DSML| |invoke name="write"><| |DSML| |parameter name="x">v</...invoke>
_INVOKE_RE = re.compile(
    r"<[^<>]*?invoke\s+name=[\"']([^\"']+)[\"'][^>]*>(.*?)</[^<>]*?invoke>",
    re.DOTALL | re.IGNORECASE,
)

# <parameter name="x" string="true|false">value</parameter>
_PARAM_RE = re.compile(
    r"<[^<>]*?parameter\s+name=[\"']([^\"']+)[\"']"
    r"(?:\s+string=[\"']([^\"']+)[\"'])?[^>]*>(.*?)</[^<>]*?parameter>",
    re.DOTALL | re.IGNORECASE,
)

# DSML-мусор для очистки вывода (когда уже всё распарсили)
_DSML_JUNK_RE = re.compile(
    r"<\|+\s*DSML\s*\|+[^>]*>|</?\|+\s*DSML\s*\|+[^>]*>|"
    r"\|+\s*DSML\s*\|+",
    re.IGNORECASE,
)


TOOL_CALL_FORMAT = (
    "When you need to use a tool, output EXACTLY this on its own line, "
    "with no other text in the same message:\n\n"
    '<tool_call>{"name": "TOOL_NAME", "arguments": {"arg": "value"}}</tool_call>\n\n'
    "CRITICAL RULES:\n"
    "- Output only ONE <tool_call> block per response\n"
    "- The content between <tool_call> and </tool_call> MUST be valid JSON\n"
    "- Use SINGLE curly braces { and } — do NOT double them\n"
    "- Do NOT wrap it in markdown code fences\n"
    "- Do NOT add explanation around the tool_call block\n"
    "- When no tool is needed, respond normally as text"
)


# ---------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------
def _strip_dsml_junk(text: str) -> str:
    """Убирает DSML-мусор. Только для вывода — НЕ для парсинга."""
    if not text:
        return text
    return _DSML_JUNK_RE.sub("", text).strip()


def _format_tools_description(tools: list[dict[str, Any]]) -> str:
    """Компактное описание — только имя, краткое описание и required-параметры.

    Полная JSON-схема раздувает промпт в 10 раз и сбивает DeepSeek.
    """
    lines = ["Available tools:"]
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") or {}
        name = fn.get("name") or "unknown"
        desc = (fn.get("description") or "").strip()
        # Обрезаем длинное описание
        if len(desc) > 120:
            desc = desc[:117] + "..."
        params = fn.get("parameters") or {}
        required = list(params.get("required") or [])
        req_str = f" (required: {', '.join(required)})" if required else ""

        if desc:
            lines.append(f"- {name}: {desc}{req_str}")
        else:
            lines.append(f"- {name}{req_str}")
    return "\n".join(lines)


def inject_tool_instructions(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not tools:
        return messages

    tools_block = _format_tools_description(tools) + "\n\n" + TOOL_CALL_FORMAT

    new_messages: list[dict[str, Any]] = []
    injected = False
    for m in messages:
        if not injected and m.get("role") == "system":
            new_content = (m.get("content") or "") + "\n\n" + tools_block
            new_messages.append({**m, "content": new_content})
            injected = True
        else:
            new_messages.append(m)

    if not injected:
        new_messages.insert(0, {"role": "system", "content": tools_block})

    return new_messages


# ---------------------------------------------------------------
# Парсеры — работают с СЫРЫМ текстом
# ---------------------------------------------------------------
def _parse_json_tool_call(text: str) -> dict[str, Any] | None:
    m = _TOOL_CALL_RE.search(text)
    if not m:
        return None

    raw = m.group(1)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        fixed = raw.replace("{{", "{").replace("}}", "}")
        try:
            obj = json.loads(fixed)
        except json.JSONDecodeError:
            return None

    name = obj.get("name")
    args = obj.get("arguments", {})
    if not name or not isinstance(args, dict):
        return None
    return {"name": name, "arguments": args}


def _parse_anthropic_tool_call(text: str) -> dict[str, Any] | None:
    if "invoke" not in text.lower():
        return None

    inv_m = _INVOKE_RE.search(text)
    if not inv_m:
        return None

    name = inv_m.group(1).strip()
    body = inv_m.group(2)
    args: dict[str, Any] = {}

    for pm in _PARAM_RE.finditer(body):
        pname = pm.group(1)
        is_str_flag = (pm.group(2) or "true").lower()
        pvalue_raw = pm.group(3).strip()
        if is_str_flag == "false":
            try:
                args[pname] = json.loads(pvalue_raw)
                continue
            except json.JSONDecodeError:
                pass
        args[pname] = pvalue_raw

    if not name:
        return None
    return {"name": name, "arguments": args}


def extract_tool_call(text: str) -> dict[str, Any] | None:
    """Пробует оба формата на СЫРОМ тексте (с DSML)."""
    if not text:
        return None
    tc = _parse_json_tool_call(text)
    if tc:
        return tc
    return _parse_anthropic_tool_call(text)


def strip_tool_call(text: str) -> str:
    """Убирает tool_call-блоки и DSML-мусор из текста."""
    if not text:
        return text
    text = _TOOL_CALL_RE.sub("", text)
    text = _INVOKE_RE.sub("", text)
    return _strip_dsml_junk(text)


def make_tool_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:24]}"
