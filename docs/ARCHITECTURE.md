# Архитектура Deepseek-2api GUI

## Общая схема

    Пользователь → Harness (:3080) → deepseek-2api (:8080) → chat.deepseek.com
                       │                    │
                       │                    ├── AccountPool (LRU)
                       │                    ├── PowSolver (WASM)
                       │                    ├── Playwright (автологин)
                       │                    └── DeepseekProvider

## Компоненты

### main.py
Точка входа. Проверяет WASM и Chromium, запускает uvicorn на
127.0.0.1:8080, открывает браузер с GUI.

### app/core/config.py
pydantic-settings, читает `.env`. Синглтоны `settings` и `state`.

### app/core/storage.py
`credentials.json` (legacy) и `api_key.txt`. Все записи атомарные
(tmp → fsync → rename), chmod 600.

### app/core/accounts.py
Пул аккаунтов в `~/.deepseek-2api/accounts/*.json`. Потокобезопасен
(RLock). `mark_error()` сразу выставляет статус expired/banned.

### app/core/logging.py
loguru: консоль + файл + SSE-канал. `LogBroadcaster` потокобезопасен,
доставка через `call_soon_threadsafe`.

### app/auth/capture.py
Playwright в persistent context. Перехватывает `authorization` и
`cookie` из первого API-запроса к chat.deepseek.com.

### app/providers/pow_solver.py
WASM PoW через wasmtime. Singleton, потокобезопасен (Lock).

### app/providers/deepseek.py
Ядро: resolve model → pick account → prepare (session + PoW) →
raw stream → extract delta → OpenAI format. Авторелогин при
INVALID_TOKEN.

### app/gui/server.py
FastAPI. Роуты `/`, `/gui/*` (localhost only), `/v1/*` (Bearer auth).
Lifespan держит ссылки на background tasks.

## Формат чанков Deepseek

JSON-Patch:

    {"v": {"response": {"fragments": [...]}}}       # полный объект
    {"p": "response/fragments", "o": "APPEND",      # добавить фрагменты
     "v": [{"type": "THINK", "content": "..."}]}
    {"p": "response/fragments/-1/content",
     "o": "APPEND", "v": "..."}                     # append к content
    {"v": "..."}                                    # продолжение

`_StreamState` отслеживает индексы фрагментов и их типы (RESPONSE/THINK).

## Жизненный цикл запроса

1. `POST /v1/chat/completions` с Bearer auth.
2. `verify_api_key` (compare_digest) + Pydantic validation.
3. `_resolve_model` — выбрать `thinking_enabled`.
4. `_with_retry` — account + prepare (session, PoW).
5. `_raw_stream` — httpx SSE.
6. `_extract_delta` — routing content/reasoning.
7. SSE-обёртка OpenAI или единый JSON.

## Авторелогин

Триггеры: 401/403, маркеры `INVALID_TOKEN`, `{"code": ≠0, "data": null}`.

Шаги: взять `_relogin_lock` → проверить свежий аккаунт → headless
`capture_credentials` → `pool.add` + `reactivate` → повтор запроса.

## Обработка ошибок

- 4xx → JSON клиенту.
- 5xx → лог + `{"error": {...}}`.
- Ошибка в стриме после старта → `error` чанк БЕЗ `finish_reason=stop`.
