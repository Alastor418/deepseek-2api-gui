import asyncio
import base64
import contextlib
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from app.core.accounts import Account, pool
from app.core.config import settings
from app.core.storage import load_credentials
from app.providers import tool_bridge
from app.providers.base import BaseProvider
from app.providers.pow_solver import get_pow_solver


class _InvalidToken(Exception):
    """Внутренний маркер: JWT протух, нужен релогин."""


class _UnknownModel(Exception):
    """Клиент запросил модель, которой нет в SUPPORTED_MODELS."""

    def __init__(self, name: str, available: list) -> None:
        super().__init__(f"Unknown model: {name!r}. Available: {available}")
        self.name = name
        self.available = available


class _NoAccounts(Exception):
    """Нет активных аккаунтов в пуле. Нужен ручной логин."""


INVALID_TOKEN_MARKERS = (
    "INVALID_TOKEN",
    "AUTH_TOKEN_EXPIRED",
    "UNAUTHORIZED",
    "LOGIN_REQUIRED",
    "TOKEN_EXPIRED",
    "USER_NOT_LOGIN",
    "NOT_LOGGED_IN",
    "NEED_LOGIN",
    "PLEASE_LOGIN",
    "登录",
    "请先登录",
)


def _is_dead_session(
    status_code: int,
    body_text: str,
    parsed_json: dict | None,
) -> bool:
    """Единая проверка «сессия мертва».

    Срабатывает когда:
      - HTTP 401/403
      - В теле есть маркер протухшего токена
      - HTTP 2xx, но parsed_json == {"code": <не 0/None>, "data": null}
        (именно так Deepseek отдаёт invalid session)
    """
    if status_code in (401, 403):
        return True

    upper = body_text.upper()
    if any(marker in upper for marker in INVALID_TOKEN_MARKERS):
        return True

    if parsed_json is not None:
        data = parsed_json.get("data")
        code = parsed_json.get("code")
        if data is None and code not in (0, None):
            return True

    return False


class _StreamState:
    """Отслеживает типы фрагментов (RESPONSE / THINKING) в JSON-Patch потоке."""

    def __init__(self) -> None:
        self._types: dict[int, str] = {}
        self._count = 0

    def is_empty(self) -> bool:
        return self._count == 0

    def register(self, frag: dict) -> int:
        idx = self._count
        self._types[idx] = frag.get("type", "RESPONSE")
        self._count += 1
        return idx

    def resolve_index(self, path: str) -> int | None:
        try:
            parts = path.split("/")
            i = parts.index("fragments")
            n = int(parts[i + 1])
        except (ValueError, IndexError):
            return None
        if n < 0:
            n = self._count + n
        return n

    def type_at(self, idx: int | None) -> str:
        if idx is None:
            return "RESPONSE"
        return self._types.get(idx, "RESPONSE")

    def last_type(self) -> str:
        if self._count == 0:
            return "RESPONSE"
        return self._types.get(self._count - 1, "RESPONSE")


