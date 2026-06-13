"""UDP packet sender + the periodic emit loop.

SIMULATED telemetry. Opens a UDP socket to the Yamcs ``UdpTmDataLink`` target
(1 datagram = 1 CCSDS packet) and runs the periodic emit loop: one HK packet per
tick, plus PUS-5 event packets whenever the model triggers them.

The loop is bounded by ``duration`` (seconds; 0 = forever) so it never becomes a
long-lived unbounded process in tests / CI.
"""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable

from sgs_sim.anomalies import Model
from sgs_sim.ccsds import SequenceCounter
from sgs_sim.config import SimConfig
from sgs_sim.events import build_event_packet
from sgs_sim.hk import build_hk_packet
from sgs_sim.pus import MessageTypeCounter

logger = logging.getLogger("sgs_sim")


class UdpSender:
    """Thin wrapper over a UDP socket to a fixed (host, port) target."""

    def __init__(self, host: str, port: int) -> None:
        self._target = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, packet: bytes) -> None:
        """Send one packet as a single UDP datagram."""
        self._sock.sendto(packet, self._target)

    def close(self) -> None:
        """Close the underlying socket."""
        self._sock.close()

    def __enter__(self) -> UdpSender:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def run_loop(
    config: SimConfig,
    *,
    duration: float,
    sender: UdpSender | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> int:
    """Run the periodic emit loop.

    Args:
        config: the resolved simulator configuration.
        duration: run time in seconds; ``0`` = forever (until interrupted).
        sender: an open :class:`UdpSender`; created from ``config`` if ``None``
            (and closed on exit).
        sleep: injectable sleep (for tests).
        now: injectable monotonic clock (for tests).

    Returns:
        The number of HK packets emitted.
    """
    owns_sender = sender is None
    if sender is None:
        sender = UdpSender(config.host, config.port)

    model = Model(config)
    seq_counter = SequenceCounter()
    msg_counter = MessageTypeCounter()
    period = 1.0 / config.rate_hz if config.rate_hz > 0 else 0.0

    hk_count = 0
    start = now()
    try:
        while True:
            tick = model.step()

            hk_packet = build_hk_packet(tick.params, seq_counter, msg_counter)
            sender.send(hk_packet)
            hk_count += 1

            for event in tick.events:
                event_packet = build_event_packet(event, seq_counter, msg_counter)
                sender.send(event_packet)
                logger.info(
                    "SIMULATED event emitted: id=%s subtype=%d context=%d",
                    event.event_id.name,
                    event.subtype,
                    event.context,
                )

            if duration > 0 and (now() - start) >= duration:
                break

            if period > 0:
                sleep(period)
    finally:
        if owns_sender:
            sender.close()

    return hk_count
