import asyncio
import contextlib
import json
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from loguru import logger

from app.auth.capture import capture_credentials
from app.core.accounts import pool
from app.core.config import settings, state
from app.core.logging import LOG_FILE, broadcaster, setup_logging
from app.core.storage import (
    Credentials,
    clear_credentials,
    get_or_create_api_key,
    load_credentials,
    save_credentials,
)
from app.providers.deepseek import DeepseekProvider, _is_dead_session
from app.schemas import AccountCreate, AccountLabelUpdate, ChatCompletionRequest

STATIC = Path(__file__).parent / "static"

# Разрешённые хосты для /gui/* — только локальные.
# "testclient" — это host, который Starlette TestClient использует
# в тестах; в продакшене он никогда не появится.
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

# Держим ссылки на "одноразовые" tasks — иначе GC их соберёт.
_background_tasks: set[asyncio.Task] = set()


# ============================================================
# Startup: прогрев WASM + автологин
# ============================================================
async def _check_existing_token(provider: DeepseekProvider) -> bool:
    """Быстрая проверка, что текущий аккаунт даёт валидную сессию."""
    acc = provider._pick_account()
    if acc is None:
        return False

    headers = provider._headers_for(acc)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{provider.BASE_URL}/chat_session/create",
                headers=headers,
                json={},
            )
            try:
                parsed = r.json()
            except Exception:
                parsed = None

            if _is_dead_session(r.status_code, r.text, parsed):
                logger.info(f"   [startup] dead session: {r.text[:120]}")
                return False
            if not isinstance(parsed, dict):
                return False
            data = parsed.get("data")
            if not isinstance(data, dict):
                return False
            biz = data.get("biz_data")
            if not isinstance(biz, dict):
                return False
            return bool(biz.get("id"))
    except Exception as e:
        logger.debug(f"Token check failed: {e}")
        return False


async def _warm_up_pow() -> None:
    """JIT-компилирует WASM при старте, чтобы первый запрос был быстрым."""
    try:
        from app.providers.pow_solver import get_pow_solver

        def _do_warmup() -> None:
            solver = get_pow_solver()
            with contextlib.suppress(Exception):
                solver.solve(
                    "17f75b5e0984f15fc0b8def0c77b48ee4b41b1865f5e8217971722f7870ad4cb",
                    "cba9b8a9bf8368b6341c",
                    1785354733914,
                    144000,
                )

        await asyncio.to_thread(_do_warmup)
        logger.info("OK wasmtime warmed up - first PoW will be fast")
    except Exception as e:
        logger.warning(f"! Warm-up failed: {e}")


async def _startup_auto_login(provider: DeepseekProvider) -> None:
    """При старте: если токен протух — headless-логин."""
    await asyncio.sleep(3)

    try:
        if await _check_existing_token(provider):
            logger.info("OK Стартовая проверка: токен валиден")
            return

        logger.info("! Токен невалиден или отсутствует — запускаю headless-автологин")

        creds = await asyncio.wait_for(
            capture_credentials(
                on_log=logger.info,
                headless=True,
                try_existing_session=True,
                auto_send_prompt="hi",
            ),
            timeout=settings.AUTO_RELOGIN_TIMEOUT,
        )

        if not creds.get("authorization"):
            logger.warning(
                "! Headless-автологин не удался — нужен ручной вход через GUI"
            )
            return

        acc = pool.add(
            authorization=creds["authorization"],
            cookie=creds.get("cookie", ""),
            label="auto-startup",
        )
        pool.reactivate(acc.id)
        logger.success(f"OK Автологин при старте успешен: {acc.id}")
    except TimeoutError:
        logger.warning("! Автологин при старте истёк по таймауту — нужен ручной вход")
    except Exception as e:
        logger.error(f"X Автологин при старте: {type(e).__name__}: {e}")


