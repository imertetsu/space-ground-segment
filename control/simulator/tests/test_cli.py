"""Tests for the CLI / emit loop over a real loopback UDP receiver."""

from __future__ import annotations

import socket
from itertools import pairwise

from sgs_sim import config as cfg_mod
from sgs_sim.ccsds import APID_HK, PrimaryHeader
from sgs_sim.cli.main import main
from sgs_sim.hk import HK_PACKET_LEN, decode_hk_packet


def _bind_receiver() -> tuple[socket.socket, int]:
    """Bind a loopback UDP receiver on an ephemeral port (before sending)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(5.0)
    return sock, sock.getsockname()[1]


def _drain(sock: socket.socket) -> list[bytes]:
    packets: list[bytes] = []
    sock.settimeout(0.5)
    try:
        while True:
            data, _ = sock.recvfrom(4096)
            packets.append(data)
    except TimeoutError:
        pass
    return packets


def test_cli_short_run_emits_valid_hk_packets() -> None:
    receiver, port = _bind_receiver()
    try:
        rc = main(
            [
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--rate",
                "50",
                "--duration",
                "0.2",
                "--no-tc",
            ]
        )
        assert rc == 0
        packets = _drain(receiver)
    finally:
        receiver.close()

    assert packets, "no packets received"

    hk_packets = [p for p in packets if PrimaryHeader.unpack(p).apid == APID_HK]
    assert hk_packets, "no HK packets received"

    for packet in hk_packets:
        ph = PrimaryHeader.unpack(packet)
        assert ph.version == 0
        assert ph.packet_type == 0  # TM
        assert ph.secondary_header_flag == 1
        assert ph.apid == APID_HK
        assert ph.sequence_flags == 0b11
        assert len(packet) == HK_PACKET_LEN == 25
        assert ph.packet_data_length == len(packet) - 6 - 1
        # Decodes against the frozen field-map.
        decode_hk_packet(packet)


def test_cli_sequence_counts_advance() -> None:
    receiver, port = _bind_receiver()
    try:
        main(
            [
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--rate",
                "50",
                "--duration",
                "0.2",
                "--no-tc",
            ]
        )
        packets = _drain(receiver)
    finally:
        receiver.close()

    hk_counts = [
        PrimaryHeader.unpack(p).sequence_count
        for p in packets
        if PrimaryHeader.unpack(p).apid == APID_HK
    ]
    assert len(hk_counts) >= 2
    # Sequence counts advance by 1 each HK packet (monotonic for a short run).
    for prev, cur in pairwise(hk_counts):
        assert cur == prev + 1


def test_cli_bad_config_returns_error_code() -> None:
    rc = main(["--config", "does-not-exist.toml", "--duration", "0.1"])
    assert rc == 2


def test_default_config_path_exists() -> None:
    assert cfg_mod.default_config_path().is_file()
