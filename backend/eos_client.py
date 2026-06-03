import asyncio
import dataclasses
import re
import struct
import time
import logging
from typing import Optional
from pythonosc import osc_message_builder
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message import ParseError as OscParseError
from config import settings

logger = logging.getLogger(__name__)

_RATE_LIMIT_S = 0.05  # EOS rejects commands sent faster than 50ms apart
_RECONNECT_ATTEMPTS = 3
_RECONNECT_DELAY_S = 1.0
_CONNECT_TIMEOUT_S = 5.0


class EosUnreachableError(Exception):
    pass


@dataclasses.dataclass
class BoardState:
    show_name:        Optional[str]   = None
    active_cue:       Optional[str]   = None
    active_cue_list:  Optional[str]   = None
    active_cue_label: Optional[str]   = None
    next_cue:         Optional[str]   = None
    next_cue_list:    Optional[str]   = None
    mode:             str             = "unknown"   # "Live" | "Blind" | "unknown"
    connected:        bool            = False
    last_updated:     Optional[float] = None        # time.time() wall-clock


class EosClient:
    def __init__(self):
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._last_sent: float = 0.0
        self._lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._listen_task: asyncio.Task | None = None
        self.board_state = BoardState()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if not settings.eos_host:
            raise EosUnreachableError("EOS_HOST is not configured")
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(settings.eos_host, settings.eos_port),
            timeout=_CONNECT_TIMEOUT_S,
        )
        logger.info("Connected to EOS at %s:%d", settings.eos_host, settings.eos_port)
        try:
            await self._send_subscribe()
        except Exception:
            await self._close_writer()
            raise
        self.board_state = dataclasses.replace(self.board_state, connected=True)

    async def _close_writer(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
            self.board_state = dataclasses.replace(self.board_state, connected=False)

    async def _reconnect(self) -> None:
        async with self._connect_lock:
            if self.connected:
                return  # another coroutine already reconnected
            for attempt in range(1, _RECONNECT_ATTEMPTS + 1):
                await self._close_writer()
                try:
                    await self.connect()
                    return
                except Exception as exc:
                    logger.warning("Reconnect attempt %d/%d failed: %s", attempt, _RECONNECT_ATTEMPTS, exc)
                    if attempt < _RECONNECT_ATTEMPTS:
                        await asyncio.sleep(_RECONNECT_DELAY_S)
            raise EosUnreachableError(
                f"Could not reconnect to EOS after {_RECONNECT_ATTEMPTS} attempts"
            )

    async def _send_subscribe(self) -> None:
        packet = self._build_raw_packet("/eos/subscribe", 1)
        self._writer.write(packet)
        await self._writer.drain()
        logger.info("Sent /eos/subscribe 1")

    def _build_raw_packet(self, address: str, *args) -> bytes:
        builder = osc_message_builder.OscMessageBuilder(address=address)
        for arg in args:
            builder.add_arg(arg)
        msg = builder.build()
        return struct.pack(">I", len(msg.dgram)) + msg.dgram

    def _build_packet(self, cmd: str) -> bytes:
        return self._build_raw_packet("/eos/cmd", cmd)

    @staticmethod
    def _parse_cue_text(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (cue_list, cue_number, label) from EOS active/pending cue text.

        Formats: "list/cue [label words] time [pct%]"  (multi-word labels supported)
        """
        parts = text.strip().split()
        if not parts:
            return None, None, None

        cue_part = parts[0]
        slash = cue_part.find("/")
        if slash < 0:
            return None, None, None
        cue_list = cue_part[:slash]
        cue_num  = cue_part[slash + 1:]

        if len(parts) < 2:
            return cue_list, cue_num, None

        remaining = parts[1:]
        # Drop trailing "75%" if present (active cue format)
        if remaining and remaining[-1].endswith("%"):
            remaining = remaining[:-1]
        # Drop trailing time float (e.g. "3.00")
        if remaining and re.fullmatch(r"\d+\.\d+", remaining[-1]):
            remaining = remaining[:-1]

        label = " ".join(remaining).strip() or None
        return cue_list, cue_num, label

    def _handle_osc_message(self, msg: OscMessage) -> None:
        addr = msg.address
        params = msg.params
        now = time.time()

        if addr == "/eos/out/show/name" and params:
            self.board_state = dataclasses.replace(
                self.board_state, show_name=str(params[0]), last_updated=now
            )

        elif addr == "/eos/out/active/cue/text" and params:
            cl, cq, label = self._parse_cue_text(str(params[0]))
            self.board_state = dataclasses.replace(
                self.board_state, active_cue_list=cl, active_cue=cq, active_cue_label=label, last_updated=now
            )

        elif addr == "/eos/out/pending/cue/text" and params:
            cl, cq, _ = self._parse_cue_text(str(params[0]))
            self.board_state = dataclasses.replace(
                self.board_state, next_cue_list=cl, next_cue=cq, last_updated=now
            )

        elif addr == "/eos/out/event/state" and params:
            val = params[0]
            mode = "Live" if val == 1 else "Blind" if val == 0 else "unknown"
            self.board_state = dataclasses.replace(
                self.board_state, mode=mode, last_updated=now
            )

        else:
            self.board_state = dataclasses.replace(self.board_state, last_updated=now)

    async def _listen_loop(self) -> None:
        logger.info("OSC receive loop started")
        while True:
            try:
                if not settings.eos_host:
                    await asyncio.sleep(10)
                    continue

                if not self.connected:
                    await asyncio.sleep(_RECONNECT_DELAY_S)
                    try:
                        await self._reconnect()
                    except EosUnreachableError:
                        continue

                header = await self._reader.readexactly(4)
                length = struct.unpack(">I", header)[0]
                if length == 0:
                    continue

                body = await self._reader.readexactly(length)
                try:
                    msg = OscMessage(body)
                except OscParseError as exc:
                    logger.debug("Malformed OSC packet ignored: %s", exc)
                    continue
                try:
                    self._handle_osc_message(msg)
                except Exception:
                    logger.exception("Unexpected error handling OSC message %s", msg.address)
                    continue

            except asyncio.IncompleteReadError:
                logger.warning("EOS connection closed (EOF). Will reconnect.")
                await self._close_writer()

            except (ConnectionError, ConnectionResetError, BrokenPipeError) as exc:
                logger.warning("EOS connection error: %s", exc)
                await self._close_writer()

            except asyncio.CancelledError:
                logger.info("OSC receive loop cancelled")
                raise

    async def start_listening(self) -> None:
        if self._listen_task and not self._listen_task.done():
            return
        self._listen_task = asyncio.create_task(
            self._listen_loop(), name="eos-receive-loop"
        )

    async def stop_listening(self) -> None:
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

    async def close(self) -> None:
        """Stop the receive loop and close the TCP connection."""
        await self.stop_listening()
        await self._close_writer()

    async def send_cmd(self, cmd: str) -> None:
        """Send an EOS command string over OSC TCP. Reconnects on connection failure."""
        async with self._lock:
            # Rate limiting: enforce minimum 50ms between sends
            elapsed = time.monotonic() - self._last_sent
            if elapsed < _RATE_LIMIT_S:
                await asyncio.sleep(_RATE_LIMIT_S - elapsed)

            packet = self._build_packet(cmd)

            for attempt in range(_RECONNECT_ATTEMPTS + 1):
                if not self.connected:
                    await self._reconnect()
                try:
                    self._writer.write(packet)
                    await self._writer.drain()
                    self._last_sent = time.monotonic()
                    logger.info("Sent to EOS: %s", cmd)
                    return
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as exc:
                    logger.warning("Send failed (attempt %d): %s", attempt + 1, exc)
                    await self._close_writer()
                    if attempt >= _RECONNECT_ATTEMPTS:
                        raise EosUnreachableError(f"Send failed after {_RECONNECT_ATTEMPTS} retries: {exc}")

    async def ping(self) -> None:
        """Fire-and-forget /eos/ping. Does not wait for /eos/out/ping reply."""
        packet = self._build_raw_packet("/eos/ping")
        async with self._lock:
            if not self.connected:
                await self._reconnect()
            self._writer.write(packet)
            await self._writer.drain()


# Module-level singleton — shared across requests
eos_client = EosClient()
