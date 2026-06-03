import struct
import pytest
from unittest.mock import MagicMock
from eos_client import EosClient, BoardState


# ── _parse_cue_text ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    # active cue: list/cue, multi-word label, time, percent
    ("1/5 Intro Scene 3.00 75%",  ("1", "5",    "Intro Scene")),
    # pending cue: no percent
    ("1/6 Verse 5.00",            ("1", "6",    "Verse")),
    # decimal cue number
    ("1/10.5 Finale 2.50 100%",   ("1", "10.5", "Finale")),
    # unlabeled cue (no label tokens between cue# and time)
    ("1/3 3.00 50%",              ("1", "3",    None)),
    # malformed — no slash in first token
    ("bad-input",                 (None, None,  None)),
    # empty string
    ("",                          (None, None,  None)),
])
def test_parse_cue_text(text, expected):
    result = EosClient._parse_cue_text(text)
    assert result == expected


# ── _build_raw_packet ────────────────────────────────────────────────────────

def test_build_raw_packet_has_length_prefix():
    """Packet must start with a 4-byte big-endian length matching the OSC body."""
    client = EosClient()
    packet = client._build_raw_packet("/eos/ping")
    assert len(packet) >= 4
    declared_length = struct.unpack(">I", packet[:4])[0]
    assert declared_length == len(packet) - 4


def test_build_raw_packet_with_string_arg():
    client = EosClient()
    packet = client._build_raw_packet("/eos/cmd", "Chan 1 At Full Enter")
    declared_length = struct.unpack(">I", packet[:4])[0]
    assert declared_length == len(packet) - 4
    assert b"/eos/cmd" in packet


def test_build_raw_packet_with_int_arg():
    """Subscribe packet must contain int arg 1."""
    client = EosClient()
    packet = client._build_raw_packet("/eos/subscribe", 1)
    declared_length = struct.unpack(">I", packet[:4])[0]
    assert declared_length == len(packet) - 4
    assert b"/eos/subscribe" in packet


# ── _handle_osc_message ──────────────────────────────────────────────────────

def _mock_msg(address: str, params: list) -> MagicMock:
    msg = MagicMock()
    msg.address = address
    msg.params = params
    return msg


def test_handle_osc_show_name():
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/show/name", ["Hamlet Act II"]))
    assert client.board_state.show_name == "Hamlet Act II"
    assert client.board_state.last_updated is not None


def test_handle_osc_active_cue_text():
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/active/cue/text", ["1/5 Intro 3.00 75%"]))
    assert client.board_state.active_cue_list  == "1"
    assert client.board_state.active_cue       == "5"
    assert client.board_state.active_cue_label == "Intro"


def test_handle_osc_pending_cue_text():
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/pending/cue/text", ["1/6 Verse 5.00"]))
    assert client.board_state.next_cue_list == "1"
    assert client.board_state.next_cue      == "6"


def test_handle_osc_event_state_live():
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/event/state", [1]))
    assert client.board_state.mode == "Live"


def test_handle_osc_event_state_blind():
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/event/state", [0]))
    assert client.board_state.mode == "Blind"


def test_handle_osc_event_state_unknown_value():
    """Unexpected state values must not be mapped to Live or Blind."""
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/event/state", [99]))
    assert client.board_state.mode == "unknown"


def test_handle_osc_event_state_non_int():
    """Non-integer state values must not raise and must leave mode as unknown."""
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/event/state", ["live"]))
    assert client.board_state.mode == "unknown"


def test_handle_osc_unknown_address_does_not_raise():
    """Unrecognized addresses must be silently ignored."""
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/notify/patch/list/0/1", [42, "uid-abc"]))
    assert client.board_state.last_updated is not None


def test_handle_osc_empty_params_does_not_raise():
    """Empty params list for a known address must not raise."""
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/show/name", []))
    assert client.board_state.show_name is None  # unchanged


# ── BoardState defaults ───────────────────────────────────────────────────────

def test_board_state_defaults():
    state = BoardState()
    assert state.connected is False
    assert state.mode == "unknown"
    assert state.show_name is None
    assert state.last_updated is None
    assert state.active_cue is None
    assert state.next_cue is None