class DeepseekProvider(BaseProvider):
    """Провайдер Deepseek (веб-версия) — v3.1.

    - WASM-PoW (DeepSeekHashV1), singleton
    - stream=true / stream=false
    - deepseek-chat и deepseek-reasoner (с reasoning_content)
    - Авторетрай при INVALID_TOKEN + headless-релогин
    - Ротация аккаунтов из AccountPool
    """

    BASE_URL = "https://chat.deepseek.com/api/v0"

    def __init__(self) -> None:
        super().__init__()
        self._pow_solver = get_pow_solver()
        self._relogin_lock = asyncio.Lock()
        # DeepSeek web API: одна активная сессия на аккаунт.
        # Параллельные запросы блокируют друг друга — сериализуем.
        self._request_lock = asyncio.Lock()
        # Throttle: DeepSeek отклоняет параллельные сессии.
        self._last_request_end: float = 0.0
        self._min_interval: float = 2.0

    async def chat_completion(
        self, request_data: dict[str, Any], original_request: Request
    ) -> StreamingResponse | JSONResponse:
        try:
            raw_model = request_data.get("model", "deepseek-chat")
            resolved = self._resolve_model(raw_model)

            # Жёсткое форсирование (см. .env → FORCE_THINKING / FORCE_SEARCH)
            if settings.FORCE_THINKING and not resolved.get("thinking"):
                resolved["thinking"] = True
                logger.info("   [Force] thinking_enabled=True")
            if settings.FORCE_SEARCH and not resolved.get("search"):
                resolved["search"] = True
                logger.info("   [Force] search_enabled=True")

            if (
                settings.AUTO_WEB_SEARCH
                and self._client_wants_web_search(request_data)
                and not resolved.get("search")
            ):
                resolved["search"] = True
                logger.info("   [Auto] web_search -> search_enabled=True")
            stream = bool(request_data.get("stream", False))
            logger.info(
                f"-> Deepseek completion (model={raw_model} -> {resolved['name']}, "
                f"thinking={resolved['thinking']}, stream={stream})"
            )
            request_data["__resolved__"] = resolved
            request_data["__has_tools__"] = bool(request_data.get("tools"))

            if stream:
                return await self._handle_stream(request_data, raw_model)
            return await self._handle_non_stream(request_data, raw_model)
        except _UnknownModel as e:
            logger.warning(f"! Unknown model: {e.name}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": str(e),
                        "type": "invalid_request_error",
                        "code": "model_not_found",
                    }
                },
            )
        except _NoAccounts as e:
            logger.warning(f"! No accounts: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "message": str(e),
                        "type": "no_accounts",
                    }
                },
            )
        except Exception as e:
            logger.exception(f"Provider error: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": {"message": str(e), "type": "provider_error"}},
            )

    @staticmethod
    def _client_wants_web_search(request_data: dict) -> bool:
        tools = request_data.get("tools") or []
        if not isinstance(tools, list):
            return False
        markers = ("web_search", "web", "search", "browse", "fetch")
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            fn = tool.get("function") or {}
            name = (fn.get("name") or "").lower()
            if any(m in name for m in markers):
                return True
        return False

    @staticmethod
    def _strip_dsml(text: str) -> str:
        """Deepseek-веб иногда галлюцинирует XML-теги вида <...DSML...>.

        Это band-aid, пока живём с веб-API. Если начнёт портить контент —
        уберём и решим через промпт.
        """
        if not text or "DSML" not in text:
            return text
        import re
        text = re.sub(r"</?[^>]*DSML[^>]*>", "", text)
        text = re.sub(r"</?tool_(calls|invoke)[^>]*>", "", text)
        return text.strip()

    @staticmethod
    def _strip_finished_marker(text: str) -> str:
        """Deepseek-веб иногда добавляет 'FINISHED' в конце ответа.

        Убираем только если перед FINISHED есть whitespace — иначе можно
        испортить слово вида 'UNFINISHED'.
        """
        if not text:
            return text
        for suffix in ("\nFINISHED", " FINISHED"):
            if text.endswith(suffix):
                return text[: -len(suffix)].rstrip()
        return text

    def _resolve_model(self, name: str) -> dict[str, Any]:
        aliases = settings.MODEL_ALIASES or {}
        if name in aliases:
            cfg = aliases[name]
            return {
                "name": cfg.get("model", "deepseek-chat"),
                "thinking": bool(cfg.get("thinking", False)),
                "search": bool(cfg.get("search", False)),
            }

        if name == "deepseek-reasoner":
            return {"name": "deepseek-chat", "thinking": True, "search": False}

        if name == "deepseek-chat":
            return {"name": "deepseek-chat", "thinking": False, "search": False}

        raise _UnknownModel(name, list(settings.SUPPORTED_MODELS))

    def _pick_account(self) -> Account | None:
        acc = pool.next_active()
        if acc:
            return acc
        creds = load_credentials()
        if creds:
            return Account(
                id="legacy",
                label="legacy",
                authorization=creds.authorization,
                cookie=creds.cookie,
                status="active",
            )
        return None

    async def _get_pow_header(self, client: httpx.AsyncClient, headers: dict) -> str:
        r = await client.post(
            f"{self.BASE_URL}/chat/create_pow_challenge",
            json={"target_path": "/api/v0/chat/completion"},
            headers=headers,
        )
        r.raise_for_status()
        c = r.json()["data"]["biz_data"]["challenge"]
        logger.info(
            f"   [PoW] challenge difficulty={c['difficulty']} "
            f"expire_at={c['expire_at']}"
        )
        answer = await asyncio.to_thread(
            self._pow_solver.solve,
            c["challenge"],
            c["salt"],
            c["expire_at"],
            c["difficulty"],
        )
        logger.info(f"   [PoW] solved answer={answer}")
        payload = {
            "algorithm": c["algorithm"],
            "challenge": c["challenge"],
            "salt": c["salt"],
            "answer": answer,
            "signature": c["signature"],
            "target_path": c["target_path"],
        }
        return base64.b64encode(json.dumps(payload).encode()).decode()

    def _headers_for(self, acc: Account) -> dict[str, str]:
        return {
            "accept": "*/*",
            "authorization": acc.authorization,
            "cookie": acc.cookie,
            "content-type": "application/json",
            "origin": "https://chat.deepseek.com",
            "referer": "https://chat.deepseek.com/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            ),
            "x-app-version": "20241129.1",
            "x-client-platform": "web",
            "x-client-version": "1.4.0-fragments",
        }

    @staticmethod
    def _format_prompt(messages: list) -> str:
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            parts.append(f"{role}: {content}")
        parts.append("assistant:")
        return "\n\n".join(parts)

    def _build_payload(self, request_data: dict, session_id: str) -> dict:
        messages = request_data.get("messages") or []

        # Если клиент просит tools — внедряем их описание в system prompt
        tools = request_data.get("tools")
        if tools and isinstance(tools, list):
            logger.info(f"   [tools] {len(tools)} шт")
            messages = tool_bridge.inject_tool_instructions(messages, tools)

        prompt = self._format_prompt(messages) if messages else "hi"
        resolved = request_data.get("__resolved__") or {}
        return {
            "chat_session_id": session_id,
            "parent_message_id": None,
            "prompt": prompt,
            "ref_file_ids": [],
            "thinking_enabled": bool(resolved.get("thinking", False)),
            "search_enabled": bool(resolved.get("search", False)),
            "client_stream_id": f"{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:16]}",
        }

    async def _prepare(self, request_data: dict, acc: Account):
        headers = self._headers_for(acc)
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{self.BASE_URL}/chat_session/create", headers=headers, json={}
            )

            try:
                parsed = r.json()
            except Exception:
                parsed = None

            if _is_dead_session(r.status_code, r.text, parsed):
                raise _InvalidToken(
                    f"session/create: {r.status_code} {r.text[:200]}"
                )

            if not isinstance(parsed, dict):
                raise _InvalidToken(
                    f"session/create: non-dict json ({r.status_code}): {r.text[:200]}"
                )

            data = parsed.get("data")
            if not isinstance(data, dict):
                raise _InvalidToken(
                    f"session/create: data is {type(data).__name__}: {r.text[:200]}"
                )

            biz = data.get("biz_data")
            if not isinstance(biz, dict):
                raise _InvalidToken(
                    f"session/create: biz_data is {type(biz).__name__}: {r.text[:200]}"
                )

            session_id = biz.get("id")
            if not session_id:
                raise _InvalidToken(
                    f"session/create: no session id: {r.text[:200]}"
                )

            logger.info(f"   [Session] {session_id}")
            headers["x-ds-pow-response"] = await self._get_pow_header(client, headers)

        return headers, self._build_payload(request_data, session_id)

    async def _raw_stream(
        self, headers: dict, payload: dict
    ) -> AsyncGenerator[dict, None]:
        timeout = httpx.Timeout(60.0, read=settings.REQUEST_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client, client.stream(
            "POST",
            f"{self.BASE_URL}/chat/completion",
            headers=headers,
            json=payload,
        ) as r:
            logger.info(
                f"   [Stream] status={r.status_code} "
                f"ct={r.headers.get('content-type', '?')}"
            )
            if r.status_code != 200:
                body = await r.aread()
                text = body.decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = None
                if _is_dead_session(r.status_code, text, parsed):
                    raise _InvalidToken(
                        f"completion: {r.status_code} {text[:200]}"
                    )
                r.raise_for_status()
                return

            first_chunk_seen = False
            async for line in r.aiter_lines():
                if not line:
                    continue

                if not line.startswith("data:"):
                    try:
                        parsed = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(parsed, dict) and _is_dead_session(
                        200, line, parsed
                    ):
                        raise _InvalidToken(
                            f"completion (inline): {line[:200]}"
                        )
                    continue

                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if not first_chunk_seen:
                    first_chunk_seen = True
                    if isinstance(chunk, dict) and _is_dead_session(
                        200, raw, chunk
                    ):
                        raise _InvalidToken(
                            f"completion (first chunk): {raw[:200]}"
                        )

                yield chunk

    @classmethod
    def _extract_delta(
        cls, chunk: dict, state: _StreamState
    ) -> dict[str, str | None]:
        path = chunk.get("p")
        op = chunk.get("o")
        value = chunk.get("v")

        if (
            path
            and "response/fragments" in path
            and path.endswith("/content")
            and isinstance(value, str)
        ):
            idx = state.resolve_index(path)
            if state.type_at(idx) == "THINK":
                return {"content": None, "reasoning": value}
            return {"content": value, "reasoning": None}

        if path == "response/fragments" and op == "APPEND" and isinstance(value, list):
            c_buf: list = []
            r_buf: list = []
            for frag in value:
                if not isinstance(frag, dict):
                    continue
                state.register(frag)
                t = frag.get("type")
                c = frag.get("content")
                if isinstance(c, str) and c:
                    (r_buf if t == "THINK" else c_buf).append(c)
            return {
                "content": "".join(c_buf) or None,
                "reasoning": "".join(r_buf) or None,
            }

        if isinstance(value, dict):
            resp = value.get("response")
            if isinstance(resp, dict) and state.is_empty():
                frags = resp.get("fragments")
                if isinstance(frags, list):
                    full_c: list = []
                    full_r: list = []
                    for frag in frags:
                        if not isinstance(frag, dict):
                            continue
                        state.register(frag)
                        t = frag.get("type")
                        c = frag.get("content")
                        if isinstance(c, str) and c:
                            (full_r if t == "THINK" else full_c).append(c)
                    return {
                        "content": "".join(full_c) or None,
                        "reasoning": "".join(full_r) or None,
                    }

        if path is None and op is None and isinstance(value, str):
            if state.last_type() == "THINK":
                return {"content": None, "reasoning": value}
            return {"content": value, "reasoning": None}

        return {"content": None, "reasoning": None}

    async def _auto_relogin(self, failed_acc: Account) -> Account | None:
        if not settings.AUTO_RELOGIN:
            return None

        async with self._relogin_lock:
            fresh = pool.next_active()
            if fresh and fresh.id != failed_acc.id:
                return fresh

            logger.warning("! Токен протух — запускаю авторелогин (headless)")
            try:
                from app.auth.capture import capture_credentials

                creds = await asyncio.wait_for(
                    capture_credentials(
                        on_log=logger.info,
                        headless=True,
                        try_existing_session=True,
                        auto_send_prompt="hi",
                    ),
                    timeout=settings.AUTO_RELOGIN_TIMEOUT,
                )
            except Exception as e:
                logger.error(f"X Headless-релогин не удался: {e}")
                if failed_acc.id != "legacy":
                    pool.mark_error(failed_acc.id, str(e), "expired")
                return None

            if not creds.get("authorization"):
                logger.error("X Авторелогин: токен не получен")
                return None

            acc = pool.add(
                authorization=creds["authorization"],
                cookie=creds.get("cookie", ""),
                label="auto",
            )
            pool.reactivate(acc.id)
            logger.success(f"OK Авторелогин успешен, аккаунт {acc.id}")
            return acc

    async def _with_retry(self, request_data: dict):
        last_err: Exception | None = None
        for attempt in range(1, settings.MAX_RETRIES + 1):
            acc = self._pick_account()
            if acc is None:
                raise _NoAccounts(
                    "Нет доступных аккаунтов. Нажмите «Войти в Deepseek» в GUI."
                )
            try:
                headers, payload = await self._prepare(request_data, acc)
                if acc.id != "legacy":
                    pool.mark_used(acc.id)
                return acc, headers, payload
            except _InvalidToken as e:
                logger.warning(f"! [attempt {attempt}] INVALID_TOKEN: {e}")
                last_err = e
                if acc.id != "legacy":
                    pool.mark_error(acc.id, str(e), "expired")
                new_acc = await self._auto_relogin(acc)
                if new_acc is None:
                    raise
                continue
            except httpx.HTTPStatusError as e:
                last_err = e
                logger.error(
                    f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                )
                if _is_dead_session(
                    e.response.status_code, e.response.text, None
                ):
                    if acc.id != "legacy":
                        pool.mark_error(acc.id, e.response.text[:200], "expired")
                    new_acc = await self._auto_relogin(acc)
                    if new_acc is None:
                        raise
                    continue
                raise
        raise last_err or RuntimeError("retry exhausted")

    async def _handle_non_stream(
        self, request_data: dict, client_model: str
    ) -> JSONResponse:
        async with self._request_lock:
            return await self._do_non_stream(request_data, client_model)

    async def _do_non_stream(
        self, request_data: dict, client_model: str
    ) -> JSONResponse:
        acc, headers, payload = await self._with_retry(request_data)
        full_content = ""
        full_reasoning = ""
        state = _StreamState()

        try:
            async for ch in self._raw_stream(headers, payload):
                d = self._extract_delta(ch, state)
                if d["content"]:
                    full_content += d["content"]
                if d["reasoning"]:
                    full_reasoning += d["reasoning"]
        except _InvalidToken:
            new_acc = await self._auto_relogin(acc)
            if new_acc is None:
                raise
            headers, payload = await self._prepare(request_data, new_acc)
            state = _StreamState()
            async for ch in self._raw_stream(headers, payload):
                d = self._extract_delta(ch, state)
                if d["content"]:
                    full_content += d["content"]
                if d["reasoning"]:
                    full_reasoning += d["reasoning"]

        full_content = self._strip_finished_marker(
            self._strip_dsml(full_content)
        )
        message: dict[str, Any] = {"role": "assistant", "content": full_content}
        if full_reasoning:
            message["reasoning_content"] = self._strip_dsml(full_reasoning)

        return JSONResponse(
            {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": client_model,
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        )

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    def _chunk(
        self,
        chat_id: str,
        model: str,
        delta: dict,
        finish: str | None = None,
    ) -> str:
        return self._sse(
            {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {"index": 0, "delta": delta, "finish_reason": finish}
                ],
            }
        )

    def _chunk_tool_calls(
        self,
        chat_id: str,
        model: str,
        name: str,
        args_json: str,
    ) -> str:
        """SSE-чанк в OpenAI-формате для tool_calls."""
        return self._sse(
            {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": tool_bridge.make_tool_call_id(),
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": args_json,
                                    },
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        )

    async def _handle_stream(
        self, request_data: dict, client_model: str
    ) -> StreamingResponse:
        has_tools = bool(request_data.get("__has_tools__"))

        async def gen() -> AsyncGenerator[str, None]:
            # Lock на ВЕСЬ стрим: _with_retry тоже внутри —
            # иначе два параллельных _with_retry создают две сессии.
            async with self._request_lock:
                # Throttle: DeepSeek отклоняет параллельные сессии.
                # Ждём минимум 2 сек после предыдущего запроса.
                import time as _t
                elapsed = _t.monotonic() - self._last_request_end
                if elapsed < self._min_interval:
                    wait = self._min_interval - elapsed
                    logger.info(f"   [throttle] sleeping {wait:.1f}s")
                    await asyncio.sleep(wait)
                try:
                    async for chunk in _gen_impl():
                        yield chunk
                finally:
                    self._last_request_end = _t.monotonic()

        async def _gen_impl() -> AsyncGenerator[str, None]:
            acc, headers, payload = await self._with_retry(request_data)

            chat_id = f"chatcmpl-{uuid.uuid4().hex}"
            first = True
            stream_headers = headers
            stream_payload = payload
            cur_acc = acc

            # Состояние для детекции <tool_call>
            TAIL_KEEP = 20
            pending = ""       # буфер (не отправлен клиенту)
            tool_mode = False  # переключились в режим tool_call?
            tool_buf = ""      # накопитель для tool_call-блока
            finish_reason = "stop"

            try:
                while True:
                    try:
                        state = _StreamState()
                        async with contextlib.aclosing(
                            self._raw_stream(stream_headers, stream_payload)
                        ) as stream:
                            async for ch in stream:
                                d = self._extract_delta(ch, state)
                                if first and (d["content"] or d["reasoning"]):
                                    yield self._chunk(
                                        chat_id,
                                        client_model,
                                        {"role": "assistant"},
                                    )
                                    first = False
                                if d["reasoning"]:
                                    yield self._chunk(
                                        chat_id,
                                        client_model,
                                        {"reasoning_content": d["reasoning"]},
                                    )
                                if not d["content"]:
                                    continue

                                if tool_mode:
                                    tool_buf += d["content"]
                                    _tool_buf_lower = tool_buf.lower()
                                    _is_closed = (
                                        "</tool_call>" in _tool_buf_lower
                                        or "invoke>" in _tool_buf_lower
                                    )
                                    if _is_closed:
                                        tc = tool_bridge.extract_tool_call(
                                            tool_buf
                                        )
                                        if tc:
                                            yield self._chunk_tool_calls(
                                                chat_id,
                                                client_model,
                                                tc["name"],
                                                json.dumps(
                                                    tc["arguments"],
                                                    ensure_ascii=False,
                                                ),
                                            )
                                            finish_reason = "tool_calls"
                                            tool_buf = ""
                                            break
                                        else:
                                            # Не распарсилось — отдаём как текст
                                            yield self._chunk(
                                                chat_id,
                                                client_model,
                                                {"content": tool_buf},
                                            )
                                            tool_buf = ""
                                            tool_mode = False
                                    continue

                                # Обычный режим
                                pending += d["content"]

                                _start = -1
                                if has_tools:
                                    # Ищем маркер tool-call в буфере.
                                    # Универсальный: "invoke " (слово+пробел) —
                                    # DeepSeek может дробить теги на символы,
                                    # но "invoke " точно появится целиком.
                                    for marker in ("<tool_call>", "invoke "):
                                        i = pending.find(marker)
                                        if i != -1 and (_start == -1 or i < _start):
                                            _start = i
                                    # Откатываемся к началу тега, если он есть
                                    if _start > 0:
                                        lt = pending.rfind("<", 0, _start)
                                        if lt != -1 and _start - lt < 200:
                                            _start = lt
                                if _start != -1:
                                    idx = _start
                                    before = pending[:idx]
                                    if before:
                                        cleaned = self._strip_finished_marker(
                                            self._strip_dsml(before)
                                        )
                                        if cleaned:
                                            yield self._chunk(
                                                chat_id,
                                                client_model,
                                                {"content": cleaned},
                                            )
                                    tool_buf = pending[idx:]
                                    tool_mode = True
                                    pending = ""
                                elif len(pending) > TAIL_KEEP:
                                    flush = pending[:-TAIL_KEEP]
                                    cleaned = self._strip_finished_marker(
                                        self._strip_dsml(flush)
                                    )
                                    if cleaned:
                                        yield self._chunk(
                                            chat_id,
                                            client_model,
                                            {"content": cleaned},
                                        )
                                    pending = pending[-TAIL_KEEP:]

                        # Конец стрима — выгружаем остаток
                        if pending:
                            cleaned = self._strip_finished_marker(
                                self._strip_dsml(pending)
                            )
                            if cleaned:
                                yield self._chunk(
                                    chat_id,
                                    client_model,
                                    {"content": cleaned},
                                )
                            pending = ""

                        if tool_mode and tool_buf:
                            # Закрывающий тег так и не пришёл — пробуем распарсить
                            tc = tool_bridge.extract_tool_call(tool_buf)
                            if tc:
                                yield self._chunk_tool_calls(
                                    chat_id,
                                    client_model,
                                    tc["name"],
                                    json.dumps(
                                        tc["arguments"], ensure_ascii=False
                                    ),
                                )
                                finish_reason = "tool_calls"
                            else:
                                yield self._chunk(
                                    chat_id,
                                    client_model,
                                    {"content": tool_buf},
                                )
                            tool_buf = ""

                        yield self._chunk(
                            chat_id, client_model, {},
                            finish=finish_reason,
                        )
                        yield "data: [DONE]\n\n"
                        return

                    except _InvalidToken as e:
                        logger.warning(
                            f"! Стрим: INVALID_TOKEN, релогин… ({e})"
                        )
                        if cur_acc.id != "legacy":
                            pool.mark_error(cur_acc.id, str(e), "expired")
                        new_acc = await self._auto_relogin(cur_acc)
                        if new_acc is None:
                            yield self._sse(
                                {
                                    "error": {
                                        "message": "relogin failed",
                                        "type": "auth_error",
                                    }
                                }
                            )
                            yield "data: [DONE]\n\n"
                            return
                        stream_headers, stream_payload = await self._prepare(
                            request_data, new_acc
                        )
                        cur_acc = new_acc
                        continue

            except asyncio.CancelledError:
                # Клиент отключился или ASGI отменяет — просто выходим.
                logger.debug("stream cancelled by client")
                raise

            except GeneratorExit:
                # Starlette закрывает генератор — молча выходим.
                logger.debug("stream closed by ASGI")
                return

            except Exception as e:
                logger.exception(f"stream error: {e}")
                # Не yield-им если соединение уже закрыто.
                try:
                    yield self._sse(
                        {
                            "error": {
                                "message": str(e),
                                "type": "provider_error",
                            }
                        }
                    )
                    yield "data: [DONE]\n\n"
                except GeneratorExit:
                    return

        return StreamingResponse(gen(), media_type="text/event-stream")
