import asyncio
import struct
import time
import logging
from pythonosc import osc_message_builder
from config import settings

logger = logging.getLogger(__name__)

_RATE_LIMIT_S = 0.05  # EOS rejects commands sent faster than 50ms apart
_RECONNECT_ATTEMPTS = 3
_RECONNECT_DELAY_S = 1.0
_CONNECT_TIMEOUT_S = 5.0


class EosUnreachableError(Exception):
    pass


class EosClient:
    def __init__(self):
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._last_sent: float = 0.0
        self._lock = asyncio.Lock()

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

    async def _close_writer(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    async def _reconnect(self) -> None:
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

    def _build_packet(self, cmd: str) -> bytes:
        builder = osc_message_builder.OscMessageBuilder(address="/eos/cmd")
        builder.add_arg(cmd)
        msg = builder.build()
        dgram = msg.dgram
        # OSC 1.0 TCP framing: 4-byte big-endian length prefix
        return struct.pack(">I", len(dgram)) + dgram

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
        builder = osc_message_builder.OscMessageBuilder(address="/eos/ping")
        msg = builder.build()
        dgram = msg.dgram
        packet = struct.pack(">I", len(dgram)) + dgram
        async with self._lock:
            if not self.connected:
                await self._reconnect()
            self._writer.write(packet)
            await self._writer.drain()


# Module-level singleton — shared across requests
eos_client = EosClient()
