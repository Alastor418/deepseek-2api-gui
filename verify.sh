#!/usr/bin/env bash
# ============================================================
# Health check DeepSeek-2API + Harness + Omarchy-плагина
# ============================================================
# Запуск:
#   bash verify.sh
# ============================================================

set -uo pipefail

C_RESET='\033[0m'; C_GREEN='\033[0;32m'; C_YELLOW='\033[1;33m'
C_RED='\033[0;31m'; C_BLUE='\033[0;34m'; C_DIM='\033[2m'

PASS=0
FAIL=0

check() {
    local name="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo -e "  ${C_GREEN}[✓]${C_RESET} $name"
        PASS=$((PASS + 1))
    else
        echo -e "  ${C_RED}[✗]${C_RESET} $name"
        FAIL=$((FAIL + 1))
    fi
}

check_output() {
    local name="$1"
    local expected="$2"
    local actual="$3"
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${C_GREEN}[✓]${C_RESET} $name: $actual"
        PASS=$((PASS + 1))
    else
        echo -e "  ${C_RED}[✗]${C_RESET} $name: $actual (ожидалось: $expected)"
        FAIL=$((FAIL + 1))
    fi
}

echo
echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Проверка здоровья DeepSeek-2API                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo

# --- 1. Файлы ---
echo -e "${C_BLUE}Файлы и директории${C_RESET}"
check "~/deepseek-2api-gui существует" test -d "$HOME/deepseek-2api-gui"
check "~/deepseek-2api-gui/.venv" test -d "$HOME/deepseek-2api-gui/.venv"
check "~/.deepseek-2api/api_key.txt" test -f "$HOME/.deepseek-2api/api_key.txt"

if [ -f "$HOME/.deepseek-2api/api_key.txt" ]; then
    KEY_MODE=$(stat -c %a "$HOME/.deepseek-2api/api_key.txt" 2>/dev/null || echo "?")
    check_output "chmod api_key.txt" "600" "$KEY_MODE"
fi

# --- 2. systemd ---
echo
echo -e "${C_BLUE}systemd сервисы${C_RESET}"
API_ACTIVE=$(systemctl --user is-active deepseek-2api.service 2>/dev/null || echo "inactive")
check_output "deepseek-2api active" "active" "$API_ACTIVE"
API_ENABLED=$(systemctl --user is-enabled deepseek-2api.service 2>/dev/null || echo "disabled")
check_output "deepseek-2api enabled" "enabled" "$API_ENABLED"

HARNESS_UNIT=$(systemctl --user list-unit-files deepseek-harness.service 2>/dev/null | grep -c deepseek-harness || echo 0)
if [ "$HARNESS_UNIT" -gt 0 ]; then
    H_ACTIVE=$(systemctl --user is-active deepseek-harness.service 2>/dev/null || echo "inactive")
    check_output "deepseek-harness active" "active" "$H_ACTIVE"
else
    echo -e "  ${C_YELLOW}[—]${C_RESET} deepseek-harness не установлен (пропущено)"
fi

# --- 3. API эндпоинты ---
echo
echo -e "${C_BLUE}API эндпоинты${C_RESET}"

STATUS=$(curl -s --max-time 5 http://127.0.0.1:8080/gui/status 2>/dev/null)
if [ -n "$STATUS" ]; then
    echo -e "  ${C_GREEN}[✓]${C_RESET} /gui/status отвечает"
    PASS=$((PASS + 1))

    AUTH=$(echo "$STATUS" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("authenticated", False))' 2>/dev/null)
    check_output "authenticated" "True" "$AUTH"

    VERSION=$(echo "$STATUS" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("version", "?"))' 2>/dev/null)
    echo -e "  ${C_DIM}версия: $VERSION${C_RESET}"
else
    echo -e "  ${C_RED}[✗]${C_RESET} /gui/status не отвечает"
    FAIL=$((FAIL + 1))
fi

# HTTP-коды
CODE_NOAUTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8080/v1/models 2>/dev/null)
check_output "/v1/models без ключа → 401" "401" "$CODE_NOAUTH"

