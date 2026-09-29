"""Deepseek-2api GUI — точка входа.

Запускает uvicorn, открывает браузер с GUI.
"""
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn


def _die(msg: str, hint: str = "") -> None:
    print(f"X {msg}", file=sys.stderr)
    if hint:
        print(f"  {hint}", file=sys.stderr)
    sys.exit(1)


def ensure_playwright_browsers() -> None:
    """Проверяет, установлен ли Chromium для Playwright. Если нет — ставит."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _die(
            "Playwright не установлен.",
            "Активируй venv и выполни: pip install -r requirements.txt",
        )

    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if not path or not Path(path).exists():
                raise RuntimeError("chromium not found")
    except Exception:
        print("-> Устанавливаю браузер Chromium для Playwright...")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )


def ensure_wasm() -> None:
    """Проверяет наличие WASM-модуля для PoW."""
    from app.providers.pow_solver import WASM_PATH

    if not WASM_PATH.exists():
        _die(
            f"WASM-модуль не найден: {WASM_PATH}",
            "Он нужен для PoW-челленджа Deepseek. Переустанови проект.",
        )


def open_browser_later(url: str, delay: float = 1.4) -> None:
    time.sleep(delay)
    webbrowser.open(url)


def main() -> None:
    from app.core.config import LOG_DIR, settings
    from app.gui.server import create_gui_app

    print()
    print(f"  Deepseek-2api GUI v{settings.APP_VERSION}")
    print("  Автологин · Авторелогин · Мультиаккаунт")
    print("  deepseek-chat · deepseek-reasoner")
    print()
    print(f"  Web:      http://{settings.GUI_HOST}:{settings.GUI_PORT}")
    print(f"  API:      http://{settings.GUI_HOST}:{settings.GUI_PORT}/v1")
    print(f"  Logs:     {LOG_DIR / 'app.log'}")
    print(f"  Accounts: {Path.home() / '.deepseek-2api' / 'accounts'}")
    print()
    print("  Ctrl+C для остановки")
    print()

    ensure_wasm()
    ensure_playwright_browsers()

    url = f"http://{settings.GUI_HOST}:{settings.GUI_PORT}"
    threading.Thread(
        target=open_browser_later, args=(url,), daemon=True
    ).start()

    app = create_gui_app()
    uvicorn.run(
        app,
        host=settings.GUI_HOST,
        port=settings.GUI_PORT,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
