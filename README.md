# DeepSeek-2API GUI

> Локальный OpenAI-совместимый прокси для `chat.deepseek.com` с автологином, авторелогином, мультиаккаунтным пулом, **tool calling** и интеграцией с **DeepSeek Harness**.

---

## Что это

Один Python-процесс, который превращает веб-версию DeepSeek в полноценный
OpenAI-совместимый API:

- Поднимает HTTP-сервер на `http://127.0.0.1:8080/v1`
- Автологинится через Playwright в `chat.deepseek.com`
- Перехватывает `Authorization` и `Cookie`
- Решает PoW-челлендж `DeepSeekHashV1` через WASM
- Работает с моделями `deepseek-chat` и `deepseek-reasoner`
- Возвращает reasoning-цепочку в `reasoning_content`
- Поддерживает **tool calling** (OpenAI-формат)
- Работает с пулом аккаунтов (LRU + автобан + реактивация)
- Сам перелогинивается при истечении токена

**Зачем:** использовать бесплатный DeepSeek через локальный API в любых клиентах — Chatbox, Open WebUI, Continue.dev, Cursor, собственные скрипты, DeepSeek Harness.

---

## Возможности

| Фича | Статус |
|------|--------|
| OpenAI-совместимый API `/v1/chat/completions` | OK |
| `deepseek-chat` (быстрый чат) | OK |
| `deepseek-reasoner` (reasoning_content) | OK |
| Streaming SSE | OK |
| Non-stream JSON | OK |
| Tool calling (tool_calls в OpenAI-формате) | OK |
| Автологин через Playwright | OK |
| Авторелогин при INVALID_TOKEN | OK |
| Мультиаккаунт (пул с LRU) | OK |
| Автобан и реактивация аккаунтов | OK |
| Браузерные расширения (обход hCaptcha) | OK |
| DeepSeek Harness (Web UI агента) | OK |
| Omarchy плагин (иконка в баре) | OK |


---

## Требования

- **Linux** (тестировано на Arch Linux / Omarchy 4)
- **Python 3.12** — обязательно, 3.13+ падает из-за `wasmtime`
- **Node.js 24.x** — для DeepSeek Harness (26.x ломает)
- `rsync`, `curl`, `git`
- ~700 МБ свободного места
- Аккаунт DeepSeek

---

## Установка одной командой

    git clone https://github.com/Alastor418/deepseek-2api-gui.git
    cd deepseek-2api-gui
    bash install.sh

Installer сам сделает всё:

1. Проверит ОС и зависимости
2. Поставит Python 3.12 и Node 24 (через `mise`, если нет)
3. Скопирует проект в `~/deepseek-2api-gui`
4. Создаст venv, поставит pip-зависимости
5. Поставит системные библиотеки для Chromium (через `pacman`)
6. Скачает Chromium для Playwright
7. Установит systemd-сервис `deepseek-2api.service`
8. Сгенерирует мастер-ключ API
9. Откроет GUI для логина в DeepSeek
10. Установит и настроит **DeepSeek Harness**
11. Установит **Omarchy плагин** (если Omarchy есть)

---

## Быстрый старт после установки

### 1. Первый логин в DeepSeek

Installer откроет `http://127.0.0.1:8080` в браузере:

1. Нажми **«Войти в Deepseek»**
2. В открывшемся Chromium залогинься в аккаунт
3. **Отправь любое сообщение** в чате DeepSeek (это критично — токен перехватывается только на API-запросе)
4. Дождись зелёного статуса в GUI
5. Вернись в терминал и нажми Enter

**Если hCaptcha блокирует Playwright** — см. раздел «Браузерные расширения».

### 2. Проверка что всё работает

    bash ~/deepseek-2api-gui/verify.sh

Скрипт проверит 22 пункта и покажет `X passed, Y failed`.

### 3. Первый запрос к API

    API_KEY=$(cat ~/.deepseek-2api/api_key.txt)

    curl -N http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      -d '{
        "model": "deepseek-reasoner",
        "messages": [{"role": "user", "content": "Сколько будет 17*23?"}],
        "stream": true
      }'

**Ожидаемое:** SSE-чанки с `reasoning_content` (мысли), потом с `content` (ответ), потом `[DONE]`.


---

## Использование API

