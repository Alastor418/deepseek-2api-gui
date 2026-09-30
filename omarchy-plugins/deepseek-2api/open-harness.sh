#!/usr/bin/env bash
# Открывает DeepSeek Harness (с автостартом и получением свежего URL).

set -u

LOG="$HOME/.cache/open-harness.log"
mkdir -p "$(dirname "$LOG")"
echo "--- $(date) ---" >> "$LOG"

URL_RE='http://127\.0\.0\.1:3080/\?token=[A-Za-z0-9_-]+'

# Проверяем, запущен ли сервис
if ! systemctl --user is-active --quiet deepseek-harness.service; then
    echo "Harness not active, starting..." >> "$LOG"
    notify-send "DeepSeek Harness" "Запускаю сервис..." 2>/dev/null || true
    systemctl --user start deepseek-harness.service || {
        notify-send "DeepSeek Harness" \
            "Не удалось запустить сервис. Проверь: systemctl --user status deepseek-harness.service" \
            2>/dev/null || true
        exit 1
    }
fi

# Polling: ждём URL до 30 секунд
URL=""
for i in $(seq 1 30); do
    URL=$(journalctl --user -u deepseek-harness.service \
        | grep -oE "$URL_RE" | tail -1 || true)
    if [ -n "$URL" ]; then
        break
    fi
    sleep 1
done

if [ -z "$URL" ]; then
    echo "URL not found after 30s" >> "$LOG"
    notify-send "DeepSeek Harness" \
        "URL не найден за 30с. Проверь: journalctl --user -u deepseek-harness.service -n 50" \
        2>/dev/null || true
    exit 1
fi

echo "Opening: $URL" >> "$LOG"
xdg-open "$URL"
