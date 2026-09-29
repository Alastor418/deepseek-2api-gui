"""Общие фикстуры для тестов."""
import pytest


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Изолирует ~/.deepseek-2api в tmp_path для каждого теста."""
    data_dir = tmp_path / "ds2api"
    data_dir.mkdir()
    (data_dir / "logs").mkdir()
    accounts_dir = data_dir / "accounts"
    accounts_dir.mkdir()

    monkeypatch.setattr(
        "app.core.storage.CRED_FILE", data_dir / "credentials.json"
    )
    monkeypatch.setattr(
        "app.core.storage.KEY_FILE", data_dir / "api_key.txt"
    )
    monkeypatch.setattr("app.core.accounts.ACCOUNTS_DIR", accounts_dir)

    return data_dir
