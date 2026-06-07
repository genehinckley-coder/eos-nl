import routes.translate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from routes.translate import router
from sanitizer import TranslationError, DestructiveCommandError
from eos_client import EosUnreachableError
from ollama_client import OllamaError

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)


# ── empty / whitespace input (handled before Ollama call) ────────────────────

def test_empty_input():
    r = _client.post("/api/translate", json={"input": ""})
    data = r.json()
    assert r.status_code == 200
    assert data["ok"] is False
    assert data["error"] == "empty input"
    assert data["source"] == "bridge"
    assert data["sent"] is False


def test_whitespace_only_input():
    r = _client.post("/api/translate", json={"input": "   "})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["error"] == "empty input"
    assert data["source"] == "bridge"
    assert data["sent"] is False


# ── happy path: Ollama → sanitizer → EOS dispatch ────────────────────────────

def test_valid_command_dispatched():
    with patch("routes.translate.ollama_client.translate", new_callable=AsyncMock) as mock_tr, \
         patch("routes.translate.eos_client.send_cmd", new_callable=AsyncMock) as mock_send, \
         patch.object(routes.translate.settings, "eos_host", "127.0.0.1"), \
         patch.object(routes.translate.settings, "model_name", "test-model"):
        mock_tr.return_value = "Chan 1 @ Full Enter"
        r = _client.post("/api/translate", json={"input": "set channel 1 to full"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["sent"] is True            # invariant: ok=True implies sent=True
    assert data["syntax"] == "Chan 1 @ Full Enter"
    assert data["source"] == "test-model"
    mock_send.assert_awaited_once_with("Chan 1 @ Full Enter")


# ── Ollama failure ────────────────────────────────────────────────────────────

def test_ollama_error():
    with patch("routes.translate.ollama_client.translate", new_callable=AsyncMock) as mock_tr, \
         patch("routes.translate.eos_client.send_cmd", new_callable=AsyncMock) as mock_send, \
         patch.object(routes.translate.settings, "model_name", "test-model"):
        mock_tr.side_effect = OllamaError("timeout")
        r = _client.post("/api/translate", json={"input": "set channel 1 to full"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["sent"] is False
    assert data["source"] == "test-model"
    mock_send.assert_not_awaited()


# ── sanitizer raises TranslationError ────────────────────────────────────────

def test_translation_error():
    with patch("routes.translate.ollama_client.translate", new_callable=AsyncMock) as mock_tr, \
         patch("routes.translate.sanitizer.clean",
               side_effect=TranslationError("cannot parse")), \
         patch("routes.translate.eos_client.send_cmd", new_callable=AsyncMock) as mock_send, \
         patch.object(routes.translate.settings, "eos_host", "127.0.0.1"), \
         patch.object(routes.translate.settings, "model_name", "test-model"):
        mock_tr.return_value = "some model output"
        r = _client.post("/api/translate", json={"input": "something unrecognised"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["sent"] is False
    assert data["syntax"] is None
    assert data["source"] == "test-model"
    mock_send.assert_not_awaited()


# ── sanitizer raises DestructiveCommandError ──────────────────────────────────

def test_destructive_blocked():
    with patch("routes.translate.ollama_client.translate", new_callable=AsyncMock) as mock_tr, \
         patch("routes.translate.sanitizer.clean",
               side_effect=DestructiveCommandError("blocked", syntax="Record Cue 5 Enter")), \
         patch("routes.translate.eos_client.send_cmd", new_callable=AsyncMock) as mock_send, \
         patch.object(routes.translate.settings, "eos_host", "127.0.0.1"), \
         patch.object(routes.translate.settings, "model_name", "test-model"):
        mock_tr.return_value = "Record Cue 5 Enter"
        r = _client.post("/api/translate", json={"input": "record cue 5"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["syntax"] == "Record Cue 5 Enter"   # syntax echoed for UI display
    assert data["sent"] is False
    assert data["source"] == "test-model"
    mock_send.assert_not_awaited()


# ── EOS_HOST not configured ───────────────────────────────────────────────────

def test_eos_host_unconfigured():
    with patch("routes.translate.ollama_client.translate", new_callable=AsyncMock) as mock_tr, \
         patch("routes.translate.eos_client.send_cmd", new_callable=AsyncMock) as mock_send, \
         patch.object(routes.translate.settings, "eos_host", ""), \
         patch.object(routes.translate.settings, "model_name", "test-model"):
        mock_tr.return_value = "Chan 1 @ Full Enter"
        r = _client.post("/api/translate", json={"input": "channel 1 full"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["sent"] is False
    assert "EOS_HOST" in data["error"]
    assert data["source"] == "test-model"
    mock_send.assert_not_awaited()


# ── EOS unreachable at send time ──────────────────────────────────────────────

def test_eos_unreachable():
    with patch("routes.translate.ollama_client.translate", new_callable=AsyncMock) as mock_tr, \
         patch("routes.translate.eos_client.send_cmd", new_callable=AsyncMock) as mock_send, \
         patch.object(routes.translate.settings, "eos_host", "127.0.0.1"), \
         patch.object(routes.translate.settings, "model_name", "test-model"):
        mock_tr.return_value = "Chan 1 @ Full Enter"
        mock_send.side_effect = EosUnreachableError("connection refused")
        r = _client.post("/api/translate", json={"input": "channel 1 full"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["sent"] is False
    assert data["error"] == "EOS unreachable: connection refused"
    assert data["source"] == "test-model"
    mock_send.assert_awaited_once_with("Chan 1 @ Full Enter")
