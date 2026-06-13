"""UDP telecommand receiver + the accept/apply/verify flow (FOS / Epic 2 Phase 3).

SIMULATED telecommanding. Binds a UDP socket on the TC port (Yamcs' ``udp-out``
target, :10025), receives one CCSDS/PUS-C telecommand per datagram, validates it
against the frozen command set (:mod:`sgs_sim.tc`), applies it to the running
:class:`sgs_sim.anomalies.Model`, and returns PUS service-1 verification ACKs
(:mod:`sgs_sim.verification`) over the TM link back to the ground.

Flow per received TC (ECSS-E-ST-70-41C service 1):

    valid TC   -> acceptance-success (TM[1,1])
                  apply (SET_MODE changes spacecraft_mode; PING is a no-op)
                  -> completion-success (TM[1,7])
    invalid TC -> acceptance-failure (TM[1,2])   (rejected; nothing applied)

Every action is logged as SIMULATED. The receiver runs in its own thread so it is
concurrent with the periodic HK loop (:mod:`sgs_sim.sender`).
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable

from sgs_sim import tc
from sgs_sim.anomalies import Model
from sgs_sim.ccsds import SequenceCounter
from sgs_sim.hk import SpacecraftMode
from sgs_sim.pus import MessageTypeCounter
from sgs_sim.tc import ParsedTc, TcParseError
from sgs_sim.verification import (
    build_acceptance_failure,
    build_acceptance_success,
    build_completion_success,
)

logger = logging.getLogger("sgs_sim")

#: Default TC receive port — Yamcs ``udp-out`` (UdpTcDataLink) target.
DEFAULT_TC_PORT = 10025

#: Max datagram size we read (a TC is tiny; this is generous headroom).
_RECV_BUFSIZE = 4096

#: Poll timeout (s) so the receive loop can notice a stop request promptly.
_RECV_TIMEOUT = 0.2


# Sender callback: emit an ACK packet over the TM link. Injected so the receiver
# does not own a TM socket (the HK loop owns the TM UdpSender).
AckSender = Callable[[bytes], None]


class TcReceiver:
    """Receives + verifies telecommands and applies them to the model.

    The receiver owns its own CCSDS sequence counter (APID 102) and PUS message
    type counter (service 1) for the verification ACK stream it emits.
    """

    def __init__(self, model: Model, ack_sender: AckSender) -> None:
        self._model = model
        self._ack_sender = ack_sender
        self._seq_counter = SequenceCounter()
        self._msg_counter = MessageTypeCounter()

    def handle_datagram(self, datagram: bytes) -> None:
        """Process one received UDP datagram as a telecommand.

        Structurally parses + validates the TC, emits the matching service-1
        ACK(s), and applies a valid command to the model. Never raises — a
        malformed datagram is logged and (when a request id is recoverable) gets
        an acceptance-failure ACK.
        """
        try:
            parsed = tc.parse(datagram)
        except TcParseError as exc:
            self._handle_unparseable(datagram, exc)
            return

        result = tc.validate(parsed)
        if not result.ok:
            reason = result.reason.value if result.reason else "invalid"
            logger.warning(
                "SIMULATED TC REJECTED at validation (acceptance-failure): "
                "service=%d subtype=%d reason=%s (%s)",
                parsed.service_type,
                parsed.message_subtype,
                reason,
                result.detail,
            )
            self._send(build_acceptance_failure, parsed.request_id)
            return

        # Accepted.
        logger.info(
            "SIMULATED TC ACCEPTED (acceptance-success): service=%d subtype=%d request_id=%s",
            parsed.service_type,
            parsed.message_subtype,
            parsed.request_id.hex(),
        )
        self._send(build_acceptance_success, parsed.request_id)

        # Apply, then report completion.
        self._apply(parsed, result.mode)
        logger.info(
            "SIMULATED TC COMPLETED (completion-success): subtype=%d request_id=%s",
            parsed.message_subtype,
            parsed.request_id.hex(),
        )
        self._send(build_completion_success, parsed.request_id)

    def _apply(self, parsed: ParsedTc, mode: SpacecraftMode | None) -> None:
        """Apply an accepted command to the model (SET_MODE / PING)."""
        if mode is not None:  # SET_MODE
            self._model.command_mode(mode)
            logger.info("SIMULATED applied SET_MODE -> %s", mode.name)
        else:  # PING (no-op)
            logger.info("SIMULATED applied PING (no-op)")

    def _handle_unparseable(self, datagram: bytes, exc: TcParseError) -> None:
        """A datagram that is not a structurally valid TC for this FOS."""
        try:
            request_id = tc.extract_request_id(datagram)
        except TcParseError:
            logger.warning("SIMULATED TC dropped (unparseable, no request id): %s", exc)
            return
        logger.warning(
            "SIMULATED TC REJECTED (acceptance-failure): %s request_id=%s",
            exc,
            request_id.hex(),
        )
        self._send(build_acceptance_failure, request_id)

    def _send(
        self,
        builder: Callable[[bytes, SequenceCounter, MessageTypeCounter], bytes],
        request_id: bytes,
    ) -> None:
        packet = builder(request_id, self._seq_counter, self._msg_counter)
        self._ack_sender(packet)


def run_receiver(
    receiver: TcReceiver,
    *,
    host: str,
    port: int,
    stop: threading.Event,
    sock: socket.socket | None = None,
) -> None:
    """Run the blocking TC receive loop until ``stop`` is set.

    Args:
        receiver: the :class:`TcReceiver` that processes each datagram.
        host: bind host (e.g. ``127.0.0.1`` / ``0.0.0.0``).
        port: bind port (the Yamcs TC link target, default :10025).
        stop: a :class:`threading.Event`; the loop exits once it is set.
        sock: an already-bound UDP socket (for tests); created + bound otherwise.
    """
    owns_sock = sock is None
    if sock is None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError as exc:
            # Port busy (e.g. another instance / live Yamcs side). Do not crash
            # the simulator — log and run TM-only.
            logger.error(
                "SIMULATED TC receiver could not bind %s:%d (%s); running TM-only",
                host,
                port,
                exc,
            )
            sock.close()
            return
    sock.settimeout(_RECV_TIMEOUT)
    logger.info("SIMULATED TC receiver listening on %s:%d (UDP)", host, port)
    try:
        while not stop.is_set():
            try:
                datagram, _addr = sock.recvfrom(_RECV_BUFSIZE)
            except TimeoutError:
                continue
            except OSError:
                if stop.is_set():
                    break
                raise
            receiver.handle_datagram(datagram)
    finally:
        if owns_sock:
            sock.close()


def start_receiver_thread(
    receiver: TcReceiver,
    *,
    host: str,
    port: int,
    stop: threading.Event,
) -> threading.Thread:
    """Start :func:`run_receiver` in a daemon thread and return it."""
    thread = threading.Thread(
        target=run_receiver,
        args=(receiver,),
        kwargs={"host": host, "port": port, "stop": stop},
        name="sgs-sim-tc-receiver",
        daemon=True,
    )
    thread.start()
    return thread