CODE_BADAUTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
    -H "Authorization: Bearer wrong" \
    http://127.0.0.1:8080/v1/models 2>/dev/null)
check_output "/v1/models с плохим ключом → 403" "403" "$CODE_BADAUTH"

if [ -f "$HOME/.deepseek-2api/api_key.txt" ]; then
    API_KEY=$(cat "$HOME/.deepseek-2api/api_key.txt")
    CODE_OK=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        -H "Authorization: Bearer $API_KEY" \
        http://127.0.0.1:8080/v1/models 2>/dev/null)
    check_output "/v1/models с правильным ключом → 200" "200" "$CODE_OK"
fi

# --- 4. Аккаунты ---
echo
echo -e "${C_BLUE}Аккаунты${C_RESET}"
if [ -n "$STATUS" ]; then
    ACCOUNTS=$(echo "$STATUS" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("accounts_active", 0))' 2>/dev/null)
    if [ "$ACCOUNTS" -gt 0 ]; then
        echo -e "  ${C_GREEN}[✓]${C_RESET} активных аккаунтов: $ACCOUNTS"
        PASS=$((PASS + 1))
    else
        echo -e "  ${C_YELLOW}[!]${C_RESET} аккаунтов 0 — нужно залогиниться"
        echo -e "      ${C_DIM}Открой http://127.0.0.1:8080 или расширение браузера${C_RESET}"
    fi
fi

# --- 5. Harness ---
if [ "$HARNESS_UNIT" -gt 0 ]; then
    echo
    echo -e "${C_BLUE}Harness${C_RESET}"
    HARNESS_URL=$(journalctl --user -u deepseek-harness.service --no-pager 2>/dev/null \
        | grep -oE "http://127\.0\.0\.1:3080/\?token=[A-Za-z0-9_-]+" | tail -1)
    if [ -n "$HARNESS_URL" ]; then
        echo -e "  ${C_GREEN}[✓]${C_RESET} URL найден: ${HARNESS_URL:0:60}..."
        PASS=$((PASS + 1))
    else
        echo -e "  ${C_YELLOW}[!]${C_RESET} URL не найден в journald"
    fi

    check "~/.dsh/.env существует" test -f "$HOME/.dsh/.env"
    check "~/.dsh/profiles/web/cordis.patch.yml" test -f "$HOME/.dsh/profiles/web/cordis.patch.yml"
fi

# --- 6. Omarchy-плагин ---
echo
echo -e "${C_BLUE}Omarchy-плагин${C_RESET}"
PLUGIN_DIR="$HOME/.config/omarchy/plugins/deepseek-2api"
if [ -d "$PLUGIN_DIR" ]; then
    check "плагин установлен" test -d "$PLUGIN_DIR"
    check "manifest.json" test -f "$PLUGIN_DIR/manifest.json"
    check "BarWidget.qml" test -f "$PLUGIN_DIR/BarWidget.qml"
    check "status.sh executable" test -x "$PLUGIN_DIR/status.sh"
else
    echo -e "  ${C_YELLOW}[—]${C_RESET} плагин не установлен"
fi

# --- 7. Расширения браузера ---
echo
echo -e "${C_BLUE}Браузерные расширения${C_RESET}"
check "chrome extension" test -f "$HOME/deepseek-2api-gui/browser-extensions/chrome/manifest.json"
check "firefox extension" test -f "$HOME/deepseek-2api-gui/browser-extensions/firefox/manifest.json"

# --- Итог ---
echo
echo "╔════════════════════════════════════════════════════════════╗"
printf "║  Результат: %3d passed, %3d failed                          ║\n" "$PASS" "$FAIL"
echo "╚════════════════════════════════════════════════════════════╝"

if [ "$FAIL" -eq 0 ]; then
    echo -e "${C_GREEN}  Всё работает. Открывай: http://127.0.0.1:8080${C_RESET}"
    exit 0
else
    echo -e "${C_YELLOW}  Есть проблемы. Смотри docs/TROUBLESHOOTING.md${C_RESET}"
    exit 1
fi
