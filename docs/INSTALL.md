# Детали установки

## Что делает `install.sh`

Полная последовательность:

1. **Проверка зависимостей** — `rsync`, `curl`, `git`, Python 3.12, Node 24
2. **Установка Python 3.12** через `mise`, если нет
3. **Установка Node.js 24** через `mise`, если нет
4. **Копирование проекта** в `~/deepseek-2api-gui`
5. **Создание venv** и установка `requirements.txt`
6. **Скачивание Chromium** для Playwright (~170 МБ)
7. **Установка systemd unit** `deepseek-2api.service`, запуск
8. **Ожидание `~/.deepseek-2api/api_key.txt`** — генерируется при старте
9. **Открытие GUI** в браузере и **ожидание Enter** (после логина в Deepseek)
10. **Установка npm-пакета** `@deepseek-ai/dsh`, если нет
11. **Генерация `~/.dsh/settings.yaml`** и `~/.dsh/.credentials.yaml`
12. **Установка systemd unit** `deepseek-harness.service`, запуск
13. **Установка Omarchy-плагина** (если Omarchy есть)

## Где что лежит

    ~/deepseek-2api-gui/             # код проекта
      .venv/                         # виртуальное окружение
      app/                           # Python-код
      docs/                          # документация
      install.sh                     # этот installer

    ~/.deepseek-2api/                # данные пользователя
      api_key.txt                    # мастер-ключ нашего API (chmod 600)
      credentials.json               # legacy
      accounts/                      # пул аккаунтов (*.json, chmod 600)
      browser/                       # профиль Chromium
      logs/app.log                   # логи (ротация 10 МБ × 5)

    ~/.dsh/                          # конфиг DeepSeek Harness
      settings.yaml                  # провайдеры и модели
      .credentials.yaml              # мастер-ключ (chmod 600)

    ~/.config/systemd/user/
      deepseek-2api.service
      deepseek-harness.service

    ~/.config/omarchy/plugins/deepseek-2api/
      manifest.json
      BarWidget.qml
      status.sh
      open-harness.sh
      notify-expired.sh

    ~/.cache/
      ms-playwright/                 # Chromium
      deepseek-2api-status.json      # кэш статуса для Omarchy-плагина
      deepseek-2api-token-notified   # кулдаун notify-expired
      open-harness.log               # лог open-harness.sh

## Ручная установка (без `install.sh`)

    git clone https://github.com/USERNAME/deepseek-2api-gui.git
    cd deepseek-2api-gui
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    playwright install chromium
    python main.py

Первый запуск откроет браузер с GUI.

## Настройки через `.env`

    cp .env.example .env
    $EDITOR .env

| Переменная | По умолчанию | Описание |
|---|---|---|
| `GUI_HOST` | `127.0.0.1` | Не менять без причины! |
| `GUI_PORT` | `8080` | Порт API и GUI |
| `API_MASTER_KEY` | автогенерация | Мастер-ключ API |
| `AUTO_RELOGIN` | `true` | Headless-релогин |
| `MAX_RETRIES` | `2` | Попыток перед сдачей |
| `AUTO_RELOGIN_TIMEOUT` | `180` | Таймаут логина (сек) |
| `REQUEST_TIMEOUT` | `300` | Таймаут запросов к Deepseek |
| `LOG_TO_FILE` | `true` | Писать в файл |
| `LOG_ROTATION_MB` | `10` | Размер одного файла |
| `LOG_RETENTION` | `5` | Сколько файлов хранить |

## Как это связано с DeepSeek Harness

Схема:

    Пользователь → Harness (:3080)
                     │
                     ▼
               custom provider
             (baseURL из settings.yaml)
                     │
                     ▼
           http://127.0.0.1:8080/v1
                     │
                     ▼
            deepseek-2api (:8080)
                     │
                     ▼
          chat.deepseek.com (web API)

Harness **не** ходит в DeepSeek напрямую — он ходит в наш прокси как в
обычный OpenAI-совместимый endpoint. Прокси уже сам управляет PoW,
аккаунтами, авторелогином и трансляцией ответа.

## Ручная правка `~/.dsh/settings.yaml`

Если installer сгенерировал неверный формат — правишь руками.

Формат может отличаться в разных версиях Harness. Самый надёжный способ
узнать актуальный — открыть `~/.dsh/settings.yaml` после первого запуска
`dsh web` с провайдером, добавленным через UI.

Наш шаблон (best guess на момент v3.1.0):

    llm-pi-ai:
      providers:
        deepseek-2api:
          type: openai-completions
          baseURL: http://127.0.0.1:8080/v1
          apiKeyEnv: DEEPSEEK_2API_KEY
          models:
            - id: deepseek-chat
              name: DeepSeek Chat
            - id: deepseek-reasoner
              name: DeepSeek Reasoner
      default:
        provider: deepseek-2api
        model: deepseek-chat

Мастер-ключ — в `~/.dsh/.credentials.yaml`:

    DEEPSEEK_2API_KEY: sk-xxxxxxxxxxxxxxxxxxxxxxxx

## Проверка работоспособности

API:

    curl -s http://127.0.0.1:8080/gui/status | python3 -m json.tool

Ожидаем `"authenticated": true`, `"accounts_active": 1`.

Chat completion:

    API_KEY=$(cat ~/.deepseek-2api/api_key.txt)
    curl -N http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"stream":true}'

Harness:

    systemctl --user status deepseek-harness.service
    journalctl --user -u deepseek-harness.service -n 30

## Обновление

    cd ~/deepseek-2api-gui
    git pull
    source .venv/bin/activate
    pip install -r requirements.txt
    systemctl --user restart deepseek-2api.service
    systemctl --user restart deepseek-harness.service

Миграция данных не нужна — формат JSON-файлов стабилен.

## Ручная правка `~/.dsh/settings.yaml`

Если installer сгенерировал неверный формат — правишь руками.

Формат может отличаться в разных версиях Harness. Самый надёжный способ
узнать актуальный — открыть `~/.dsh/settings.yaml` после первого запуска
`dsh web` с провайдером, добавленным через UI.

Наш шаблон (best guess на момент v3.1.0):

    llm-pi-ai:
      providers:
        deepseek-2api:
          type: openai-completions
          baseURL: http://127.0.0.1:8080/v1
          apiKeyEnv: DEEPSEEK_2API_KEY
          models:
            - id: deepseek-chat
              name: DeepSeek Chat
            - id: deepseek-reasoner
              name: DeepSeek Reasoner
      default:
        provider: deepseek-2api
        model: deepseek-chat

Мастер-ключ — в `~/.dsh/.credentials.yaml`:

    DEEPSEEK_2API_KEY: sk-xxxxxxxxxxxxxxxxxxxxxxxx

## Проверка работоспособности

API:

    curl -s http://127.0.0.1:8080/gui/status | python3 -m json.tool

Ожидаем `"authenticated": true`, `"accounts_active": 1`.

Chat completion:

    API_KEY=$(cat ~/.deepseek-2api/api_key.txt)
    curl -N http://127.0.0.1:8080/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $API_KEY" \
      -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"stream":true}'

Harness:

    systemctl --user status deepseek-harness.service
    journalctl --user -u deepseek-harness.service -n 30

## Обновление

    cd ~/deepseek-2api-gui
    git pull
    source .venv/bin/activate
    pip install -r requirements.txt
    systemctl --user restart deepseek-2api.service
    systemctl --user restart deepseek-harness.service

Миграция данных не нужна — формат JSON-файлов стабилен.
