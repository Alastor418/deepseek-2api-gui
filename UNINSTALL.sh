#!/usr/bin/env bash
# ============================================================
# Полное удаление DeepSeek-2API + Harness + Omarchy-плагина
# ============================================================
# Что удаляется:
#   • systemd-сервисы (остановка + disable + удаление unit-файлов)
#   • ~/deepseek-2api-gui (проект)
#   • ~/.deepseek-2api (аккаунты, ключ, логи, профиль Chromium)
#   • ~/.dsh (конфиг Harness + токены + сессии)
#   • ~/.config/omarchy/plugins/deepseek-2api (плагин бара)
#   • ~/.cache/ms-playwright (Chromium от Playwright, ОПЦИОНАЛЬНО)
#   • @deepseek-ai/dsh (npm-пакет, ОПЦИОНАЛЬНО)
#
# Запуск:
#   bash UNINSTALL.sh
# ============================================================

set -uo pipefail

C_RESET='\033[0m'; C_GREEN='\033[0;32m'; C_YELLOW='\033[1;33m'
C_RED='\033[0;31m'; C_BLUE='\033[0;34m'; C_DIM='\033[2m'

log()  { echo -e "${C_BLUE}[*]${C_RESET} $1"; }
ok()   { echo -e "${C_GREEN}[✓]${C_RESET} $1"; }
warn() { echo -e "${C_YELLOW}[!]${C_RESET} $1"; }
dim()  { echo -e "${C_DIM}  $1${C_RESET}"; }

echo
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Удаление DeepSeek-2API + Harness                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo

read -rp "  Точно удаляем всё? [y/N] " ans
if [[ ! "$ans" =~ ^[Yy]$ ]]; then
    echo "  Отменено."
    exit 0
fi

echo

# 1. Останавливаем systemd-сервисы
log "Останавливаю systemd-сервисы..."
systemctl --user stop deepseek-harness.service 2>/dev/null && \
    dim "  → harness остановлен" || true
systemctl --user stop deepseek-2api.service 2>/dev/null && \
    dim "  → api остановлен" || true
systemctl --user disable deepseek-harness.service 2>/dev/null || true
systemctl --user disable deepseek-2api.service 2>/dev/null || true

# 2. Удаляем unit-файлы
log "Удаляю unit-файлы..."
rm -f "$HOME/.config/systemd/user/deepseek-harness.service"
rm -f "$HOME/.config/systemd/user/deepseek-2api.service"
systemctl --user daemon-reload 2>/dev/null || true
ok "Unit-файлы удалены"

# 3. Удаляем проект
if [ -d "$HOME/deepseek-2api-gui" ]; then
    log "Удаляю ~/deepseek-2api-gui..."
    rm -rf "$HOME/deepseek-2api-gui"
    ok "Проект удалён"
fi

# 4. Удаляем данные
if [ -d "$HOME/.deepseek-2api" ]; then
    log "Удаляю ~/.deepseek-2api..."
    rm -rf "$HOME/.deepseek-2api"
    ok "Данные удалены"
fi

# 5. Удаляем Harness
if [ -d "$HOME/.dsh" ]; then
    log "Удаляю ~/.dsh..."
    rm -rf "$HOME/.dsh"
    ok "Harness-конфиг удалён"
fi

# 6. Удаляем Omarchy-плагин
if [ -d "$HOME/.config/omarchy/plugins/deepseek-2api" ]; then
    log "Удаляю Omarchy-плагин..."
    rm -rf "$HOME/.config/omarchy/plugins/deepseek-2api"
    command -v omarchy-restart-shell >/dev/null 2>&1 && \
        omarchy-restart-shell 2>/dev/null || true
    ok "Плагин удалён"
fi

# 7. Опционально: Playwright browsers
echo
read -rp "  Удалить Chromium от Playwright (~500 МБ)? [y/N] " del_pw
if [[ "$del_pw" =~ ^[Yy]$ ]]; then
    rm -rf "$HOME/.cache/ms-playwright"
    ok "Chromium удалён"
fi

# 8. Опционально: npm-пакет dsh
echo
read -rp "  Удалить npm-пакет @deepseek-ai/dsh? [y/N] " del_dsh
if [[ "$del_dsh" =~ ^[Yy]$ ]]; then
    if command -v npm >/dev/null 2>&1; then
        npm uninstall -g @deepseek-ai/dsh 2>/dev/null && \
            ok "dsh удалён" || warn "npm uninstall не удался"
        hash -r 2>/dev/null || true
    else
        warn "npm не найден"
    fi
fi

echo
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    УДАЛЕНО                                 ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo
