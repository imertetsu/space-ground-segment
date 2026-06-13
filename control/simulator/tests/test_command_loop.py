"""Integration test: TC -> accept -> apply -> verify, over loopback UDP.

Runs the full emit loop (HK + concurrent TC receiver), sends real telecommands
to the simulator's TC port, and asserts the PUS service-1 ACKs come back over the
TM link and that a SET_MODE actually changes the HK ``spacecraft_mode``.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from sgs_sim import config as config_mod
from sgs_sim import pus
from sgs_sim.ccsds import APID_HK, APID_VERIFICATION, PrimaryHeader
from sgs_sim.config import SimConfig
from sgs_sim.hk import SpacecraftMode, decode_hk_packet
from sgs_sim.pus import PusTmSecondaryHeader
from sgs_sim.sender import run_loop
from sgs_sim.tc import build_tc_packet


def _free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _test_config() -> tuple[SimConfig, int, int]:
    """Config with ephemeral TM + TC ports (so tests never collide on :10025)."""
    base = config_mod.load(config_mod.default_config_path())
    tm_port = _free_udp_port()
    tc_port = _free_udp_port()
    cfg = base.with_overrides(
        host="127.0.0.1",
        port=tm_port,
        tc_host="127.0.0.1",
        tc_port=tc_port,
        rate_hz=50.0,
    )
    return cfg, tm_port, tc_port


class _Decoded:
    """Helper to classify a received TM packet."""

    @staticmethod
    def ack(packet: bytes) -> tuple[int, bytes] | None:
        """Return (subtype, request_id) if this is a service-1 ACK, else None."""
        primary = PrimaryHeader.unpack(packet)
        if primary.apid != APID_VERIFICATION:
            return None
        sec = PusTmSecondaryHeader.unpack(packet[6:])
        if sec.service_type != pus.SERVICE_VERIFICATION:
            return None
        request_id = packet[6 + pus.SECONDARY_HEADER_LEN :]
        return sec.message_subtype, request_id


def _run_loop_thread(cfg: SimConfig, duration: float) -> threading.Thread:
    thread = threading.Thread(
        target=run_loop, args=(cfg,), kwargs={"duration": duration}, daemon=True
    )
    thread.start()
    return thread


def _send_tc_until_ack(
    tm_receiver: socket.socket,
    tc_addr: tuple[str, int],
    packet: bytes,
    want_subtypes: set[int],
    *,
    timeout: float = 4.0,
) -> tuple[dict[int, bytes], list[bytes]]:
    """Send ``packet`` to the TC port (retrying) until the wanted ACK subtypes arrive.

    Returns (subtype -> request_id for the seen ACKs, all HK packets observed).
    """
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    acks: dict[int, bytes] = {}
    hk_packets: list[bytes] = []
    deadline = time.monotonic() + timeout
    tm_receiver.settimeout(0.2)
    last_send = 0.0
    try:
        while time.monotonic() < deadline and not want_subtypes <= acks.keys():
            now = time.monotonic()
            if now - last_send > 0.25:
                sender.sendto(packet, tc_addr)
                last_send = now
            try:
                data, _ = tm_receiver.recvfrom(4096)
            except TimeoutError:
                continue
            primary = PrimaryHeader.unpack(data)
            if primary.apid == APID_HK:
                hk_packets.append(data)
                continue
            classified = _Decoded.ack(data)
            if classified is not None:
                subtype, request_id = classified
                acks.setdefault(subtype, request_id)
    finally:
        sender.close()
    return acks, hk_packets


def _drain_hk(tm_receiver: socket.socket, *, timeout: float = 2.0) -> list[bytes]:
    hk: list[bytes] = []
    tm_receiver.settimeout(0.2)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            data, _ = tm_receiver.recvfrom(4096)
        except TimeoutError:
            continue
        if PrimaryHeader.unpack(data).apid == APID_HK:
            hk.append(data)
    return hk


def test_set_mode_safe_acked_and_changes_hk() -> None:
    cfg, tm_port, tc_port = _test_config()

    tm_receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tm_receiver.bind(("127.0.0.1", tm_port))

    loop = _run_loop_thread(cfg, duration=6.0)
    try:
        # Give the receiver a moment to bind its TC socket.
        time.sleep(0.3)

        set_mode_safe = build_tc_packet(
            subtype=pus.SUBTYPE_CMD_SET_MODE,
            sequence_count=11,
            args=bytes([SpacecraftMode.SAFE]),
        )
        acks, _ = _send_tc_until_ack(
            tm_receiver,
            ("127.0.0.1", tc_port),
            set_mode_safe,
            {pus.SUBTYPE_ACCEPTANCE_SUCCESS, pus.SUBTYPE_COMPLETION_SUCCESS},
        )

        assert pus.SUBTYPE_ACCEPTANCE_SUCCESS in acks, "no acceptance-success ACK"
        assert pus.SUBTYPE_COMPLETION_SUCCESS in acks, "no completion-success ACK"
        # The request id in both ACKs echoes the TC's first 4 octets.
        assert acks[pus.SUBTYPE_ACCEPTANCE_SUCCESS] == set_mode_safe[:4]
        assert acks[pus.SUBTYPE_COMPLETION_SUCCESS] == set_mode_safe[:4]

        # A subsequent HK packet reflects the commanded mode = SAFE.
        hk_after = _drain_hk(tm_receiver, timeout=2.0)
        modes = [decode_hk_packet(p).parameters.spacecraft_mode for p in hk_after]
        assert modes, "no HK packets after the command"
        assert modes[-1] == SpacecraftMode.SAFE, f"mode did not change to SAFE: {modes}"
    finally:
        loop.join(timeout=8.0)
        tm_receiver.close()


def test_invalid_tc_gets_acceptance_failure() -> None:
    cfg, tm_port, tc_port = _test_config()

    tm_receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tm_receiver.bind(("127.0.0.1", tm_port))

    loop = _run_loop_thread(cfg, duration=6.0)
    try:
        time.sleep(0.3)

        # Out-of-range mode (5) -> rejected at validation -> acceptance-failure.
        bad_tc = build_tc_packet(
            subtype=pus.SUBTYPE_CMD_SET_MODE, sequence_count=22, args=bytes([5])
        )
        acks, _ = _send_tc_until_ack(
            tm_receiver,
            ("127.0.0.1", tc_port),
            bad_tc,
            {pus.SUBTYPE_ACCEPTANCE_FAILURE},
        )

        assert pus.SUBTYPE_ACCEPTANCE_FAILURE in acks, "no acceptance-failure ACK"
        assert acks[pus.SUBTYPE_ACCEPTANCE_FAILURE] == bad_tc[:4]
        # An invalid TC must NOT produce a completion-success ACK.
        assert pus.SUBTYPE_COMPLETION_SUCCESS not in acks
    finally:
        loop.join(timeout=8.0)
        tm_receiver.close()


@pytest.mark.parametrize("target", [SpacecraftMode.PAYLOAD, SpacecraftMode.NOMINAL])
def test_set_mode_payload_and_nominal(target: SpacecraftMode) -> None:
    cfg, tm_port, tc_port = _test_config()

    tm_receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tm_receiver.bind(("127.0.0.1", tm_port))

    loop = _run_loop_thread(cfg, duration=6.0)
    try:
        time.sleep(0.3)
        packet = build_tc_packet(
            subtype=pus.SUBTYPE_CMD_SET_MODE, sequence_count=5, args=bytes([target])
        )
        acks, _ = _send_tc_until_ack(
            tm_receiver,
            ("127.0.0.1", tc_port),
            packet,
            {pus.SUBTYPE_COMPLETION_SUCCESS},
        )
        assert pus.SUBTYPE_COMPLETION_SUCCESS in acks
        hk_after = _drain_hk(tm_receiver, timeout=2.0)
        modes = [decode_hk_packet(p).parameters.spacecraft_mode for p in hk_after]
        assert modes and modes[-1] == target
    finally:
        loop.join(timeout=8.0)
        tm_receiver.close()
