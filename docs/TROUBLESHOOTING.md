# Решение проблем

## Критично: Python 3.13+ не работает

### Симптом

Сервис запускается, но падает каждые несколько минут:

    systemd[1]: deepseek-2api.service: Main process exited, code=dumped, status=6/ABRT
    systemd-coredump: Process NNNN (python) of user 1000 dumped core.

В логах — stack trace с `wasmtime_func_call` и `_ctypes.cpython-3XX`.

### Причина

`wasmtime` (нужен для PoW-челленджа `DeepSeekHashV1`) несовместим с Python
3.13 и 3.14. SIGABRT на вызове WASM через ctypes.

### Решение

Откатиться на Python 3.12:

    mise use -g python@3.12
    cd ~/deepseek-2api-gui
    rm -rf .venv
    mise exec -- python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    systemctl --user restart deepseek-2api.service

### Проверка

    systemctl --user show deepseek-2api.service -p NRestarts

`NRestarts=0` и не растёт.

Отдельный smoke PoW:

    cd ~/deepseek-2api-gui && source .venv/bin/activate
    python -c "from app.providers.pow_solver import PowSolver; \
               s = PowSolver(); \
               a = s.solve('17f75b5e0984f15fc0b8def0c77b48ee4b41b1865f5e8217971722f7870ad4cb', \
                           'cba9b8a9bf8368b6341c', 1785354733914, 144000); \
               print(f'OK: {a}')"

Если печатает число — Python 3.12 работает корректно.

---

## Установка

### `playwright install chromium` падает с `libnss3.so`

    sudo pacman -S nss libxss alsa-lib libcups libdrm libxkbcommon \
        at-spi2-atk at-spi2-core libxcomposite libxdamage libxrandr \
        mesa gtk3 pango cairo

### `python` не найден

Используй `python3` или активируй venv.

### Node.js 26 ломает Harness

В README Harness указано: нужен Node 24.x. На 26.x падает
`import.meta.main`.

    mise use -g node@24
    # или
    nvm install 24 && nvm use 24

---

## Запуск

### Порт 8080 занят

    echo "GUI_PORT=8090" >> .env
    systemctl --user restart deepseek-2api.service

Кто занял:

    ss -tlnp | grep 8080

### Порт 3080 занят (Harness)

    systemctl --user edit deepseek-harness.service
    # добавь в [Service]: ExecStart=... dsh web --port 3090
    systemctl --user daemon-reload
    systemctl --user restart deepseek-harness.service

---

## Логин

### Окно Chromium закрывается сразу

Так и должно быть. После перехвата токена браузер закрывается автоматически.

### Токен не перехватывается

Ты залогинился, но **не отправил сообщение**. Playwright слушает только
API-запросы, а они идут только при отправке сообщения.

Решение: залогинься и **отправь любое сообщение** в чате Deepseek.

### Постоянно просит логин

Профиль Chromium в `~/.deepseek-2api/browser/`. Если Deepseek инвалидирует
сессию — логинься заново.

Сброс:

    rm -rf ~/.deepseek-2api/browser
    systemctl --user restart deepseek-2api.service

---

## API

### `401 Unauthorized: Missing Authorization header`

Заголовок не передан или без `Bearer `:

    -H "Authorization: Bearer sk-..."

### `403 Forbidden: Invalid API Key`

Ключ не совпадает с тем, что в GUI. Скопируй заново.

### `500: Нет доступных аккаунтов`

Пул пуст и `credentials.json` отсутствует. Нажми «Войти в Deepseek».

### Пустой `content` в ответе

Если в ответе только `finish_reason: stop` — модель вернула только
thoughts. Проверь `reasoning_content` (для `deepseek-reasoner`).

### Стрим прерывается через 60 секунд

Nginx-таймаут или другой прокси. Убедись, что запрос идёт напрямую на
`127.0.0.1:8080`.

---

## DeepSeek Harness

### Harness не видит провайдера

Открой `~/.dsh/settings.yaml` и сравни с шаблоном в `install.sh`. Формат
может отличаться в разных версиях Harness. Настрой провайдера вручную
через Web UI `http://127.0.0.1:3080`, потом сравни файл.

### Harness падает при старте

    journalctl --user -u deepseek-harness.service -n 50

Частые причины:

1. **Node.js 26** вместо 24 — `mise use -g node@24`
2. **`~/.dsh/settings.yaml`** в неверном формате — сохрани, удали, запусти
   `install.sh` заново
3. **Порт 3080 занят** — см. выше

### `dsh: command not found`

    npm install -g @deepseek-ai/dsh@latest
    # или
    mise use -g node@24
    mise exec -- npm install -g @deepseek-ai/dsh@latest

---

## Логи

- Консоль (stdout)
- Файл `~/.deepseek-2api/logs/app.log`
- GUI-блок «Логи в реальном времени» (SSE)
- Кнопка «Скачать .log» в GUI
- `journalctl --user -u deepseek-2api.service -f`

### Логи съедают место

Ротация: 10 МБ × 5 файлов. Настройка в `config.py`:

    LOG_ROTATION_MB: int = 10
    LOG_RETENTION: int = 5

Отключить: `LOG_TO_FILE: bool = False`

---

## Аккаунты

### Как добавить вручную

В GUI → «+ Добавить аккаунт вручную»:

- Название (например, `main`)
- Authorization: `Bearer eyJ...` (из DevTools → Network → API-запрос)
- Cookie (опционально, но увеличивает срок жизни)

### Как реактивировать забаненный аккаунт

Кнопка «Активировать». Если Deepseek реально забанил — аккаунт бесполезен.

---

## Полное удаление

    systemctl --user disable --now deepseek-2api.service
    systemctl --user disable --now deepseek-harness.service
    rm -f ~/.config/systemd/user/deepseek-2api.service
    rm -f ~/.config/systemd/user/deepseek-harness.service
    rm -rf ~/deepseek-2api-gui
    rm -rf ~/.deepseek-2api
    rm -rf ~/.dsh
    rm -rf ~/.config/omarchy/plugins/deepseek-2api