**Base URL:** `http://127.0.0.1:8080/v1`
**API Key:** смотри в GUI (кнопка «Копировать»)

### Non-stream

    curl http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      -d '{
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "Привет!"}]
      }'

### Stream

    curl -N http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      -d '{
        "model": "deepseek-reasoner",
        "messages": [{"role": "user", "content": "2+2?"}],
        "stream": true
      }'

Ответ — SSE-чанки:

    data: {"delta":{"reasoning_content":"..."}}
    data: {"delta":{"content":"4"}}
    data: {"delta":{},"finish_reason":"stop"}
    data: [DONE]

### Tool calling

    curl -N http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      -d '{
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "какая сейчас директория?"}],
        "tools": [{
          "type": "function",
          "function": {
            "name": "bash",
            "description": "Run a bash command",
            "parameters": {
              "type": "object",
              "properties": {
                "command": {"type": "string"}
              },
              "required": ["command"]
            }
          }
        }],
        "stream": true
      }'

**Ожидаемое:** в чанках появится `tool_calls` с JSON-аргументами:

    data: {"choices":[{"delta":{"tool_calls":[{
      "index": 0,
      "id": "call_...",
      "type": "function",
      "function": {
        "name": "bash",
        "arguments": "{\"command\": \"pwd\"}"
      }
    }]},"finish_reason":null}]}
    data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}
    data: [DONE]

Дальше клиент сам выполняет tool и отправляет результат обратно в `messages`.

### Python (openai SDK)

    from openai import OpenAI

    client = OpenAI(
        base_url="http://127.0.0.1:8080/v1",
        api_key=open("/home/user/.deepseek-2api/api_key.txt").read().strip(),
    )

    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[{"role": "user", "content": "2+2?"}],
        stream=True,
    )

    for chunk in response:
        delta = chunk.choices[0].delta
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            print(f"[thinking] {delta.reasoning_content}", end="", flush=True)
        if delta.content:
            print(delta.content, end="", flush=True)

---

## Совместимые клиенты

| Клиент | Статус | Как подключить |
|--------|--------|----------------|
| **Chatbox** | чат + reasoning | API Host: `http://127.0.0.1:8080`, Path: `/v1` |
| **Open WebUI** | чат | Settings -> Connections -> OpenAI API |
| **Continue.dev** | чат | `apiBase: http://127.0.0.1:8080/v1` |
| **Cursor** | чат | OpenAI API Base: `http://127.0.0.1:8080/v1` |
| **Python openai** | всё | `OpenAI(base_url=..., api_key=...)` |
| **DeepSeek Harness** | tools + UI | Installer настраивает автоматически |
| **OpenCode** | только чат | Tool calls не поддерживаются |


---

## DeepSeek Harness

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) — официальный агент-харнесс с Web UI. Installer настраивает его автоматически.

**Что делает installer:**

1. Ставит `@deepseek-ai/dsh` глобально через npm
2. Прогревает профиль `web` (создаёт `~/.dsh/profiles/web/`)
3. Записывает `~/.dsh/.env` с нашим мастер-ключом
4. Пишет `~/.dsh/profiles/web/cordis.patch.yml` с провайдером `deepseek-2api`
5. Создаёт systemd-юнит `deepseek-harness.service`

**Как открыть:**

    URL=$(journalctl --user -u deepseek-harness.service --no-pager | \
          grep -oE 'http://127\.0\.0\.1:3080/\?token=[A-Za-z0-9_-]+' | tail -1)
    xdg-open "$URL"

Или через Omarchy плагин: **ЛКМ** по иконке `󰚩` в баре.

**Возможности в Harness:**

- Чат с `deepseek-chat` / `deepseek-reasoner`
- **Tool calling работает** — модель вызывает `bash`, `read`, `write`,
  `web_search` и другие из 26 tools Harness
- Reasoning виден через UI
- Файлы создаются в `~/Documents/deepseek-harness/default-workspace/`

**Проверенный сценарий:** попроси «создай файл snake.py с игрой змейка
на Python» — Harness сам вызовет `write` tool, файл создастся, увидишь
diff-карточку в UI.

**Управление:**

    systemctl --user status deepseek-harness.service
    systemctl --user restart deepseek-harness.service
    journalctl --user -u deepseek-harness.service -f

**Если Harness не видит провайдер:**

