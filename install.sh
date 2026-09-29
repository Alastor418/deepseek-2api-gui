#!/usr/bin/env bash
# ============================================================
# Deepseek-2api GUI v3.1.0 — автоматический установщик
# ============================================================
# Что делает:
#   1. Проверяет зависимости (Python 3.12, Node 24, rsync, curl, git)
#   2. Устанавливает наш проект в ~/deepseek-2api-gui
#   3. Создаёт venv, ставит pip-зависимости, скачивает Chromium
#   4. Ставит и запускает systemd-сервис deepseek-2api
#   5. Ждёт, пока ты залогинишься через GUI
#   6. Генерирует ~/.dsh/settings.yaml с мастер-ключом нашего API
#   7. Ставит и запускает DeepSeek Harness
#   8. Ставит Omarchy-плагин (если Omarchy установлен)
#
# Запуск:
#   bash install.sh
# ============================================================

set -euo pipefail

# ---------- colors ----------
C_RESET='\033[0m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[1;33m'
C_RED='\033[0;31m'
C_BLUE='\033[0;34m'
C_DIM='\033[2m'

log()  { echo -e "${C_BLUE}[*]${C_RESET} $1"; }
ok()   { echo -e "${C_GREEN}[✓]${C_RESET} $1"; }
warn() { echo -e "${C_YELLOW}[!]${C_RESET} $1"; }
err()  { echo -e "${C_RED}[✗]${C_RESET} $1"; }
dim()  { echo -e "${C_DIM}$1${C_RESET}"; }

