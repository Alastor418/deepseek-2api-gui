"""Тесты AccountPool — CRUD, LRU, mark_error (критический фикс #1)."""
import time

from app.core.accounts import AccountPool


async def test_add_and_get(tmp_data_dir):
    pool = AccountPool()
    await pool.load()
    acc = await pool.add("Bearer token1", "cookie1", "label1")
    assert await pool.get(acc.id) is not None
    assert (await pool.get(acc.id)).label == "label1"
    assert (await pool.get(acc.id)).status == "active"
    assert await pool.count_active() == 1


async def test_add_same_token_reactivates(tmp_data_dir):
    pool = AccountPool()
    await pool.load()
    a1 = await pool.add("Bearer same", "c1", "first")
    await pool.mark_error(a1.id, "boom", "expired")
    assert (await pool.get(a1.id)).status == "expired"

    a2 = await pool.add("Bearer same", "c2", "second")
    assert a2.id == a1.id
    assert (await pool.get(a1.id)).status == "active"
    assert (await pool.get(a1.id)).cookie == "c2"


async def test_mark_error_immediately_deactivates(tmp_data_dir):
    """Критический фикс: mark_error СРАЗУ ставит статус expired."""
    pool = AccountPool()
    await pool.load()
    acc = await pool.add("Bearer t", "c", "x")
    await pool.mark_error(acc.id, "INVALID_TOKEN", "expired")

    assert (await pool.get(acc.id)).status == "expired"
    assert (await pool.get(acc.id)).error_count == 1
    assert await pool.count_active() == 0

    # И next_active больше не берёт мёртвый аккаунт
    assert await pool.next_active() is None


async def test_mark_error_banned(tmp_data_dir):
    pool = AccountPool()
    await pool.load()
    acc = await pool.add("Bearer t", "c", "x")
    await pool.mark_error(acc.id, "banned", "banned")
    assert (await pool.get(acc.id)).status == "banned"


async def test_reactivate(tmp_data_dir):
    pool = AccountPool()
    await pool.load()
    acc = await pool.add("Bearer t", "c", "x")
    await pool.mark_error(acc.id, "err", "expired")
    await pool.reactivate(acc.id)

    a = await pool.get(acc.id)
    assert a.status == "active"
    assert a.error_count == 0
    assert a.last_error == ""


async def test_next_active_lru(tmp_data_dir):
    pool = AccountPool()
    await pool.load()
    a1 = await pool.add("Bearer A", "", "a")
    time.sleep(0.01)
    a2 = await pool.add("Bearer B", "", "b")
    time.sleep(0.01)
    a3 = await pool.add("Bearer C", "", "c")

    # Все last_used_at == 0, значит порядок — по created_at
    assert (await pool.next_active()).id == a1.id

    # Помечаем a1 использованным — теперь самый старый a2
    await pool.mark_used(a1.id)
    assert (await pool.next_active()).id == a2.id

    await pool.mark_used(a2.id)
    assert (await pool.next_active()).id == a3.id


async def test_remove(tmp_data_dir):
    pool = AccountPool()
    await pool.load()
    acc = await pool.add("Bearer t", "c", "x")
    assert await pool.remove(acc.id) is True
    assert await pool.get(acc.id) is None
    assert await pool.remove(acc.id) is False


async def test_update_label(tmp_data_dir):
    pool = AccountPool()
    await pool.load()
    acc = await pool.add("Bearer t", "c", "x")
    assert await pool.update_label(acc.id, "new") is True
    assert (await pool.get(acc.id)).label == "new"
    assert await pool.update_label("missing", "y") is False


async def test_persistence_reload(tmp_data_dir):
    """Пул должен переживать перезагрузку из файлов."""
    pool1 = AccountPool()
    await pool1.load()
    acc = await pool1.add("Bearer t", "cookie", "label")
    acc_id = acc.id

    # Новый инстанс читает с диска
    pool2 = AccountPool()
    await pool2.load()
    assert (await pool2.get(acc_id)) is not None
    assert (await pool2.get(acc_id)).label == "label"
    assert (await pool2.count_active()) == 1


async def test_accounts_file_chmod_600(tmp_data_dir):
    pool = AccountPool()
    await pool.load()
    acc = await pool.add("Bearer t", "c", "x")
    path = tmp_data_dir / "accounts" / f"{acc.id}.json"
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


async def test_add_creates_no_tmp_leftovers(tmp_data_dir):
    pool = AccountPool()
    await pool.load()
    await pool.add("Bearer t", "c", "x")
    leftovers = list((tmp_data_dir / "accounts").glob("*.tmp"))
    assert leftovers == []
