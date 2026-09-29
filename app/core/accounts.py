"""Мультиаккаунтный пул Deepseek.

- Аккаунты хранятся в ~/.deepseek-2api/accounts/*.json
- Каждый аккаунт — Authorization + Cookie + метаданные
- Выбор аккаунта: LRU среди status='active' (равномерная нагрузка)
- При ошибке аккаунт помечается как expired/banned и больше не берётся
- Аккаунт можно реактивировать после успешного релогина
- Все публичные методы потокобезопасны (RLock)
- Записи атомарные: tmp → fsync → rename, права 0o600
"""
import contextlib
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

from app.core.config import DATA_DIR

ACCOUNTS_DIR = DATA_DIR / "accounts"
ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)


class Account(BaseModel):
    id: str
    label: str = ""
    authorization: str
    cookie: str = ""
    created_at: float = 0.0
    last_used_at: float = 0.0
    last_error: str = ""
    error_count: int = 0
    status: str = "active"  # active | expired | banned | limited

    def is_usable(self) -> bool:
        return self.status == "active"


class AccountPool:
    """Пул аккаунтов. Все публичные методы потокобезопасны."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._lock = threading.RLock()
        self._load()

    # ---------- persistence ----------
    def _path(self, acc_id: str) -> Path:
        return ACCOUNTS_DIR / f"{acc_id}.json"

    def _load(self) -> None:
        with self._lock:
            self._accounts.clear()
            for f in sorted(ACCOUNTS_DIR.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    acc = Account(**data)
                    self._accounts[acc.id] = acc
                except Exception:
                    continue

    def _save(self, acc: Account) -> None:
        path = self._path(acc.id)
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=parent, prefix=path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(acc.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(Exception):
                os.unlink(tmp_path)
            raise

    # ---------- CRUD ----------
    def list(self) -> list[Account]:
        with self._lock:
            return sorted(self._accounts.values(), key=lambda a: a.created_at)

    def get(self, acc_id: str) -> Account | None:
        with self._lock:
            return self._accounts.get(acc_id)

    def add(self, authorization: str, cookie: str = "", label: str = "") -> Account:
        with self._lock:
            # если токен уже есть — обновляем cookie и реактивируем
            for acc in self._accounts.values():
                if acc.authorization == authorization:
                    acc.cookie = cookie or acc.cookie
                    acc.status = "active"
                    acc.error_count = 0
                    acc.last_error = ""
                    self._save(acc)
                    return acc

            acc = Account(
                id=uuid.uuid4().hex[:12],
                label=label or f"account-{len(self._accounts)+1}",
                authorization=authorization,
                cookie=cookie,
                created_at=time.time(),
                status="active",
            )
            self._accounts[acc.id] = acc
            self._save(acc)
            return acc

    def remove(self, acc_id: str) -> bool:
        with self._lock:
            if acc_id in self._accounts:
                del self._accounts[acc_id]
                with contextlib.suppress(Exception):
                    self._path(acc_id).unlink(missing_ok=True)
                return True
            return False

    def update_label(self, acc_id: str, label: str) -> bool:
        with self._lock:
            acc = self._accounts.get(acc_id)
            if not acc:
                return False
            acc.label = label
            self._save(acc)
            return True

    # ---------- selection ----------
    def next_active(self) -> Account | None:
        with self._lock:
            active = [a for a in self._accounts.values() if a.is_usable()]
            if not active:
                return None
            active.sort(key=lambda a: a.last_used_at or 0)
            return active[0]

    def count_active(self) -> int:
        with self._lock:
            return sum(1 for a in self._accounts.values() if a.is_usable())

    # ---------- state changes ----------
    def mark_used(self, acc_id: str) -> None:
        with self._lock:
            acc = self._accounts.get(acc_id)
            if not acc:
                return
            acc.last_used_at = time.time()
            self._save(acc)

    def mark_error(self, acc_id: str, error: str, status: str = "expired") -> None:
        """Помечает аккаунт проблемным. status ∈ {expired, banned, limited}.

        Явно выставляет статус сразу — это соответствует докстрингу
        и не оставляет мёртвый аккаунт в пуле active.
        """
        with self._lock:
            acc = self._accounts.get(acc_id)
            if not acc:
                return
            acc.last_error = error[:200]
            acc.error_count += 1
            acc.status = status
            self._save(acc)

    def reactivate(self, acc_id: str) -> None:
        with self._lock:
            acc = self._accounts.get(acc_id)
            if not acc:
                return
            acc.status = "active"
            acc.error_count = 0
            acc.last_error = ""
            self._save(acc)


pool = AccountPool()
