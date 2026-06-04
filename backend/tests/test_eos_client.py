import asyncio
import struct
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


# ── _schedule ────────────────────────────────────────────────────────────────

def test_schedule_no_loop_closes_coroutine():
    """With no running loop _schedule must call coro.close(), not leak the coroutine."""
    client = EosClient()

    async def dummy():
        pass  # pragma: no cover

    coro = dummy()
    client._schedule(coro)
    # A closed coroutine has no frame; an un-awaited one still has one.
    assert coro.cr_frame is None


@pytest.mark.asyncio
async def test_schedule_with_loop_creates_task():
    """With an active loop _schedule must create a task that actually runs."""
    client = EosClient()
    ran: list[bool] = []

    async def dummy():
        ran.append(True)

    client._schedule(dummy())
    await asyncio.sleep(0)  # yield so the scheduled task can execute
    assert ran == [True]


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


# ── _parse_active_chan ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("5 [75]",         {5: 75}),
    ("1-3 [100]",      {1: 100, 2: 100, 3: 100}),
    ("1 3 5 [50]",     {1: 50, 3: 50, 5: 50}),
    ("1-3 5 [80]",     {1: 80, 2: 80, 3: 80, 5: 80}),
    ("3-1 [100]",      {1: 100, 2: 100, 3: 100}),  # reversed range normalized
    ("",               {}),
    ("bad input",      {}),
    ("[100]",          {}),           # no channels before bracket
])
def test_parse_active_chan(text, expected):
    assert EosClient._parse_active_chan(text) == expected


# ── _handle_osc_message — /eos/out/active/chan ────────────────────────────────

def test_handle_osc_active_chan_updates_channels():
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/active/chan", ["1-3 [75]"]))
    assert client.board_state.channels == {1: 75, 2: 75, 3: 75}
    assert client.board_state.last_updated is not None


def test_handle_osc_active_chan_replaces_previous():
    """Each push replaces the entire selection, not merges with it."""
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/active/chan", ["1-10 [100]"]))
    client._handle_osc_message(_mock_msg("/eos/out/active/chan", ["5 [50]"]))
    assert client.board_state.channels == {5: 50}


def test_handle_osc_active_chan_empty_params_clears():
    """Empty params (operator deselects) must clear channels."""
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/active/chan", ["5 [75]"]))
    client._handle_osc_message(_mock_msg("/eos/out/active/chan", []))
    assert client.board_state.channels == {}


# ── New OSC handlers — cue count, notify ────────────────────────────────────

def test_handle_osc_cue_count():
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/get/cue/1/count", [14]))
    assert client.board_state.cue_count == 14
    assert client.board_state.last_updated is not None


def test_handle_osc_cue_count_zero():
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/get/cue/1/count", [0]))
    assert client.board_state.cue_count == 0


def test_handle_osc_cue_count_different_list():
    """Cue count response for list 2 still updates cue_count."""
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/get/cue/2/count", [7]))
    assert client.board_state.cue_count == 7


def test_handle_osc_cue_count_empty_params_no_crash():
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/get/cue/1/count", []))
    assert client.board_state.cue_count is None  # unchanged


def test_handle_osc_notify_patch_does_not_raise():
    """Patch notify must not raise; falls through to else branch, updates last_updated."""
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/notify/patch/list/0/1", [42, "uid-abc"]))
    assert client.board_state.last_updated is not None


def test_handle_osc_notify_cue_does_not_raise():
    """Cue notify must not raise even without a running event loop."""
    client = EosClient()
    client._handle_osc_message(_mock_msg("/eos/out/notify/cue/1/list/0/3", [1]))
    assert client.board_state.last_updated is not None


def test_handle_osc_notify_cue_schedules_cue_count_with_correct_list():
    """Cue notify must call _request_cue_count with the list number from the address."""
    client = EosClient()
    # Patch _request_cue_count so calling it returns a coroutine we can inspect.
    # Patch _schedule with a side_effect that closes the coroutine to suppress
    # 'coroutine was never awaited' warnings in tests without a running loop.
    with patch.object(client, "_request_cue_count", new_callable=AsyncMock) as mock_req, \
         patch.object(client, "_schedule", side_effect=lambda coro: coro.close()):
        client._handle_osc_message(_mock_msg("/eos/out/notify/cue/2/list/0/3", [1]))
        mock_req.assert_called_once_with("2")


def test_handle_osc_active_cue_triggers_cue_count_on_list_change():
    """Changing the active cue list must schedule a cue count request (no crash in test)."""
    client = EosClient()
    # First message sets list to "1"
    client._handle_osc_message(_mock_msg("/eos/out/active/cue/text", ["1/5 Intro 3.00 75%"]))
    assert client.board_state.active_cue_list == "1"
    # Second message changes list to "2" — should schedule _request_cue_count("2")
    client._handle_osc_message(_mock_msg("/eos/out/active/cue/text", ["2/1 Opening 2.00 0%"]))
    assert client.board_state.active_cue_list == "2"
    # No exception expected even without a running loop


# ── BoardState defaults ───────────────────────────────────────────────────────

def test_board_state_defaults():
    state = BoardState()
    assert state.connected is False
    assert state.mode == "unknown"
    assert state.show_name is None
    assert state.last_updated is None
    assert state.active_cue is None
    assert state.next_cue is None
    assert state.cue_count is None
    assert state.channels == {}