# ============================================================
# Lifespan
# ============================================================
@asynccontextmanager
async def _lifespan(app_instance: FastAPI):
    loop = asyncio.get_running_loop()
    broadcaster.set_loop(loop)

    provider: DeepseekProvider = app_instance.state.provider

    # Держим ссылки на tasks, иначе GC их соберёт.
    background: set[asyncio.Task] = set()
    for coro in (_warm_up_pow(), _startup_auto_login(provider)):
        t = asyncio.create_task(coro)
        background.add(t)
        t.add_done_callback(background.discard)

    try:
        yield
    finally:
        # Просто отменяем — НЕ ждём через gather.
        # В background есть asyncio.to_thread (прогрев WASM), а такой
        # поток невозможно прервать; await на нём висит до самого конца,
        # из-за чего systemd не может корректно остановить процесс.
        for t in background:
            t.cancel()


# ============================================================
# App factory
# ============================================================
def create_gui_app() -> FastAPI:
    setup_logging()

    api_key = settings.API_MASTER_KEY or get_or_create_api_key()
    settings.API_MASTER_KEY = api_key

    app = FastAPI(lifespan=_lifespan, title=settings.APP_NAME)
    app.state.provider = DeepseekProvider()

    # ---------- middleware: /gui/* только с localhost ----------
    @app.middleware("http")
    async def _localhost_only_for_gui(request: Request, call_next):
        if request.url.path.startswith("/gui/"):
            client_host = request.client.host if request.client else None
            if client_host not in _LOCAL_HOSTS:
                return JSONResponse(
                    {"error": "GUI is localhost-only"},
                    status_code=403,
                )
        return await call_next(request)

    # ---------- CORS для браузерных расширений ----------
    # Расширения шлют запросы с origin chrome-extension://* или moz-extension://*
    # (но клиент всё равно с 127.0.0.1, поэтому _localhost_only_for_gui пропускает).
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(chrome|moz)-extension://.*$",
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
        max_age=3600,
    )

    # ---------- static ----------
    @app.get("/", response_class=HTMLResponse)
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/style.css")
    async def style():
        return FileResponse(STATIC / "style.css", media_type="text/css")

    @app.get("/app.js")
    async def js():
        return FileResponse(STATIC / "app.js", media_type="application/javascript")

    # ---------- GUI status ----------
    @app.get("/gui/status")
    async def gui_status():
        creds = load_credentials()
        return {
            "authenticated": creds is not None or pool.count_active() > 0,
            "login_in_progress": state.login_in_progress,
            "api_url": f"http://{settings.GUI_HOST}:{settings.GUI_PORT}/v1",
            "api_key": settings.API_MASTER_KEY,
            "version": settings.APP_VERSION,
            "authorization_preview": (
                creds.authorization[:40] + "..." if creds else None
            ),
            "cookie_preview": (
                creds.cookie[:40] + "..." if creds else None
            ),
            "accounts_total": len(pool.list()),
            "accounts_active": pool.count_active(),
            "models": list(settings.SUPPORTED_MODELS),
            "aliases": settings.MODEL_ALIASES or {},
            "log_file": str(LOG_FILE),
        }

    # ---------- login / logout ----------
    @app.post("/gui/login")
    async def gui_login():
        if state.login_in_progress:
            raise HTTPException(400, "Вход уже выполняется")
        state.login_in_progress = True
        # Держим ссылку — иначе GC может убить task до завершения.
        task = asyncio.create_task(_do_login())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return {"status": "started"}

    @app.post("/gui/logout")
    async def gui_logout():
        clear_credentials()
        logger.info("Legacy credentials.json удалён")
        return {"status": "ok"}

    @app.post("/gui/pool/clear")
    async def gui_pool_clear():
        ids = [a.id for a in pool.list()]
        for acc_id in ids:
            pool.remove(acc_id)
        logger.info(f"Очищен пул аккаунтов: {len(ids)} шт.")
        return {"status": "ok", "removed": len(ids)}

    # ---------- logs ----------
    @app.get("/gui/logs")
    async def gui_logs():
        q = broadcaster.subscribe()

        async def gen():
            try:
                for line in broadcaster.history()[-200:]:
                    yield f"data: {json.dumps(line)}\n\n"
                while True:
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=25)
                        yield f"data: {json.dumps(msg)}\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                broadcaster.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/gui/logs/download")
    async def gui_logs_download():
        if not LOG_FILE.exists():
            raise HTTPException(404, "Лог-файл не найден")
        return FileResponse(
            LOG_FILE,
            media_type="text/plain",
            filename=f"deepseek-2api-{int(time.time())}.log",
        )

    # ---------- accounts ----------
    @app.get("/gui/accounts")
    async def gui_accounts_list():
        items = []
        for a in pool.list():
            items.append(
                {
                    "id": a.id,
                    "label": a.label,
                    "status": a.status,
                    "created_at": a.created_at,
                    "last_used_at": a.last_used_at,
                    "last_error": a.last_error,
                    "error_count": a.error_count,
                    "authorization_preview": a.authorization[:40] + "...",
                }
            )
        return {"accounts": items, "active": pool.count_active()}

    @app.post("/gui/accounts")
    async def gui_accounts_add(payload: AccountCreate):
        auth = payload.authorization.strip()
        if not auth.startswith("Bearer "):
            raise HTTPException(
                400, "authorization должен начинаться с 'Bearer '"
            )
        acc = pool.add(
            authorization=auth,
            cookie=payload.cookie.strip(),
            label=payload.label.strip(),
        )
        logger.info(f"Добавлен аккаунт {acc.id} ({acc.label})")
        return {"status": "ok", "id": acc.id}

    @app.delete("/gui/accounts/{acc_id}")
    async def gui_accounts_delete(acc_id: str):
        if not pool.remove(acc_id):
            raise HTTPException(404, "Аккаунт не найден")
        logger.info(f"Удалён аккаунт {acc_id}")
        return {"status": "ok"}

    @app.post("/gui/accounts/{acc_id}/reactivate")
    async def gui_accounts_reactivate(acc_id: str):
        if not pool.get(acc_id):
            raise HTTPException(404, "Аккаунт не найден")
        pool.reactivate(acc_id)
        logger.info(f"Реактивирован аккаунт {acc_id}")
        return {"status": "ok"}

    @app.post("/gui/accounts/{acc_id}/label")
    async def gui_accounts_label(acc_id: str, payload: AccountLabelUpdate):
        if not pool.update_label(acc_id, payload.label.strip()):
            raise HTTPException(404, "Аккаунт не найден")
        return {"status": "ok"}

    # ---------- OpenAI-compatible API ----------
    async def verify_api_key(authorization: str | None = Header(None)):
        expected = settings.API_MASTER_KEY
        if not expected:
            # Fail-closed: если ключа нет, сервер сломан.
            raise HTTPException(500, "Server misconfigured: API key not set")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Missing Authorization header")
        provided = authorization[7:]
        if not secrets.compare_digest(provided, expected):
            raise HTTPException(403, "Invalid API key")

    @app.post(
        "/v1/chat/completions", dependencies=[Depends(verify_api_key)]
    )
    async def chat_completions(request: Request, body: ChatCompletionRequest):
        provider: DeepseekProvider = request.app.state.provider
        data = body.model_dump()
        return await provider.chat_completion(data, request)

    @app.get("/v1/models", dependencies=[Depends(verify_api_key)])
    async def list_models():
        now = int(time.time())
        models = []
        for name in settings.SUPPORTED_MODELS:
            models.append(
                {
                    "id": name,
                    "object": "model",
                    "created": now,
                    "owned_by": "deepseek",
                }
            )
        for alias in settings.MODEL_ALIASES or {}:
            models.append(
                {
                    "id": alias,
                    "object": "model",
                    "created": now,
                    "owned_by": "deepseek",
                }
            )
        return {"object": "list", "data": models}

    return app


# ============================================================
# Ручной логин из GUI
# ============================================================
async def _do_login() -> None:
    try:
        logger.info("Открываю браузер для входа в Deepseek...")
        creds = await capture_credentials(on_log=logger.info, headless=False)
        if not creds.get("authorization"):
            logger.error("X Не удалось перехватить токен")
            return
        save_credentials(Credentials(**creds))
        acc = pool.add(
            authorization=creds["authorization"],
            cookie=creds.get("cookie", ""),
            label="manual",
        )
        logger.success(
            f"OK Готово! API доступен. Аккаунт {acc.id} добавлен в пул."
        )
    except Exception as e:
        logger.error(f"X Ошибка входа: {e}")
    finally:
        state.login_in_progress = False
