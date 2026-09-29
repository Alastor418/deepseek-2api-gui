# DeepSeek-2API + Harness — полный мануал

**Версия:** 3.2.0
**Тестировано на:** Arch Linux / Omarchy 4 / Hyprland / Wayland

---

## Содержание

1. [Что это](#что-это)
2. [Что устанавливается](#что-устанавливается)
3. [Требования](#требования)
4. [Установка одной командой](#установка-одной-командой)
5. [Первый вход в DeepSeek](#первый-вход-в-deepseek)
6. [Использование API](#использование-api)
7. [DeepSeek Harness](#deepseek-harness)
8. [Omarchy плагин](#omarchy-плагин)
9. [Управление сервисами](#управление-сервисами)
10. [Браузерные расширения](#браузерные-расширения)
11. [Архитектура](#архитектура)
12. [Решение проблем](#решение-проблем)
13. [Удаление](#удаление)

---

## Что это

**DeepSeek-2API** — локальный OpenAI-совместимый прокси для `chat.deepseek.com`.
Работает как обычный API-сервер, но за кулисами управляет живой сессией
браузера через Playwright и решает PoW-челлендж DeepSeek через WebAssembly.

**Что вы получаете:**

- Локальный HTTP-сервер `http://127.0.0.1:8080/v1` с OpenAI API
- Работающие модели `deepseek-chat` и `deepseek-reasoner`
- Reasoning-цепочку в отдельном поле `reasoning_content`
- Автологин через браузер (Playwright)
- Авторелогин при истечении токена
- Мультиаккаунтный пул с ротацией LRU
- Веб-GUI для управления
- Плагин в бар Omarchy
- Интеграцию с DeepSeek Harness (Web UI агента)
- Расширения для Chrome/Firefox (обход hCaptcha)

**Что вы НЕ получаете:**

- Стабильность официального API (это неофициальный прокси)
- Гарантию, что DeepSeek не забанит аккаунт
- Поддержку tools/function-calling (пока нет)

---

## Что устанавливается

Installer создаёт или модифицирует **следующие** файлы и директории:

### Файлы проекта

    ~/deepseek-2api-gui/         — код проекта (весь Python-код)
    ~/deepseek-2api-gui/.venv/   — изолированное окружение Python
    ~/deepseek-2api-gui/install.sh      — этот installer
    ~/deepseek-2api-gui/verify.sh       — health check
    ~/deepseek-2api-gui/UNINSTALL.sh    — удаление
    ~/deepseek-2api-gui/QUICKSTART.txt  — краткая шпаргалка
    ~/deepseek-2api-gui/INSTALL-COMPLETE.md — этот файл

### Данные пользователя

    ~/.deepseek-2api/
      api_key.txt              — мастер-ключ нашего API (chmod 600)
      credentials.json         — legacy (если логинились старым способом)
      accounts/                — пул аккаунтов DeepSeek (*.json)
      browser/                 — профиль Chromium для Playwright
      logs/app.log             — логи с ротацией 10 МБ × 5

### Harness

    ~/.dsh/
      .env                     — мастер-ключ (chmod 600)
      .credentials.yaml        — credential store Harness
      profiles/web/
        package.json           — манифест профиля web
        cordis.patch.yml       — патч: наш провайдер
      sessions/                — сохранённые сессии агента
      storages/                — внутреннее состояние Harness

### systemd

    ~/.config/systemd/user/
      deepseek-2api.service      — наш API
      deepseek-harness.service   — Harness (если установился)

### Omarchy (если есть)

    ~/.config/omarchy/plugins/deepseek-2api/
      manifest.json
      BarWidget.qml
      status.sh
      open-harness.sh
      notify-expired.sh

### Кэши

    ~/.cache/ms-playwright/       — Chromium от Playwright (~500 МБ)
    ~/.cache/deepseek-2api-status.json — кэш для Omarchy-плагина
    ~/.cache/open-harness.log     — лог действий плагина

### Системные пакеты (через pacman, требует sudo)

    nss libxss alsa-lib libcups libdrm libxkbcommon
    at-spi2-atk at-spi2-core libxcomposite libxdamage
    libxrandr mesa gtk3 pango cairo

Это **только** библиотеки, которые нужны Chromium для запуска.
Если они уже стоят — installer не тронет систему.

### Через mise (если нет в системе)

    Python 3.12 (последняя 3.12.x)
    Node.js 24  (для Harness)

### Через npm

    @deepseek-ai/dsh@latest  (глобально, ~500 npm-пакетов)

---

## Требования

### Обязательно

- **Arch Linux** или **Omarchy** (тестировано на Omarchy 4)
- `sudo` доступ (для установки системных библиотек через pacman)
- `rsync`, `curl`, `git` (обычно уже стоят)
- **700 МБ свободного места** (Chromium + Node + Python + npm)
- **Интернет** при первом запуске
- **Аккаунт DeepSeek** (регистрация на chat.deepseek.com)

### Опционально

- **Omarchy** — для интеграции в бар
- **Hyprland** — для корректной работы плагина
- **Chrome / Firefox** — для установки расширения (если hCaptcha)
- **mise** — если хотите автоматическую установку Python/Node

### Известные ограничения

- **Python 3.13+ НЕ РАБОТАЕТ** — wasmtime падает с SIGABRT.
  Installer сам поставит 3.12.
- **Node.js 26.x НЕ РАБОТАЕТ** с Harness — нужен 24.x.
- **hCaptcha** при первом логине может заблокировать Playwright.
  Решение — расширение для браузера (см. ниже).

---

## Установка одной командой

    unzip deepseek-2api-v3.2.0-full.zip
    cd deepseek-2api-v3.2.0-full
    bash install.sh

Installer выполняет **11 шагов** последовательно:

### Шаг 1: Pre-flight проверка

Проверяет ОС, наличие `rsync`, `curl`, `git`. Если чего-то нет — останавливается
и говорит как поставить.

### Шаг 2: Python 3.12

Ищет `python3.12` в системе. Если нет — ставит через `mise`. Если нет ни
того, ни другого — останавливается с инструкцией.

### Шаг 3: Node.js 24

Аналогично Python. Если нет Node 24 — ставит через `mise`. Если mise нет —
пропускает Harness (можно поставить потом).

### Шаг 4: Копирование проекта

Копирует файлы в `~/deepseek-2api-gui`. **Если папка уже существует** —
спросит перезаписать.

### Шаг 5: venv + зависимости

Создаёт `.venv`, ставит `requirements.txt` (1-3 минуты).

### Шаг 6: Системные библиотеки

Проверяет наличие `nss`, `gtk3`, `cairo` и т.д. Если чего-то нет —
**запросит sudo** и поставит через `pacman`. Если они уже стоят — пропускает.

### Шаг 7: Chromium для Playwright

Скачивает Chromium 153 (~170 МБ, 1-3 минуты). Кэширует в
`~/.cache/ms-playwright/`. Если уже есть — пропускает.

### Шаг 8: systemd-сервис API

Создаёт `~/.config/systemd/user/deepseek-2api.service`,
запускает и включает автозапуск.

### Шаг 9: Мастер-ключ

Ждёт, пока сервис сгенерирует `~/.deepseek-2api/api_key.txt`,
читает его.

### Шаг 10: Логин в DeepSeek ⚠️ ИНТЕРАКТИВНЫЙ

Открывает GUI в браузере. Вы должны:

1. Нажать «Войти в Deepseek»
2. Пройти логин
3. **Отправить любое сообщение** в чате
4. Дождаться зелёного статуса
5. Вернуться в терминал и **нажать Enter**

Если hCaptcha блокирует Playwright — installer покажет подсказку про
расширение.

### Шаг 11: Harness + Omarchy

- Ставит `@deepseek-ai/dsh` глобально
- Настраивает `~/.dsh/.env` + `~/.dsh/profiles/web/cordis.patch.yml`
- Создаёт systemd-юнит `deepseek-harness.service`
- Ставит Omarchy-плагин (если Omarchy есть)

### Проверка установки

После installer:

    bash ~/deepseek-2api-gui/verify.sh

Скрипт прогоняет 15+ проверок и говорит что работает, что нет.

---

## Первый вход в DeepSeek

### Способ A: Через GUI (Playwright)

Это основной способ. Installer сам открывает GUI.

1. **Нажмите «Войти в Deepseek»** в GUI
2. Откроется Chromium, залогиньтесь в аккаунт
3. **Отправьте любое сообщение** — например, `test`
   Это критично: Playwright слушает API-запросы, а они идут только
   при отправке сообщения.
4. Браузер закроется автоматически
5. В GUI статус станет зелёным

**Если hCaptcha блокирует** — переходите к способу B.

### Способ B: Через браузерное расширение

Это fallback для случая, когда Playwright не может пройти hCaptcha.

1. Установите расширение:

   **Chrome / Chromium / Edge:**
   - Откройте `chrome://extensions/`
   - Включите **Developer mode** (тумблер в правом верхнем углу)
   - Нажмите **Load unpacked**
   - Выберите `~/deepseek-2api-gui/browser-extensions/chrome/`
   - Закрепите иконку на панели (значок пазла → 📌)

   **Firefox:**
   - Откройте `about:debugging#/runtime/this-firefox`
   - Нажмите **Load Temporary Add-on…**
   - Выберите файл `~/deepseek-2api-gui/browser-extensions/firefox/manifest.json`

2. Откройте `https://chat.deepseek.com/` в браузере
3. Залогиньтесь (пройдите капчу руками)
4. **Отправьте любое сообщение** в чате
5. Расширение перехватит `Authorization` + `Cookie` и POST-нет их
   на `http://127.0.0.1:8080/gui/accounts`
6. В GUI или через `verify.sh` появится аккаунт с меткой `extension`

Проверка:

    curl -s http://127.0.0.1:8080/gui/accounts | python3 -m json.tool

Должен появиться один аккаунт со `status: active`.

**Ограничения расширения:**

- Токен перехватывается только когда вы **делаете запрос** в чате DeepSeek
- Расширение в Firefox живёт до перезапуска браузера (temporary add-on)
- Chrome требует Developer Mode


---

## Использование API

### Base URL

    http://127.0.0.1:8080/v1

### API Key

Смотрите в GUI (кнопка «Копировать») или:

    cat ~/.deepseek-2api/api_key.txt

### Модели

- `deepseek-chat` — обычный чат
- `deepseek-reasoner` — с reasoning_content

### Пример: non-stream

    API_KEY=$(cat ~/.deepseek-2api/api_key.txt)

    curl http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      -d '{
        "model": "deepseek-chat",
        "messages": [{"role":"user","content":"Привет!"}]
      }'

Ответ — обычный JSON в формате OpenAI.

### Пример: stream

    curl -N http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      -d '{
        "model": "deepseek-reasoner",
        "messages": [{"role":"user","content":"Сколько будет 17*23?"}],
        "stream": true
      }'

Ответ — SSE-чанки:

    data: {"delta":{"reasoning_content":"..."}}
    data: {"delta":{"reasoning_content":"..."}}
    ...
    data: {"delta":{"content":"391"}}
    data: [DONE]

Поля delta:

- `role` — в первом чанке
- `reasoning_content` — мысли (только reasoner)
- `content` — финальный текст

### Пример: Python openai

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
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)

### Совместимые клиенты

| Клиент          | Статус           | Как подключить                              |
|-----------------|------------------|---------------------------------------------|
| Chatbox         | ✅ работает      | API Host: `http://127.0.0.1:8080`, Path: `/v1` |
| Open WebUI      | ✅ работает      | Settings → Connections → OpenAI API          |
| Continue.dev    | ✅ работает      | `apiBase: http://127.0.0.1:8080/v1`         |
| Cursor          | ✅ chat          | OpenAI API Base: `http://127.0.0.1:8080/v1` |
| Python openai   | ✅ работает      | См. пример выше                              |
| DeepSeek Harness| ✅ работает      | Installer настраивает автоматически          |

### Ограничения API

- **Tool calling не поддерживается** — только обычный чат
- **Multimodal нет** — только текст
- **Images не передаются**
- **Usage в ответе всегда нулевой** (0 токенов)
- **Streaming только SSE** — не WebSocket

---

## DeepSeek Harness

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) —
официальный agent harness от DeepSeek AI с Web UI. Installer настраивает
его автоматически.

### Что делает installer

1. Устанавливает `@deepseek-ai/dsh` глобально через npm
2. Прогревает профиль `web` (создаёт `~/.dsh/profiles/web/`)
3. Записывает `~/.dsh/.env` с нашим мастер-ключом
4. Пишет `~/.dsh/profiles/web/cordis.patch.yml` с провайдером `deepseek-2api`
5. Создаёт systemd-юнит `deepseek-harness.service`
6. Запускает его

### Как открыть

Harness слушает на `http://127.0.0.1:3080`. При старте генерирует
одноразовый токен-URL. Найти его можно:

    journalctl --user -u deepseek-harness.service --no-pager \
      | grep -oE 'http://127\.0\.0\.1:3080/\?token=[A-Za-z0-9_-]+' | tail -1

Открыть:

    xdg-open "$(journalctl --user -u deepseek-harness.service --no-pager \
      | grep -oE 'http://127\.0\.0\.1:3080/\?token=[A-Za-z0-9_-]+' | tail -1)"

Или через Omarchy-плагин: **ЛКМ** по иконке 󰚩 в баре.

### Как использовать

1. Откройте Harness
2. В селекторе модели должен быть **`DeepSeek 2API (local)`**
3. Пишите сообщения — они пойдут через наш API

Если селектор показывает `deepseek-official` — значит конфиг
не подхватился. Проверьте:

    dsh --dump-config --profile web | grep -A 3 "agent-default-model"

Должно быть `provider: deepseek-2api`.

### Управление

    systemctl --user status deepseek-harness.service
    systemctl --user restart deepseek-harness.service
    systemctl --user stop deepseek-harness.service
    journalctl --user -u deepseek-harness.service -f

### Если Harness не видит наш провайдер

1. Проверьте `~/.dsh/.env`:

       cat ~/.dsh/.env
       # должно быть: DEEPSEEK_2API_KEY=sk-...

2. Проверьте `~/.dsh/profiles/web/cordis.patch.yml`:

       cat ~/.dsh/profiles/web/cordis.patch.yml
       # должно содержать block с providers.deepseek-2api

3. Перезапустите:

       systemctl --user restart deepseek-harness.service

4. Если всё ещё не работает — запустите `verify.sh`, он покажет что не так.

---

## Omarchy плагин

Если у вас Omarchy — installer автоматически поставит плагин в бар.

### Как выглядит

Иконка **󰚩** в правой части бара. Цвет:

- 🟢 **зелёная** — API работает, токен валиден
- 🟡 **жёлтая** — не авторизован (нужно залогиниться)
- 🟠 **оранжевая** — API не отвечает, показан кэш
- 🔴 **красная** — сервис не запущен

### Действия

- **ЛКМ** — открыть DeepSeek Harness (с авто-стартом, если не запущен)
- **ПКМ** — логи API в терминале (откроет foot / kitty / alacritty)
- **СКМ** (средняя кнопка) — перезапуск обоих сервисов

### Тултип

При наведении показывает:

- Версия API
- Количество активных аккаунтов
- Доступные модели
- Статус (работает / не авторизован / из кэша)

### Если плагин не работает

1. Проверьте, что `status.sh` работает:

       bash ~/.config/omarchy/plugins/deepseek-2api/status.sh | python3 -m json.tool

2. Если JSON нормальный — перезагрузите shell:

       omarchy-restart-shell

3. Если JSON пустой — API не отвечает. Проверьте:

       systemctl --user status deepseek-2api.service
       curl -s http://127.0.0.1:8080/gui/status

4. Логи плагина:

       tail -20 ~/.cache/open-harness.log

---

## Управление сервисами

### Основные команды

    # Статус
    systemctl --user status deepseek-2api.service
    systemctl --user status deepseek-harness.service

    # Перезапуск
    systemctl --user restart deepseek-2api.service
    systemctl --user restart deepseek-harness.service

    # Остановка
    systemctl --user stop deepseek-2api.service
    systemctl --user stop deepseek-harness.service

    # Автозапуск (включить / отключить)
    systemctl --user enable deepseek-2api.service
    systemctl --user disable deepseek-2api.service

### Логи

    # Живой поток
    journalctl --user -u deepseek-2api.service -f

    # Последние 50 строк
    journalctl --user -u deepseek-2api.service -n 50

    # С фильтром по времени
    journalctl --user -u deepseek-2api.service --since "1 hour ago"

    # Файл лога с ротацией
    tail -50 ~/.deepseek-2api/logs/app.log

### Health check

    bash ~/deepseek-2api-gui/verify.sh

Скрипт проверит:
- Файлы и права доступа
- systemd-сервисы (active/enabled)
- API эндпоинты (401/403/200)
- Наличие активных аккаунтов
- Harness URL
- Omarchy-плагин
- Расширения браузера

И покажет итог: X passed, Y failed.

---

## Браузерные расширения

Расширения для Chrome / Firefox, которые перехватывают токен DeepSeek
и отправляют его нашему API. Полезны если:

- Playwright не может пройти hCaptcha
- Вы не хотите давать Playwright доступ к вашему аккаунту
- У вас несколько аккаунтов (можно накликать токенов из каждого)

### Установка

**Chrome / Chromium / Edge / Brave:**

1. `chrome://extensions/`
2. Developer mode → ON
3. Load unpacked → `~/deepseek-2api-gui/browser-extensions/chrome/`
4. Закрепить на панели

**Firefox:**

1. `about:debugging#/runtime/this-firefox`
2. Load Temporary Add-on… → `browser-extensions/firefox/manifest.json`
3. Иконка появится в панели

Для **постоянной** установки в Firefox нужно подписать расширение —
это выходит за рамки данного мануала.

### Использование

1. Откройте `chat.deepseek.com`
2. Залогиньтесь (если ещё нет)
3. **Отправьте любое сообщение**
4. Расширение автоматически перехватит `Authorization` + `Cookie`
   и POST-нет на `/gui/accounts`

Проверка:

    curl -s http://127.0.0.1:8080/gui/accounts | python3 -m json.tool

**Popup расширения:**

Кликните по иконке расширения — там:

- **Статус** — когда последний раз отправляли, что ответил сервер
- **Адрес сервера** — можно поменять порт если API на другом
- **Кнопка «Отправить токен сейчас»** — повторная отправка последнего токена

### Throttle

Расширение отправляет токен не чаще **одного раза в 60 секунд**.
Это сделано чтобы не спамить API при активном использовании DeepSeek
в браузере.

### Безопасность

- Расширение ничего никуда не логирует, кроме локального API
- Никаких внешних запросов
- Токен хранится только в `browser.storage.local`
- Видны только запросы к `chat.deepseek.com/api/*`


---

## Архитектура

### Общая схема

    Пользователь ─┬─> Harness UI (:3080) ──┐
                  │                        │
                  └─> GUI (:8080) ─────────┤
                                           ▼
                                   deepseek-2api (:8080)
                                           │
                       ┌───────────────────┼───────────────────┐
                       ▼                   ▼                   ▼
                  AccountPool         PowSolver          Playwright
                  (LRU, RLock)      (WASM + wasmtime)   (persistent ctx)
                       │                   │
                       └─────────┬─────────┘
                                 ▼
                        chat.deepseek.com (web API)
                                 │
                                 ▼
                         SSE-стрим JSON-Patch
                                 │
                                 ▼
                     конвертация в OpenAI-формат

### Компоненты

| Файл                              | Назначение                                                |
|-----------------------------------|-----------------------------------------------------------|
| `main.py`                         | Точка входа, прогрев WASM, открытие браузера              |
| `app/core/config.py`              | Pydantic Settings, читает `.env`                          |
| `app/core/storage.py`             | `credentials.json` + `api_key.txt`, атомарные записи      |
| `app/core/accounts.py`            | Пул аккаунтов (thread-safe RLock)                         |
| `app/core/logging.py`             | loguru: консоль + файл + SSE-канал в GUI                  |
| `app/auth/capture.py`             | Playwright: логин, перехват `Authorization`/`Cookie`      |
| `app/providers/base.py`           | ABC для провайдеров                                       |
| `app/providers/deepseek.py`       | Ядро: session, PoW, SSE-парсер, авторелогин               |
| `app/providers/pow_solver.py`     | WASM PoW через wasmtime (singleton, Lock)                 |
| `app/schemas.py`                  | Pydantic-схемы API и GUI                                  |
| `app/gui/server.py`               | FastAPI: роуты `/`, `/gui/*`, `/v1/*`                     |
| `app/gui/static/`                 | index.html, style.css, app.js                             |

### Жизненный цикл запроса

1. Клиент шлёт `POST /v1/chat/completions` с `Bearer sk-...`
2. FastAPI проверяет ключ через `secrets.compare_digest`
3. Pydantic валидирует `ChatCompletionRequest`
4. `DeepseekProvider.chat_completion`:
   - resolve model (aliases, reasoner → `thinking_enabled=True`)
   - `_with_retry()`:
     - `_pick_account()` — LRU выбор из пула
     - `_prepare()` — создаёт `chat_session_id`, решает PoW
     - При `_InvalidToken` → `_auto_relogin()` → повтор
   - `_handle_stream()` или `_handle_non_stream()`
5. `_raw_stream()` — httpx SSE-стрим от Deepseek
6. `_extract_delta()` — парсит JSON-Patch, разделяет `content` и `reasoning`
7. Ответ отдаётся в OpenAI-формате (SSE или JSON)

### PoW (Proof of Work)

Deepseek требует перед каждым запросом решать челлендж:

1. `POST /chat/create_pow_challenge` → получаем `challenge`, `salt`, `expire_at`, `difficulty`
2. Формируем префикс `salt_expire_at_`
3. Вызываем WASM `wasm_solve` (sha3, bruteforce) через wasmtime
4. Получаем `answer`, кодируем base64 → заголовок `x-ds-pow-response`

**Критично:** wasmtime падает с SIGABRT на Python 3.13+. Нужен **3.12**.

### Кэш директории

    ~/.cache/ms-playwright/          — Chromium (500 МБ)
    ~/.cache/deepseek-2api-status.json — статус для Omarchy-плагина
    ~/.cache/open-harness.log        — лог действий плагина
    ~/.cache/deepseek-2api-token-notified — кулдаун notify-expired

---

## Решение проблем

### Критично: Python 3.13+ не работает

**Симптом:** сервис падает каждые несколько минут, `code=dumped, status=6/ABRT`.

**Причина:** wasmtime несовместим с Python 3.13 и 3.14.

**Решение:**

    mise use -g python@3.12
    cd ~/deepseek-2api-gui
    rm -rf .venv
    mise exec -- python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    systemctl --user restart deepseek-2api.service

**Проверка:**

    systemctl --user show deepseek-2api.service -p NRestarts
    # Должно быть NRestarts=0 и не расти

### hCaptcha не проходит

**Симптом:** Playwright не может залогиниться, висит на капче.

**Решение:** установите расширение для браузера (см. выше).

### Node.js 26 ломает Harness

**Симптом:** `dsh web` падает с `import.meta.main`.

**Решение:**

    mise use -g node@24
    hash -r
    systemctl --user restart deepseek-harness.service

### Порт 8080 занят

**Решение:**

    # Кто занял
    ss -tlnp | grep 8080

    # Убить (если это старый процесс)
    sudo lsof -i :8080
    kill <PID>

Или поменяйте порт в `~/deepseek-2api-gui/.env`:

    GUI_PORT=8090

Не забудьте обновить `cordis.patch.yml` (baseURL) и перезапустить оба сервиса.

### Токен не перехватывается Playwright

**Причина:** вы залогинились, но **не отправили сообщение**.

**Решение:** залогиньтесь и **отправьте любое сообщение** в чате Deepseek.

### API возвращает `500: Нет доступных аккаунтов`

**Причина:** пул аккаунтов пуст и `credentials.json` отсутствует.

**Решение:** залогиньтесь через GUI или расширение.

Проверка:

    curl -s http://127.0.0.1:8080/gui/accounts | python3 -m json.tool

### Harness не видит провайдера `deepseek-2api`

**Проверка 1:** ключ в `~/.dsh/.env`

    cat ~/.dsh/.env
    # DEEPSEEK_2API_KEY=sk-...

**Проверка 2:** патч-файл

    dsh --dump-config --profile web | grep -A 3 "agent-default-model"
    # provider: deepseek-2api

**Решение:** переустановить конфиг

    bash ~/deepseek-2api-gui/install.sh
    # На вопрос о перезаписи → N
    # Установить только Harness-часть вручную — см. install.sh

Или вручную:

    systemctl --user stop deepseek-harness.service
    rm -rf ~/.dsh/profiles/web
    dsh web --no-open &  # прогреется
    # Затем скопируйте cordis.patch.yml из шаблона installer'а

### Omarchy-иконка красная

**Проверка:**

    bash ~/.config/omarchy/plugins/deepseek-2api/status.sh | python3 -m json.tool

Если JSON пустой или `cached: true` — API не отвечает:

    systemctl --user status deepseek-2api.service
    journalctl --user -u deepseek-2api.service -n 30

### ПКМ в Omarchy не открывает терминал

**Причина:** в системе нет `alacritty`, а старый BarWidget был захардкожен на него.

**Решение:** обновите `BarWidget.qml` (в installer уже новый). Проверьте:

    grep -A5 "RightButton" ~/.config/omarchy/plugins/deepseek-2api/BarWidget.qml
    # Должен быть fallback: xdg-terminal-exec → omarchy-launch-terminal → foot → kitty → alacritty

### Стрим прерывается через 60 секунд

**Причина:** прокси или nginx-таймаут. Мы используем `httpx.Timeout(60, read=300)`.

**Решение:** убедитесь, что клиент идёт напрямую на `127.0.0.1:8080`, а не через прокси.

### Логи съедают место

**Ротация по умолчанию:** 10 МБ × 5 файлов.

**Настройка** в `app/core/config.py`:

    LOG_ROTATION_MB: int = 10
    LOG_RETENTION: int = 5

**Отключить полностью:**

    LOG_TO_FILE: bool = False

### systemd жалуется `State 'stop-sigterm' timed out. Killing.`

**Причина:** в фоновом thread висит `asyncio.to_thread` (прогрев WASM).
Python не может прервать поток.

**Это не критично** — следующая перезагрузка проходит чисто. `KillMode=mixed`
и `SendSIGKILL=yes` гарантируют что cgroup будет убита.

**Если критично** — уберите `_warm_up_pow()` из `app/gui/server.py`.

### `dsh: command not found` после установки

    hash -r  # обновить кэш
    which dsh

Если пусто — проверьте `mise`:

    mise exec -- which dsh
    mise use -g node@24
    mise exec -- npm install -g @deepseek-ai/dsh@latest

---

## Удаление

### Полное удаление

    bash ~/deepseek-2api-gui/UNINSTALL.sh

Скрипт:

1. Остановит и отключит systemd-сервисы
2. Удалит unit-файлы
3. Удалит `~/deepseek-2api-gui`
4. Удалит `~/.deepseek-2api` (аккаунты, ключ, логи)
5. Удалит `~/.dsh` (конфиг Harness)
6. Удалит Omarchy-плагин
7. **Спросит** про удаление Chromium от Playwright (~500 МБ)
8. **Спросит** про удаление npm-пакета `@deepseek-ai/dsh`

### Ручное удаление

Если скрипт недоступен:

    systemctl --user disable --now deepseek-2api.service deepseek-harness.service
    rm -f ~/.config/systemd/user/deepseek-2api.service
    rm -f ~/.config/systemd/user/deepseek-harness.service
    systemctl --user daemon-reload

    rm -rf ~/deepseek-2api-gui
    rm -rf ~/.deepseek-2api
    rm -rf ~/.dsh
    rm -rf ~/.config/omarchy/plugins/deepseek-2api

    # Опционально
    rm -rf ~/.cache/ms-playwright
    npm uninstall -g @deepseek-ai/dsh

### Что остаётся после удаления

Если не делать опциональные шаги:

- `~/.cache/ms-playwright/` — Chromium (500 МБ)
- npm-пакет `@deepseek-ai/dsh` (в `~/.local/share/mise/.../node/24/`)

Python 3.12 и Node.js 24 (поставленные через mise) остаются — они могут
использоваться другими проектами.

---

## FAQ

### Это безопасно?

В целом да, но:

- Это **неофициальный** прокси — может нарушать ToS DeepSeek
- Ваш аккаунт DeepSeek может быть забанен
- Не используйте для критичных задач

Рекомендации:

- Используйте отдельный аккаунт DeepSeek (не основной)
- Не гоняйте большие объёмы
- Не давайте API публичный доступ

### Сколько стоит?

Бесплатно. DeepSeek web API бесплатный для личного использования.
Вы платите только за электричество и трафик.

### Какие лимиты?

DeepSeek web имеет rate limit, но точных чисел нет. Наш прокси не
добавляет своих лимитов.

### Можно ли использовать на нескольких машинах?

Да, но каждая машина имеет свой `~/.deepseek-2api/api_key.txt`.
Клиенты должны использовать ключ той машины, где запущен сервис.

### Как добавить ещё аккаунт DeepSeek?

Через расширение в браузере:

1. Откройте `chat.deepseek.com` в новой вкладке
2. Залогиньтесь во второй аккаунт
3. Отправьте сообщение
4. Расширение добавит аккаунт в пул
5. Теперь их два — API будет чередовать через LRU

Проверка:

    curl -s http://127.0.0.1:8080/gui/accounts | python3 -m json.tool

### Почему ответ приходит медленно?

Первые несколько секунд — это:

1. Решение PoW (144000 difficulty) — 0.3-1 сек
2. Создание `chat_session_id` — ~0.5 сек
3. Сама модель — зависит от длины

Хотите быстрее — используйте `deepseek-chat` (без `thinking`).
`deepseek-reasoner` тратит время на reasoning_content.

### Что делать если `verify.sh` показывает FAIL?

1. Запустите: `journalctl --user -u deepseek-2api.service -n 50`
2. Смотрите последнюю ошибку
3. Ищите её в секции «Решение проблем» выше
4. Если не нашли — создайте issue на GitHub с логом

### Можно ли использовать в Docker?

Технически да, но нужны:

- X11/Wayland для Playwright (или `xvfb-run`)
- `--cap-add=SYS_ADMIN` для установки Chromium
- Правильная передача `~/.deepseek-2api/`

Проще всего — установить на хост, а API слушать на `0.0.0.0`
(**не рекомендуется** без firewall).

### Как обновить?

    cd ~/deepseek-2api-gui
    git pull   # или распакуйте новый архив
    source .venv/bin/activate
    pip install -r requirements.txt
    systemctl --user restart deepseek-2api.service
    systemctl --user restart deepseek-harness.service

Миграция данных не нужна — формат JSON-файлов стабилен.

### Где взять исходники?

    ~/deepseek-2api-gui/  — весь код

Или на GitHub: `https://github.com/USERNAME/deepseek-2api-gui`

### Как контрибьютить?

1. Fork на GitHub
2. Создайте feature-ветку
3. `pytest`, `ruff check .`, `mypy app` — всё должно быть зелёным
4. Pull Request

---

## Итог

После установки у вас есть:

- ✅ Локальный OpenAI-совместимый API
- ✅ Работающие модели `deepseek-chat` и `deepseek-reasoner`
- ✅ Веб-GUI для управления
- ✅ DeepSeek Harness с Web UI агента
- ✅ Плагин в баре Omarchy
- ✅ Расширения для Chrome/Firefox (обход hCaptcha)
- ✅ systemd-сервисы с автозапуском
- ✅ 47 тестов (pytest) + чистый ruff + mypy

Если что-то сломалось — `bash ~/deepseek-2api-gui/verify.sh`.

Если хотите удалить — `bash ~/deepseek-2api-gui/UNINSTALL.sh`.

Удачи!

---

*DeepSeek-2API v3.2.0 — MIT License*