1. Проверь `~/.dsh/.env` — должно быть `DEEPSEEK_2API_KEY=sk-...`
2. Проверь `~/.dsh/profiles/web/cordis.patch.yml` — должен содержать
   `providers.deepseek-2api`
3. Перезапусти: `systemctl --user restart deepseek-harness.service`

---

## Браузерные расширения

Если **hCaptcha блокирует Playwright** — используй расширение. Оно
перехватывает токен из твоего обычного браузера.

### Установка

**Chrome / Chromium / Edge / Brave:**

1. Открой `chrome://extensions/`
2. Включи **Developer mode** (тумблер справа сверху)
3. Нажми **Load unpacked**
4. Выбери `~/deepseek-2api-gui/browser-extensions/chrome/`
5. Закрепи иконку на панели

**Firefox:**

1. Открой `about:debugging#/runtime/this-firefox`
2. Нажми **Load Temporary Add-on...**
3. Выбери `~/deepseek-2api-gui/browser-extensions/firefox/manifest.json`

### Использование

1. Открой `chat.deepseek.com`
2. Залогинься вручную (пройди капчу)
3. **Отправь любое сообщение** в чате
4. Расширение перехватит `Authorization` + `Cookie` и POST-нет в наш API
5. Проверь:

       curl -s http://127.0.0.1:8080/gui/accounts | python3 -m json.tool

**Ограничения:**

- Токен перехватывается только когда ты **делаешь запрос** в чате DeepSeek
- Throttle: не чаще 1 раза в 60 секунд
- Никаких внешних запросов — только локальный API

---

## Omarchy плагин

Если Omarchy установлен — installer поставит иконку `󰚩` в бар:

- зелёная — работает, токен валиден
- жёлтая — не авторизован
- оранжевая — сервис не отвечает (кэш)
- красная — сервис не запущен

**Действия:**

- **ЛКМ** — открыть DeepSeek Harness
- **ПКМ** — логи API в терминале
- **СКМ** (средняя кнопка) — перезапуск сервисов

**Если плагин не работает:**

1. Проверь status.sh:

       bash ~/.config/omarchy/plugins/deepseek-2api/status.sh | python3 -m json.tool

2. Если JSON нормальный — перезагрузи shell:

       omarchy-restart-shell

3. Логи плагина: `tail -20 ~/.cache/open-harness.log`

---

## Управление сервисами

    # Статус
    systemctl --user status deepseek-2api.service
    systemctl --user status deepseek-harness.service

    # Перезапуск
    systemctl --user restart deepseek-2api.service
    systemctl --user restart deepseek-harness.service

    # Логи
    journalctl --user -u deepseek-2api.service -f
    journalctl --user -u deepseek-2api.service -n 50

    # Файл лога
    tail -50 ~/.deepseek-2api/logs/app.log

    # Health check
    bash ~/deepseek-2api-gui/verify.sh

    # Удаление
    bash ~/deepseek-2api-gui/UNINSTALL.sh


---

## Конфигурация

Файл `.env` в корне проекта (см. `.env.example`):

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `GUI_HOST` | `127.0.0.1` | Не менять без причины |
| `GUI_PORT` | `8080` | Порт API и GUI |
| `API_MASTER_KEY` | автогенерация | Мастер-ключ API |
| `AUTO_RELOGIN` | `true` | Headless-релогин при истечении токена |
| `MAX_RETRIES` | `2` | Попыток перед сдачей |
| `AUTO_RELOGIN_TIMEOUT` | `180` | Таймаут headless-логина (сек) |
| `AUTO_WEB_SEARCH` | `false` | Автовключать поиск при tool `web_search` |
| `FORCE_THINKING` | `false` | Всегда включать reasoning для всех запросов |
| `FORCE_SEARCH` | `false` | Всегда включать поиск для всех запросов |
| `REQUEST_TIMEOUT` | `300` | Таймаут запросов к DeepSeek |
| `LOG_TO_FILE` | `true` | Писать лог в файл |
| `LOG_ROTATION_MB` | `10` | Размер одного файла лога |
| `LOG_RETENTION` | `5` | Сколько файлов хранить |

**Про `FORCE_*`:** если включить — модель всегда думает / всегда ищет.
Замедляет ответы (+3-10 сек на запрос), но даёт максимальную глубину.

