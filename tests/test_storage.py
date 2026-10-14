"""Тесты app/core/storage.py — атомарные записи, chmod 600."""
import json

from app.core.storage import (
    Credentials,
    clear_credentials,
    get_or_create_api_key,
    load_credentials,
    save_credentials,
)


async def test_save_and_load_credentials(tmp_data_dir):
    creds = Credentials(authorization="Bearer abc", cookie="x=y")
    await save_credentials(creds)

    loaded = await load_credentials()
    assert loaded is not None
    assert loaded.authorization == "Bearer abc"
    assert loaded.cookie == "x=y"


async def test_save_credentials_atomic_no_leftovers(tmp_data_dir):
    await save_credentials(Credentials(authorization="Bearer x", cookie="y"))
    leftovers = list(tmp_data_dir.glob("*.tmp"))
    assert leftovers == []


async def test_save_credentials_chmod_600(tmp_data_dir):
    await save_credentials(Credentials(authorization="Bearer x", cookie="y"))
    mode = (tmp_data_dir / "credentials.json").stat().st_mode & 0o777
    assert mode == 0o600


async def test_load_credentials_missing(tmp_data_dir):
    assert await load_credentials() is None


async def test_load_credentials_corrupted(tmp_data_dir):
    (tmp_data_dir / "credentials.json").write_text("{not json}")
    assert await load_credentials() is None


async def test_clear_credentials(tmp_data_dir):
    await save_credentials(Credentials(authorization="Bearer x", cookie="y"))
    await clear_credentials()
    assert await load_credentials() is None
    # Повторный вызов не падает
    await clear_credentials()


async def test_api_key_created_once(tmp_data_dir):
    k1 = await get_or_create_api_key()
    k2 = await get_or_create_api_key()
    assert k1 == k2
    assert k1.startswith("sk-")
    assert len(k1) > 20


async def test_api_key_chmod_600(tmp_data_dir):
    await get_or_create_api_key()
    mode = (tmp_data_dir / "api_key.txt").stat().st_mode & 0o777
    assert mode == 0o600


async def test_credentials_json_is_valid(tmp_data_dir):
    await save_credentials(Credentials(authorization="Bearer x", cookie="y"))
    data = json.loads(
        (tmp_data_dir / "credentials.json").read_text(encoding="utf-8")
    )
    assert data["authorization"] == "Bearer x"
    assert data["cookie"] == "y"
