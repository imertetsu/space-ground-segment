"""Tests for PUS service-1 command-verification ACK packets (Phase 3)."""

from __future__ import annotations

import pytest

from sgs_sim import pus
from sgs_sim.ccsds import APID_VERIFICATION, PrimaryHeader, SequenceCounter
from sgs_sim.pus import MessageTypeCounter, PusTmSecondaryHeader
from sgs_sim.tc import REQUEST_ID_LEN
from sgs_sim.verification import (
    ACK_PACKET_LEN,
    build_acceptance_failure,
    build_acceptance_success,
    build_ack_packet,
    build_completion_failure,
    build_completion_success,
)

_REQUEST_ID = bytes([0x0C, 0x80, 0xC0, 0x2A])  # sample TC first-4-octets


def _counters() -> tuple[SequenceCounter, MessageTypeCounter]:
    return SequenceCounter(), MessageTypeCounter()


def _decode(packet: bytes) -> tuple[PrimaryHeader, PusTmSecondaryHeader, bytes]:
    primary = PrimaryHeader.unpack(packet)
    secondary = PusTmSecondaryHeader.unpack(packet[6:])
    request_id = packet[6 + pus.SECONDARY_HEADER_LEN :]
    return primary, secondary, request_id


@pytest.mark.parametrize(
    ("builder", "subtype"),
    [
        (build_acceptance_success, pus.SUBTYPE_ACCEPTANCE_SUCCESS),
        (build_acceptance_failure, pus.SUBTYPE_ACCEPTANCE_FAILURE),
        (build_completion_success, pus.SUBTYPE_COMPLETION_SUCCESS),
        (build_completion_failure, pus.SUBTYPE_COMPLETION_FAILURE),
    ],
)
def test_ack_has_correct_apid_service_subtype_and_request_id(builder: object, subtype: int) -> None:
    seq, msg = _counters()
    packet = builder(_REQUEST_ID, seq, msg)  # type: ignore[operator]
    assert len(packet) == ACK_PACKET_LEN == 17

    primary, secondary, request_id = _decode(packet)
    assert primary.apid == APID_VERIFICATION == 102
    assert primary.packet_type == 0  # TM
    assert primary.secondary_header_flag == 1
    assert secondary.service_type == pus.SERVICE_VERIFICATION == 1
    assert secondary.message_subtype == subtype
    # The request id echoes the TC's first 4 octets exactly.
    assert request_id == _REQUEST_ID
    assert len(request_id) == REQUEST_ID_LEN


def test_subtype_values_match_ecss() -> None:
    assert pus.SUBTYPE_ACCEPTANCE_SUCCESS == 1
    assert pus.SUBTYPE_ACCEPTANCE_FAILURE == 2
    assert pus.SUBTYPE_COMPLETION_SUCCESS == 7
    assert pus.SUBTYPE_COMPLETION_FAILURE == 8


def test_packet_data_length_field() -> None:
    seq, msg = _counters()
    packet = build_acceptance_success(_REQUEST_ID, seq, msg)
    primary = PrimaryHeader.unpack(packet)
    # data field = secondary(7) + requestId(4) = 11 -> packetDataLength = 10
    assert primary.packet_data_length == 10


def test_sequence_count_advances_per_ack() -> None:
    seq, msg = _counters()
    p1 = build_acceptance_success(_REQUEST_ID, seq, msg)
    p2 = build_completion_success(_REQUEST_ID, seq, msg)
    assert PrimaryHeader.unpack(p2).sequence_count == (PrimaryHeader.unpack(p1).sequence_count + 1)


def test_build_ack_rejects_bad_request_id_length() -> None:
    seq, msg = _counters()
    with pytest.raises(ValueError):
        build_ack_packet(
            subtype=pus.SUBTYPE_ACCEPTANCE_SUCCESS,
            request_id=b"\x00\x01\x02",  # 3 octets, not 4
            seq_counter=seq,
            msg_counter=msg,
        )