**Рекомендую:** оставить оба `false`. Reasoning доступен через модель
`deepseek-reasoner`, поиск — через tool `web_search` когда явно попросишь.

---

## Архитектура

    Клиент (Chatbox / Harness / curl)
           |
           v
    +--------------------------------------+
    | deepseek-2api (:8080)                |
    |  FastAPI + Provider                  |
    |                                       |
    |  - AccountPool (LRU + RLock)         |
    |  - PowSolver (WASM + wasmtime)       |
    |  - Playwright (persistent context)   |
    |  - ToolBridge (OpenAI <-> DeepSeek)  |
    |  - _request_lock + throttle          |
    +--------------+-----------------------+
                   v
          chat.deepseek.com (web API)

**Компоненты:**

| Файл | Назначение |
|------|-----------|
| `main.py` | Точка входа, прогрев WASM |
| `app/core/config.py` | Pydantic Settings |
| `app/core/storage.py` | Атомарные записи JSON (tmp -> fsync -> rename) |
| `app/core/accounts.py` | Пул аккаунтов (thread-safe RLock) |
| `app/core/logging.py` | loguru + SSE-канал в GUI |
| `app/auth/capture.py` | Playwright: логин + перехват токена |
| `app/providers/deepseek.py` | Ядро: session, PoW, SSE, авторелогин |
| `app/providers/pow_solver.py` | WASM PoW через wasmtime (singleton) |
| `app/providers/tool_bridge.py` | Мост tool_calls OpenAI <-> DeepSeek |
| `app/gui/server.py` | FastAPI роуты |
| `app/gui/static/` | GUI (HTML/CSS/JS) |

**Ключевые особенности:**

**Tool bridge.** DeepSeek web не умеет настоящие `tool_calls`. Мы вкладываем
описание tools в system prompt, парсим его ответ в формате
`<tool_call>{json}</tool_call>` или `<invoke name=...>`, и возвращаем
клиенту правильный OpenAI-формат `tool_calls`.

**Request lock.** DeepSeek блокирует параллельные сессии на одном
аккаунте. Lock сериализует запросы от клиента.

**Throttle 2 сек.** Между запросами пауза, чтобы DeepSeek не отклонял
следующий запрос сразу после предыдущего.

**WASM PoW.** DeepSeek требует решать челлендж `DeepSeekHashV1` перед
каждым запросом. Мы используем WASM-модуль через wasmtime. **Критично:**
Python 3.13+ падает с SIGABRT из-за несовместимости wasmtime.

---

## Разработка

    cd ~/deepseek-2api-gui
    source .venv/bin/activate

    # Зависимости для разработки
    pip install -e ".[dev]"

    # Проверки
    ruff check .          # Линтер
    mypy app              # Тайп-чекер
    pytest -v             # Тесты (47)

---

## Документация

- `docs/INSTALL.md` — детали установки
- `docs/API.md` — справочник API
- `docs/ARCHITECTURE.md` — как устроено
- `docs/TROUBLESHOOTING.md` — решение проблем
- `QUICKSTART.txt` — шпаргалка
- `INSTALL-COMPLETE.md` — полный мануал
- `CHANGELOG.md` — история версий

---

## Roadmap

- [x] v3.0 — базовый прокси
- [x] v3.1 — атомарные записи, тесты, ruff/mypy
- [x] v3.2 — browser extensions, Harness integration
- [x] v3.3 — tool bridge, throttle, force flags
- [ ] v3.4 — persistent streaming, better reconnection
- [ ] v3.5 — tool calling на клиентах без OpenAI-формата
- [ ] v4.0 — мультипровайдер (Gemini, Claude) через один API

---

## Лицензия

MIT — см. `LICENSE`.

---

## Дисклеймер

Проект использует **неофициальный** API `chat.deepseek.com`. Использование
может нарушать ToS DeepSeek. Используй на свой риск и только для личных
целей. Не гоняй большие объёмы, не давай API публичный доступ.

Автор не несёт ответственности за бан аккаунта или другие последствия.

---

## Acknowledgements

- [DeepSeek AI](https://deepseek.com) — за модель
- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) — за агент-харнесс
- [Omarchy](https://omarchy.org) — за прекрасный Linux-дистрибутив
- [Playwright](https://playwright.dev) — за автоматизацию браузера
- [wasmtime](https://wasmtime.dev) — за WASM runtime
