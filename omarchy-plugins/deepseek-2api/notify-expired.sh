#!/usr/bin/env bash
# Уведомление при протухании токена. Не чаще раза в час.

set -u

NOTIFY_CACHE="$HOME/.cache/deepseek-2api-token-notified"
mkdir -p "$(dirname "$NOTIFY_CACHE")"

if [ -f "$NOTIFY_CACHE" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$NOTIFY_CACHE" 2>/dev/null || echo 0) ))
    if [ "$AGE" -lt 3600 ]; then
        exit 0
    fi
fi

STATUS=$(curl -s --max-time 2 http://127.0.0.1:8080/gui/status 2>/dev/null || true)
if [ -z "$STATUS" ]; then
    exit 0
fi

AUTH=$(echo "$STATUS" | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('authenticated', False))" \
    2>/dev/null || echo "False")
ACTIVE=$(echo "$STATUS" | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('accounts_active', 0))" \
    2>/dev/null || echo "0")

if [ "$AUTH" = "False" ] && [ "$ACTIVE" = "0" ]; then
    notify-send -u critical \
        "DeepSeek: токен протух" \
        "Автологин не сработал. Открой GUI: http://127.0.0.1:8080 и нажми «Войти в Deepseek»." \
        2>/dev/null || true
    touch "$NOTIFY_CACHE"
fi
