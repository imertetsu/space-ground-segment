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
import threading
import time
from collections.abc import Callable

from sgs_sim.anomalies import Model
from sgs_sim.ccsds import SequenceCounter
from sgs_sim.config import SimConfig
from sgs_sim.events import build_event_packet
from sgs_sim.hk import build_hk_packet
from sgs_sim.pus import MessageTypeCounter
from sgs_sim.receiver import TcReceiver, start_receiver_thread

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
    enable_tc: bool = True,
) -> int:
    """Run the periodic emit loop (and, by default, the concurrent TC receiver).

    Args:
        config: the resolved simulator configuration.
        duration: run time in seconds; ``0`` = forever (until interrupted).
        sender: an open :class:`UdpSender`; created from ``config`` if ``None``
            (and closed on exit).
        sleep: injectable sleep (for tests).
        now: injectable monotonic clock (for tests).
        enable_tc: start the UDP telecommand receiver (binds ``config.tc_port``)
            concurrently with the HK loop. The receiver applies accepted TCs to
            the model and emits PUS service-1 ACKs over the same TM link.

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

    stop = threading.Event()
    tc_thread = None
    if enable_tc:
        # ACKs go out over the same TM link (UDP sendto is thread-safe).
        tc_receiver = TcReceiver(model, sender.send)
        tc_thread = start_receiver_thread(
            tc_receiver, host=config.tc_host, port=config.tc_port, stop=stop
        )

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
        stop.set()
        if tc_thread is not None:
            tc_thread.join(timeout=2.0)
        if owns_sender:
            sender.close()

    return hk_count
