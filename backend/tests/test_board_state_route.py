import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from eos_client import BoardState
from routes.board_state import router


# Minimal FastAPI app containing only the board-state route
_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)


def _patched_get(state: BoardState):
    """Make a GET /api/board-state with eos_client.board_state replaced by state."""
    mock_eos = MagicMock()
    mock_eos.board_state = state
    with patch("routes.board_state.eos_client", mock_eos):
        r = _client.get("/api/board-state")
    return r


# ── offline (default BoardState) ─────────────────────────────────────────────

def test_offline_returns_200():
    r = _patched_get(BoardState())
    assert r.status_code == 200


def test_offline_connected_false():
    data = _patched_get(BoardState()).json()
    assert data["connected"] is False


def test_offline_mode_unknown():
    data = _patched_get(BoardState()).json()
    assert data["mode"] == "unknown"


def test_offline_fields_null():
    data = _patched_get(BoardState()).json()
    assert data["show_name"]    is None
    assert data["active_cue"]   is None
    assert data["next_cue"]     is None
    assert data["last_updated"] is None


# ── online (populated BoardState) ────────────────────────────────────────────

_ONLINE_STATE = BoardState(
    show_name="Hamlet Act II",
    active_cue="5",
    active_cue_list="1",
    active_cue_label="Intro",
    next_cue="6",
    next_cue_list="1",
    mode="Live",
    connected=True,
    last_updated=1700000000.0,
)


def test_online_returns_200():
    r = _patched_get(_ONLINE_STATE)
    assert r.status_code == 200


def test_online_connected_true():
    data = _patched_get(_ONLINE_STATE).json()
    assert data["connected"] is True


def test_online_show_name():
    data = _patched_get(_ONLINE_STATE).json()
    assert data["show_name"] == "Hamlet Act II"


def test_online_active_cue_fields():
    data = _patched_get(_ONLINE_STATE).json()
    assert data["active_cue"]       == "5"
    assert data["active_cue_list"]  == "1"
    assert data["active_cue_label"] == "Intro"


def test_online_next_cue():
    data = _patched_get(_ONLINE_STATE).json()
    assert data["next_cue"]      == "6"
    assert data["next_cue_list"] == "1"


def test_online_mode():
    data = _patched_get(_ONLINE_STATE).json()
    assert data["mode"] == "Live"


def test_online_last_updated():
    data = _patched_get(_ONLINE_STATE).json()
    assert abs(data["last_updated"] - 1700000000.0) < 0.001