die() { err "$1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/deepseek-2api-gui"
DSH_DIR="$HOME/.dsh"
DS2API_DIR="$HOME/.deepseek-2api"
REQUIRED_PY="3.12"
REQUIRED_NODE_MAJOR="24"

echo
echo "╔══════════════════════════════════════════════════════════╗"
echo "║      Deepseek-2api GUI v3.3.1 + DeepSeek Harness         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo

# ============================================================
# 1. Базовые утилиты
# ============================================================
log "Проверяю базовые зависимости..."
for cmd in rsync curl git; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        die "$cmd не найден. Установи: sudo pacman -S $cmd"
    fi
done
ok "rsync, curl, git — на месте"

# ============================================================
# 2. Python 3.12 (обязательно!)
# ============================================================
log "Проверяю Python $REQUIRED_PY (wasmtime несовместим с 3.13+)..."

PY_BIN=""
for candidate in python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        VERSION=$("$candidate" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        if [ "$VERSION" = "$REQUIRED_PY" ]; then
            PY_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PY_BIN" ]; then
    if command -v mise >/dev/null 2>&1; then
        log "Python $REQUIRED_PY не найден. Ставлю через mise..."
        mise use -g python@$REQUIRED_PY
        PY_BIN="$(mise exec -- which python3.12 2>/dev/null || true)"
    fi
fi

if [ -z "$PY_BIN" ]; then
    err "Python $REQUIRED_PY обязателен, но не найден."
    echo
    echo "  Варианты установки:"
    echo "    • Через mise:    mise use -g python@$REQUIRED_PY"
    echo "    • Через pacman:  yay -S python312"
    echo "    • Через pyenv:   pyenv install 3.12.7"
    echo
    echo "  ⚠ Python 3.13+ НЕ подходит — wasmtime падает с SIGABRT."
    die "Установи Python $REQUIRED_PY и перезапусти install.sh"
fi
ok "Python $REQUIRED_PY найден: $PY_BIN"

# ============================================================
# 3. Node.js 24 (не 26!)
# ============================================================
log "Проверяю Node.js $REQUIRED_NODE_MAJOR..."

NODE_OK=false
if command -v node >/dev/null 2>&1; then
    NODE_MAJOR=$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)
    if [ "$NODE_MAJOR" = "$REQUIRED_NODE_MAJOR" ]; then
        NODE_OK=true
        ok "Node.js v$(node --version) — подходит"
    else
        warn "Node.js v$(node --version) — не подходит (нужен $REQUIRED_NODE_MAJOR.x)"
    fi
fi

if [ "$NODE_OK" = false ]; then
    if command -v mise >/dev/null 2>&1; then
        log "Ставлю Node.js $REQUIRED_NODE_MAJOR через mise..."
        mise use -g node@$REQUIRED_NODE_MAJOR
        eval "$(mise activate bash --shims)" 2>/dev/null || true
        export PATH="$(mise exec -- sh -c 'echo $PATH')"
        ok "Node.js $(node --version) готов"
    else
        warn "mise не найден, Node.js $REQUIRED_NODE_MAJOR не установлен."
        warn "Установи вручную: mise install (или nvm install 24)"
        warn "Harness будет пропущен. Можно доустановить позже."
    fi
fi

# ============================================================
# 4. Наш проект
# ============================================================
if [ -d "$INSTALL_DIR" ]; then
    warn "Папка $INSTALL_DIR уже существует"
    read -rp "Перезаписать её? [y/N] " ans
    if [[ ! "$ans" =~ ^[Yy]$ ]]; then
        die "Отменено пользователем"
    fi
    rm -rf "$INSTALL_DIR"
fi

log "Копирую проект в $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
    "$SCRIPT_DIR/" "$INSTALL_DIR/"
ok "Проект скопирован"

# ============================================================
# 5. venv + зависимости
# ============================================================
log "Создаю виртуальное окружение..."
cd "$INSTALL_DIR"
"$PY_BIN" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

ACTUAL=$(python --version | grep -oE '[0-9]+\.[0-9]+')
if [ "$ACTUAL" != "$REQUIRED_PY" ]; then
    die "venv создан с Python $ACTUAL, нужен $REQUIRED_PY"
fi

pip install --upgrade pip setuptools wheel --quiet
ok "venv готов (Python $ACTUAL)"

log "Устанавливаю Python-зависимости (1-3 минуты)..."
pip install -r requirements.txt --quiet
ok "Зависимости установлены"

# ============================================================
# 6. Chromium для Playwright
# ============================================================
if [ ! -d "$HOME/.cache/ms-playwright" ]; then
    log "Скачиваю Chromium для Playwright (~170 МБ)..."
    playwright install chromium
    ok "Chromium установлен"
else
    ok "Chromium уже установлен"
fi

# ============================================================
# 7. systemd unit для deepseek-2api
# ============================================================
log "Устанавливаю systemd-сервис deepseek-2api..."
mkdir -p "$HOME/.config/systemd/user"
cp "$INSTALL_DIR/systemd/deepseek-2api.service" \
   "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now deepseek-2api.service
ok "Сервис deepseek-2api запущен"

# ============================================================
# 8. Ждём api_key.txt
# ============================================================
log "Жду генерации мастер-ключа нашего API..."
KEY_FILE="$DS2API_DIR/api_key.txt"
for _ in $(seq 1 30); do
    if [ -f "$KEY_FILE" ]; then
        break
    fi
    sleep 1
done

if [ ! -f "$KEY_FILE" ]; then
    die "Мастер-ключ не появился за 30 секунд. Проверь: journalctl --user -u deepseek-2api.service -n 50"
fi

API_KEY="$(cat "$KEY_FILE")"
ok "Мастер-ключ получен: ${API_KEY:0:12}…"

# ============================================================
# 9. Ожидание логина в Deepseek
# ============================================================
echo
echo "╔══════════════════════════════════════════════════════════╗"
echo "║             ТРЕБУЕТСЯ ЛОГИН В DEEPSEEK                   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo
echo "  1. Сейчас откроется браузер с GUI:  http://127.0.0.1:8080"
echo "  2. Нажми кнопку «Войти в Deepseek»"
echo "  3. Залогинься в открывшемся Chromium и ОТПРАВЬ ЛЮБОЕ СООБЩЕНИЕ"
echo "     в чате Deepseek (это нужно, чтобы мы перехватили токен)."
echo
echo "  Когда увидишь зелёный статус в GUI — вернись сюда и нажми Enter."
echo

sleep 2
xdg-open "http://127.0.0.1:8080" >/dev/null 2>&1 || \
    warn "Не удалось открыть браузер. Открой вручную: http://127.0.0.1:8080"

read -rp "Нажми Enter когда закончишь логин... "

# Проверим, что токен действительно получен
AUTH_STATUS="$(curl -s --max-time 5 http://127.0.0.1:8080/gui/status \
    | python3 -c 'import sys,json; print(json.load(sys.stdin).get("authenticated", False))' \
    2>/dev/null || echo "False")"

if [ "$AUTH_STATUS" != "True" ]; then
    warn "GUI ещё не показывает authenticated=true."
    warn "Harness установим, но он не заработает до успешного логина."
    warn "Если что — залогинься позже и перезапусти: systemctl --user restart deepseek-harness.service"
else
    ok "Токен Deepseek получен, GUI видит авторизацию"
fi

# ============================================================
# 10. DeepSeek Harness
# ============================================================
HARNESS_AVAILABLE=false

if command -v dsh >/dev/null 2>&1; then
    HARNESS_AVAILABLE=true
    ok "Harness (dsh) уже установлен"
elif command -v npm >/dev/null 2>&1; then
    log "Устанавливаю @deepseek-ai/dsh глобально..."
    if npm install -g \
        --allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs \
        @deepseek-ai/dsh@latest 2>&1 | tail -3; then
        HARNESS_AVAILABLE=true
        ok "Harness установлен"
    else
        warn "npm install не удался — Harness будет пропущен"
    fi
else
    warn "npm не найден — Harness не установлен"
    warn "Установи Node.js 24 и выполни: npm install -g @deepseek-ai/dsh"
fi

if [ "$HARNESS_AVAILABLE" = true ]; then
    log "Настраиваю Harness (профиль web)..."

    # Прогреваем профиль web (создаёт ~/.dsh/profiles/web/)
    dsh web --no-open >/dev/null 2>&1 &
    DSH_PID=$!
    sleep 6
    kill $DSH_PID 2>/dev/null || true
    wait $DSH_PID 2>/dev/null || true

    # Backup существующего .env
    TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
    if [ -f "$DSH_DIR/.env" ]; then
        mv "$DSH_DIR/.env" "$DSH_DIR/.env.bak-$TIMESTAMP"
        dim "  → старое .env сохранено как .env.bak-$TIMESTAMP"
    fi

    # ~/.dsh/.env — мастер-ключ нашего API
    cat > "$DSH_DIR/.env" << ENVEOF
# Credential reference для локального провайдера DeepSeek-2API.
# Подхватывается через apiKeyEnv: DEEPSEEK_2API_KEY в cordis.patch.yml.
DEEPSEEK_2API_KEY=$API_KEY
ENVEOF
    chmod 600 "$DSH_DIR/.env"

    # Backup существующего cordis.patch.yml
    PATCH_FILE="$DSH_DIR/profiles/web/cordis.patch.yml"
    if [ -f "$PATCH_FILE" ]; then
        mv "$PATCH_FILE" "$PATCH_FILE.bak-$TIMESTAMP"
        dim "  → старый cordis.patch.yml сохранён"
    fi

    # Патч профиля web: провайдер + дефолтная модель
    cat > "$PATCH_FILE" << YAMLEOF
# Профиль web — патчи поверх дефолтных bundle'ов.
# Top-level YAML array из patch-entries. Каждая запись таргетит
# существующий entry по id и ЗАМЕНЯЕТ его config целиком.

- id: ui-settings-general
  name: "@deepseek-ai/dsh-client-ui-settings-general"
  config:
    welcomeNoticeVersion: 2026-08-13.1

- id: llm-pi-ai
  name: "@deepseek-ai/dsh-llm-pi-ai"
  config:
    providers:
      deepseek-2api:
        displayName: DeepSeek 2API (local)
        api: openai-completions
        baseURL: http://127.0.0.1:8080/v1
        apiKeyEnv: DEEPSEEK_2API_KEY
        compat:
          thinkingFormat: deepseek
        models:
          - id: deepseek-chat
            name: DeepSeek Chat
            contextWindow: 131072
          - id: deepseek-reasoner
            name: DeepSeek Reasoner
            contextWindow: 131072

- id: agent-default-model
  name: "@deepseek-ai/dsh-agent-default-model"
  config:
    provider: deepseek-2api
    model: deepseek-chat
YAMLEOF

    ok "Конфиг Harness записан (~/.dsh/.env + cordis.patch.yml)"

    # ---------- systemd unit для Harness ----------
    log "Устанавливаю systemd-сервис deepseek-harness..."

    DSH_BIN="$(command -v dsh || true)"
    if [ -z "$DSH_BIN" ]; then
        warn "dsh не найден в PATH — unit не создан"
    else
        mkdir -p "$HOME/.config/systemd/user"
        cat > "$HOME/.config/systemd/user/deepseek-harness.service" << UNITEOF
[Unit]
Description=DeepSeek Harness (web UI on 127.0.0.1:3080)
After=network.target deepseek-2api.service
Wants=deepseek-2api.service

[Service]
Type=simple
ExecStart=$DSH_BIN web --no-open
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
UNITEOF
        systemctl --user daemon-reload
        systemctl --user enable --now deepseek-harness.service
        sleep 3
        if systemctl --user is-active --quiet deepseek-harness.service; then
            ok "Harness запущен (см. journalctl для URL с токеном)"
        else
            warn "Harness не стартовал. Проверь: journalctl --user -u deepseek-harness.service -n 50"
        fi
    fi
fi

# ============================================================
# 11. Omarchy-плагин
# ============================================================
if command -v omarchy >/dev/null 2>&1; then
    log "Устанавливаю Omarchy-плагин..."
    PLUGIN_DIR="$HOME/.config/omarchy/plugins/deepseek-2api"
    mkdir -p "$PLUGIN_DIR"
    cp "$INSTALL_DIR/omarchy-plugins/deepseek-2api/"* "$PLUGIN_DIR/"
    chmod +x "$PLUGIN_DIR/status.sh" \
             "$PLUGIN_DIR/open-harness.sh" \
             "$PLUGIN_DIR/notify-expired.sh" 2>/dev/null || true

    omarchy-shell shell rescanPlugins 2>/dev/null || true
    omarchy plugin enable deepseek-2api 2>/dev/null || true
    omarchy-restart-shell 2>/dev/null || true
    ok "Плагин установлен — ищи иконку 󰚩 в баре"
else
    dim "Omarchy не найден — плагин пропущен"
fi

# ============================================================
# Финал
# ============================================================
echo
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                     ГОТОВО!                              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo
echo "  GUI:      http://127.0.0.1:8080"
echo "  API:      http://127.0.0.1:8080/v1"
echo "  Harness:  http://127.0.0.1:3080  (если установлен)"
echo
echo "  Мастер-ключ API:"
echo "    $API_KEY"
echo
echo "  Полезные команды:"
echo "    systemctl --user status deepseek-2api.service"
echo "    systemctl --user status deepseek-harness.service"
echo "    journalctl --user -u deepseek-2api.service -f"
echo "    journalctl --user -u deepseek-harness.service -f"
echo
dim "  Если Harness не видит провайдера — см. docs/TROUBLESHOOTING.md"
echo
