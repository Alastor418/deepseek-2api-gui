"""Playwright-логин в chat.deepseek.com.

Открывает Chromium с persistent context, слушает запросы к API Deepseek
и перехватывает Authorization + Cookie из первого запроса.
"""
import asyncio
from collections.abc import Callable

from playwright.async_api import async_playwright

from app.core.config import DATA_DIR


async def capture_credentials(
    on_log: Callable[[str], None] = print,
    timeout: int = 600,
    headless: bool = False,
    auto_send_prompt: str | None = None,
    try_existing_session: bool = True,
) -> dict:
    """Открывает Chromium, даёт залогиниться в Deepseek,
    перехватывает Authorization и Cookie из первого API-запроса.

    Аргументы:
      headless — если True, окно браузера не показывается (нужен уже
                 сохранённый профиль с активной сессией)
      auto_send_prompt — если задано, автоматически отправит это сообщение
                 в чат, чтобы Deepseek сделал API-запрос и мы перехватили токен
      try_existing_session — сначала попробовать сразу открыть chat.deepseek.com
                 и перейти в чат (при сохранённом профиле часто сразу работает)
    """
    result: dict = {"authorization": None, "cookie": None}
    done = asyncio.Event()

    user_data_dir = DATA_DIR / "browser"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=headless,
                no_viewport=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
            )
        except Exception as e:
            on_log(f"! Не удалось запустить Chromium: {e}")
            raise RuntimeError(f"Cannot launch Chromium: {e}") from e

        def on_request(request):
            if "chat.deepseek.com/api" not in request.url:
                return
            if result["authorization"]:
                return
            headers = request.headers
            auth = headers.get("authorization") or headers.get("Authorization")
            if not auth or not auth.startswith("Bearer "):
                return
            cookie = headers.get("cookie") or headers.get("Cookie") or ""
            result["authorization"] = auth.strip()
            result["cookie"] = cookie.strip()
            on_log("OK Перехвачены Authorization и Cookie")
            done.set()

        context.on("request", on_request)

        pages = context.pages
        page = pages[0] if pages else await context.new_page()

        on_log("-> Открываю chat.deepseek.com")
        try:
            await page.goto(
                "https://chat.deepseek.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except Exception as e:
            on_log(f"! Ошибка навигации: {e}")

        # Попытка №1: если профиль уже сохранён — возможно, сразу откроется
        # чат, достаточно отправить сообщение, чтобы получить API-вызов
        if try_existing_session:
            on_log("-> Проверяю, не залогинены ли уже...")
            try:
                await page.wait_for_selector(
                    "textarea, [contenteditable='true']",
                    timeout=5000,
                )
                on_log("-> Сессия активна, отправляю тестовый запрос...")
                textarea = await page.query_selector("textarea")
                if textarea is None:
                    textarea = await page.query_selector(
                        "[contenteditable='true']"
                    )
                if textarea is not None:
                    await textarea.click()
                    await textarea.fill(auto_send_prompt or "hi")
                    await asyncio.sleep(0.3)
                    await textarea.press("Enter")
                    try:
                        await asyncio.wait_for(done.wait(), timeout=15)
                    except TimeoutError:
                        on_log("! Не удалось перехватить токен автоматически")
            except Exception:
                pass

        if not result["authorization"]:
            if headless:
                on_log("! Headless-вход не удался (нужен ручной логин)")
                await context.close()
                raise TimeoutError(
                    "Headless login failed: token not intercepted"
                ) from None

            on_log(
                "-> Войдите в аккаунт и ОТПРАВЬТЕ любое сообщение в чате"
            )
            try:
                await asyncio.wait_for(done.wait(), timeout=timeout)
            except TimeoutError as err:
                await context.close()
                raise TimeoutError("Время ожидания входа истекло") from err
        await asyncio.sleep(0.4)
        await context.close()

    return result
