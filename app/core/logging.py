"""Настройка loguru: консоль + файл + SSE-стрим в GUI.

LogBroadcaster потокобезопасен: push() можно вызывать из любого треда
(например, из playwright, работающего в своём event loop). Если привязан
главный loop — доставка идёт через call_soon_threadsafe.
"""
import asyncio
import contextlib
import sys
import threading
from collections import deque

from loguru import logger

from app.core.config import LOG_DIR, settings

LOG_FILE = LOG_DIR / "app.log"


class LogBroadcaster:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._history: deque[str] = deque(maxlen=1000)
        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def push(self, msg: str) -> None:
        msg = msg.rstrip()
        if not msg:
            return

        with self._lock:
            self._history.append(msg)
            subscribers = list(self._subscribers)

        for q in subscribers:
            if self._loop and self._loop.is_running():
                # loop уже закрыт — игнорируем
                with contextlib.suppress(RuntimeError):
                    self._loop.call_soon_threadsafe(self._safe_put, q, msg)
            else:
                self._safe_put(q, msg)

    @staticmethod
    def _safe_put(q: asyncio.Queue, msg: str) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(msg)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def history(self) -> list[str]:
        with self._lock:
            return list(self._history)


broadcaster = LogBroadcaster()


def setup_logging() -> None:
    logger.remove()

    # Консоль
    logger.add(
        sys.stdout,
        level="INFO",
        format="{time:HH:mm:ss} | {level: <7} | {message}",
        colorize=True,
    )

    # SSE-канал в GUI
    logger.add(
        lambda m: broadcaster.push(m),
        level="INFO",
        format="{time:HH:mm:ss} | {level: <7} | {message}",
    )

    # Файл
    if settings.LOG_TO_FILE:
        logger.add(
            str(LOG_FILE),
            level="INFO",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | "
                "{name}:{function}:{line} | {message}"
            ),
            rotation=f"{settings.LOG_ROTATION_MB} MB",
            retention=settings.LOG_RETENTION,
            encoding="utf-8",
        )
