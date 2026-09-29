#!/usr/bin/env bash
# Возвращает JSON со статусом Deepseek-2api для QML-виджета.
# При недоступности API — отдаёт последний успешный результат из кэша.
# Кэш помечается полем "cached": true, чтобы QML покрасил виджет оранжевым.

set -u

API_URL="http://127.0.0.1:8080/gui/status"
CACHE_FILE="$HOME/.cache/deepseek-2api-status.json"
mkdir -p "$(dirname "$CACHE_FILE")"

RESPONSE=$(curl -s --max-time 2 "$API_URL" 2>/dev/null || true)

CACHED="false"
AGE="0"

if [ -n "$RESPONSE" ]; then
    # API ответил — обновляем кэш
    echo "$RESPONSE" > "$CACHE_FILE"
    DS_JSON="$RESPONSE"
else
    # API молчит
    if [ ! -f "$CACHE_FILE" ]; then
        # Нет ни API, ни кэша — offline
        cat <<JSON
{"status":"offline","text":"󰚩",
 "tooltip":"🔴 Deepseek-2api: сервис не отвечает\nЗапусти: systemctl --user start deepseek-2api.service",
 "version":"?","accounts":"0/0","models":"—",
 "cached":false,"harness_url":""}
JSON
        exit 0
    fi
    AGE=$(( $(date +%s) - $(stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0) ))
    CACHED="true"
    DS_JSON="$(cat "$CACHE_FILE")"
fi

# URL Harness (свежий — за 3 минуты)
HARNESS_URL=$(journalctl --user -u deepseek-harness.service \
    --since "3 min ago" --no-pager 2>/dev/null \
    | grep -oE "http://127\.0\.0\.1:3080/\?token=[A-Za-z0-9_-]+" \
    | tail -1 || true)

DS_CACHED="$CACHED" \
DS_AGE="$AGE" \
DS_JSON="$DS_JSON" \
DS_HARNESS_URL="$HARNESS_URL" \
python3 << 'PYEOF'
import json
import os
import sys

try:
    d = json.loads(os.environ.get("DS_JSON", "{}"))
except Exception as e:
    print(json.dumps({
        "status": "error",
        "text": "󰚩",
        "tooltip": f"Ошибка парсинга: {e}",
        "version": "?",
        "accounts": "0/0",
        "models": "—",
        "cached": False,
        "harness_url": "",
    }, ensure_ascii=False))
    sys.exit(0)

auth    = bool(d.get("authenticated", False))
active  = int(d.get("accounts_active", 0))
total   = int(d.get("accounts_total", 0))
version = str(d.get("version", "?"))
models  = ", ".join(d.get("models", []) or [])
cached  = os.environ.get("DS_CACHED", "false") == "true"
age     = os.environ.get("DS_AGE", "0")
harness_url = os.environ.get("DS_HARNESS_URL", "")

# cached всегда перебивает auth — виджет оранжевый.
if cached:
    status = "warning"
    prefix = "🟠"
    extra = f"\n⚠ API не отвечает\nПоказан кэш ({age} сек. назад)"
elif auth:
    status = "active"
    prefix = "🟢"
    extra = ""
else:
    status = "warning"
    prefix = "🟡"
    extra = ""

if auth:
    tooltip = (
        f"{prefix} Deepseek-2api v{version}\n"
        f"Статус: работает\n"
        f"Аккаунтов: {active} / {total}\n"
        f"Модели: {models}{extra}\n\n"
        f"ЛКМ: открыть Harness\n"
        f"ПКМ: логи API\n"
        f"СКМ: перезапуск"
    )
else:
    tooltip = (
        f"{prefix} Deepseek-2api v{version}\n"
        f"Статус: не авторизован\n"
        f"Нажми «Войти в Deepseek» в GUI{extra}\n\n"
        f"ЛКМ: Harness (если работает)\n"
        f"ПКМ: логи API\n"
        f"СКМ: перезапуск"
    )

print(json.dumps({
    "status": status,
    "text": "󰚩",
    "tooltip": tooltip,
    "version": version,
    "accounts": f"{active}/{total}",
    "models": models,
    "cached": cached,
    "harness_url": harness_url,
}, ensure_ascii=False))
PYEOF

# Фоновая проверка протухания токена (если скрипт есть)
NOTIFY_SCRIPT="$HOME/.config/omarchy/plugins/deepseek-2api/notify-expired.sh"
if [ -x "$NOTIFY_SCRIPT" ]; then
    "$NOTIFY_SCRIPT" &
fi
