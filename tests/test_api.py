"""Интеграционные тесты FastAPI-роутов.

Не используем lifespan (TestClient без контекстного менеджера), поэтому
_warm_up_pow и _startup_auto_login не запускаются — они не нужны в тестах.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.accounts import AccountPool


class _FakeProvider:
    """Заглушка DeepseekProvider для API-тестов."""

    BASE_URL = "http://fake"

    async def chat_completion(self, data, request):
        return {"ok": True, "model": data["model"]}

    def _pick_account(self):
        return None

    def _headers_for(self, acc):
        return {}


@pytest.fixture
def app_client(monkeypatch, tmp_data_dir):
    from app.core.config import settings

    monkeypatch.setattr(settings, "API_MASTER_KEY", "sk-test")

    import app.gui.server as srv

    monkeypatch.setattr(srv, "DeepseekProvider", _FakeProvider)
    monkeypatch.setattr(srv, "pool", AccountPool())

    app = srv.create_gui_app()
    return TestClient(app)


# ---------- /v1/models ----------
def test_models_requires_auth(app_client):
    r = app_client.get("/v1/models")
    assert r.status_code == 401


def test_models_wrong_key(app_client):
    r = app_client.get(
        "/v1/models", headers={"Authorization": "Bearer nope"}
    )
    assert r.status_code == 403


def test_models_no_bearer_prefix(app_client):
    r = app_client.get("/v1/models", headers={"Authorization": "sk-test"})
    assert r.status_code == 401


def test_models_ok(app_client):
    r = app_client.get(
        "/v1/models", headers={"Authorization": "Bearer sk-test"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "list"
    ids = [m["id"] for m in body["data"]]
    assert "deepseek-chat" in ids
    assert "deepseek-reasoner" in ids


# ---------- /v1/chat/completions ----------
def test_chat_missing_model(app_client):
    r = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-test"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 422


def test_chat_empty_messages(app_client):
    r = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-test"},
        json={"model": "deepseek-chat", "messages": []},
    )
    assert r.status_code == 422


def test_chat_bad_role(app_client):
    r = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-test"},
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "boss", "content": "hi"}],
        },
    )
    assert r.status_code == 422


def test_chat_happy_path(app_client):
    r = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-test"},
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["model"] == "deepseek-chat"


def test_chat_wrong_key(app_client):
    r = app_client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer nope"},
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 403


# ---------- /gui/status ----------
def test_gui_status_localhost(app_client):
    # TestClient host = "testclient", он в _LOCAL_HOSTS
    r = app_client.get("/gui/status")
    assert r.status_code == 200
    body = r.json()
    assert "api_key" in body
    assert body["api_key"] == "sk-test"
    assert body["version"].startswith("3.")
