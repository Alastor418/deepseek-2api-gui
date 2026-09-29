# API Reference

Base URL по умолчанию: `http://127.0.0.1:8080/v1`
Авторизация: заголовок `Authorization: Bearer <API_KEY>`

API_KEY генерируется автоматически при первом запуске и показан в GUI.

---

## POST /v1/chat/completions

OpenAI-совместимый эндпоинт чата.

### Заголовки

    Content-Type: application/json
    Authorization: Bearer sk-...

### Тело запроса

    {
      "model": "deepseek-chat",
      "messages": [
        {"role": "user", "content": "Привет!"}
      ],
      "stream": true
    }

Поля:

- `model` (string) — `deepseek-chat` или `deepseek-reasoner`
- `messages` (array) — история сообщений
- `stream` (bool, опционально, по умолчанию false) —
  true → SSE-стрим, false → обычный JSON

### Пример: stream=false

    curl http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer sk-..." \
      -d '{
        "model": "deepseek-chat",
        "messages": [{"role":"user","content":"Привет!"}]
      }'

Ответ:

    {
      "id": "chatcmpl-...",
      "object": "chat.completion",
      "created": 1790456588,
      "model": "deepseek-chat",
      "choices": [
        {
          "index": 0,
          "message": {
            "role": "assistant",
            "content": "..."
          },
          "finish_reason": "stop"
        }
      ],
      "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }

Для `deepseek-reasoner` в message дополнительно присутствует
поле `reasoning_content` с цепочкой размышлений.

### Пример: stream=true

    curl -N http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer sk-..." \
      -d '{
        "model": "deepseek-reasoner",
        "messages": [{"role":"user","content":"Сколько будет 17*23?"}],
        "stream": true
      }'

Ответ — SSE-чанки вида:

    data: {"id":"chatcmpl-...","object":"chat.completion.chunk",
           "created":...,"model":"deepseek-reasoner",
           "choices":[{"index":0,"delta":{"reasoning_content":"..."},
                       "finish_reason":null}]}

    data: {"id":"chatcmpl-...","object":"chat.completion.chunk",
           "created":...,"model":"deepseek-reasoner",
           "choices":[{"index":0,"delta":{"content":"..."},
                       "finish_reason":null}]}

    data: {"id":"chatcmpl-...","object":"chat.completion.chunk",
           "created":...,"model":"deepseek-reasoner",
           "choices":[{"index":0,"delta":{},
                       "finish_reason":"stop"}]}

    data: [DONE]

Поля delta:

- `role` — в первом чанке: `"assistant"`
- `reasoning_content` — мысли (только для `deepseek-reasoner`)
- `content` — финальный текст

---

## GET /v1/models

Список доступных моделей и алиасов.

    curl http://127.0.0.1:8080/v1/models \
      -H "Authorization: Bearer sk-..."

Ответ:

    {
      "object": "list",
      "data": [
        {"id": "deepseek-chat", "object": "model",
         "created": ..., "owned_by": "deepseek"},
        {"id": "deepseek-reasoner", "object": "model",
         "created": ..., "owned_by": "deepseek"}
      ]
    }

---

## Управление (для GUI)

Эти эндпоинты используются встроенным GUI. Они доступны только с
`127.0.0.1` / `localhost` (middleware блокирует остальные хосты).

### GET /gui/status

    {
      "authenticated": true,
      "login_in_progress": false,
      "api_url": "http://127.0.0.1:8080/v1",
      "api_key": "sk-...",
      "version": "3.1.0",
      "accounts_total": 2,
      "accounts_active": 2,
      "models": ["deepseek-chat", "deepseek-reasoner"],
      "log_file": "/home/user/.deepseek-2api/logs/app.log"
    }

### POST /gui/login

Запускает ручной логин через браузер.

### POST /gui/logout

Удаляет `credentials.json` (legacy). Пул аккаунтов не затрагивается.

### POST /gui/pool/clear

Удаляет ВСЕ аккаунты из пула. Необратимо.

Ответ: `{"status": "ok", "removed": 3}`

### GET /gui/accounts

Список аккаунтов в пуле.

### POST /gui/accounts

Добавить аккаунт вручную.

    {
      "label": "main",
      "authorization": "Bearer eyJhbGciOi...",
      "cookie": "..."
    }

### DELETE /gui/accounts/{id}

Удалить аккаунт.

### POST /gui/accounts/{id}/reactivate

Сбросить статус с `expired`/`banned` на `active`.

### POST /gui/accounts/{id}/label

Изменить метку аккаунта.

### GET /gui/logs

SSE-стрим логов в реальном времени.

### GET /gui/logs/download

Скачать файл `app.log`.

---

## Формат ошибок

    {
      "error": {
        "message": "описание",
        "type": "provider_error"
      }
    }

Статусы:

- 400 — некорректный запрос (bad model, bad JSON)
- 401 — отсутствует заголовок Authorization
- 403 — неверный API Key (или /gui/* не с localhost)
- 422 — не прошла Pydantic-валидация
- 500 — ошибка провайдера (см. `message`)
