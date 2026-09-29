"""Тесты AccountPool — CRUD, LRU, mark_error (критический фикс #1)."""
import time

from app.core.accounts import AccountPool


def test_add_and_get(tmp_data_dir):
    pool = AccountPool()
    acc = pool.add("Bearer token1", "cookie1", "label1")
    assert pool.get(acc.id) is not None
    assert pool.get(acc.id).label == "label1"
    assert pool.get(acc.id).status == "active"
    assert pool.count_active() == 1


def test_add_same_token_reactivates(tmp_data_dir):
    pool = AccountPool()
    a1 = pool.add("Bearer same", "c1", "first")
    pool.mark_error(a1.id, "boom", "expired")
    assert pool.get(a1.id).status == "expired"

    a2 = pool.add("Bearer same", "c2", "second")
    assert a2.id == a1.id
    assert pool.get(a1.id).status == "active"
    assert pool.get(a1.id).cookie == "c2"


def test_mark_error_immediately_deactivates(tmp_data_dir):
    """Критический фикс: mark_error СРАЗУ ставит статус expired."""
    pool = AccountPool()
    acc = pool.add("Bearer t", "c", "x")
    pool.mark_error(acc.id, "INVALID_TOKEN", "expired")

    assert pool.get(acc.id).status == "expired"
    assert pool.get(acc.id).error_count == 1
    assert pool.count_active() == 0

    # И next_active больше не берёт мёртвый аккаунт
    assert pool.next_active() is None


def test_mark_error_banned(tmp_data_dir):
    pool = AccountPool()
    acc = pool.add("Bearer t", "c", "x")
    pool.mark_error(acc.id, "banned", "banned")
    assert pool.get(acc.id).status == "banned"


def test_reactivate(tmp_data_dir):
    pool = AccountPool()
    acc = pool.add("Bearer t", "c", "x")
    pool.mark_error(acc.id, "err", "expired")
    pool.reactivate(acc.id)

    a = pool.get(acc.id)
    assert a.status == "active"
    assert a.error_count == 0
    assert a.last_error == ""


def test_next_active_lru(tmp_data_dir):
    pool = AccountPool()
    a1 = pool.add("Bearer A", "", "a")
    time.sleep(0.01)
    a2 = pool.add("Bearer B", "", "b")
    time.sleep(0.01)
    a3 = pool.add("Bearer C", "", "c")

    # Все last_used_at == 0, значит порядок — по created_at
    assert pool.next_active().id == a1.id

    # Помечаем a1 использованным — теперь самый старый a2
    pool.mark_used(a1.id)
    assert pool.next_active().id == a2.id

    pool.mark_used(a2.id)
    assert pool.next_active().id == a3.id


def test_remove(tmp_data_dir):
    pool = AccountPool()
    acc = pool.add("Bearer t", "c", "x")
    assert pool.remove(acc.id) is True
    assert pool.get(acc.id) is None
    assert pool.remove(acc.id) is False


def test_update_label(tmp_data_dir):
    pool = AccountPool()
    acc = pool.add("Bearer t", "c", "x")
    assert pool.update_label(acc.id, "new") is True
    assert pool.get(acc.id).label == "new"
    assert pool.update_label("missing", "y") is False


def test_persistence_reload(tmp_data_dir):
    """Пул должен переживать перезагрузку из файлов."""
    pool1 = AccountPool()
    acc = pool1.add("Bearer t", "cookie", "label")
    acc_id = acc.id

    # Новый инстанс читает с диска
    pool2 = AccountPool()
    assert pool2.get(acc_id) is not None
    assert pool2.get(acc_id).label == "label"
    assert pool2.count_active() == 1


def test_accounts_file_chmod_600(tmp_data_dir):
    pool = AccountPool()
    acc = pool.add("Bearer t", "c", "x")
    path = tmp_data_dir / "accounts" / f"{acc.id}.json"
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_add_creates_no_tmp_leftovers(tmp_data_dir):
    pool = AccountPool()
    pool.add("Bearer t", "c", "x")
    leftovers = list((tmp_data_dir / "accounts").glob("*.tmp"))
    assert leftovers == []
