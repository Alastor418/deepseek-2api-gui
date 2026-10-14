"""Хранилище credentials.json и api_key.txt.

Все записи атомарные: tmp → fsync → rename.
Права на файлы — всегда 0o600.
"""
import asyncio
import contextlib
import json
import os
import secrets
import tempfile
from pathlib import Path

from pydantic import BaseModel

from app.core.config import DATA_DIR

CRED_FILE = DATA_DIR / "credentials.json"
KEY_FILE = DATA_DIR / "api_key.txt"


class Credentials(BaseModel):
    authorization: str
    cookie: str


def _atomic_write(path: Path, data: str, mode: int = 0o600) -> None:
    """Атомарная запись: tmp → fsync → rename. Права строго mode."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=parent, prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(Exception):
            os.unlink(tmp_path)
        raise


async def save_credentials(creds: Credentials) -> None:
    await asyncio.to_thread(_atomic_write, CRED_FILE, creds.model_dump_json(indent=2))


async def load_credentials() -> Credentials | None:
    def _load():
        if not CRED_FILE.exists():
            return None
        try:
            data = json.loads(CRED_FILE.read_text(encoding="utf-8"))
            return Credentials(**data)
        except Exception:
            return None
    return await asyncio.to_thread(_load)
    try:
        data = json.loads(CRED_FILE.read_text(encoding="utf-8"))
        return Credentials(**data)
    except Exception:
        return None


async def clear_credentials() -> None:
    def _clear():
        with contextlib.suppress(Exception):
            CRED_FILE.unlink(missing_ok=True)
    await asyncio.to_thread(_clear)


async def get_or_create_api_key() -> str:
    def _get_key():
        if KEY_FILE.exists():
            return KEY_FILE.read_text(encoding="utf-8").strip()
        key = "sk-" + secrets.token_urlsafe(32)
        _atomic_write(KEY_FILE, key)
        return key
    return await asyncio.to_thread(_get_key)
