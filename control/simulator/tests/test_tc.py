"""Tests for telecommand parsing + validation (Phase 3 command set)."""

from __future__ import annotations

import struct

import pytest

from sgs_sim import pus, tc
from sgs_sim.ccsds import APID_TC, TYPE_TC, PrimaryHeader
from sgs_sim.hk import SpacecraftMode
from sgs_sim.tc import (
    REQUEST_ID_LEN,
    TcParseError,
    TcRejectReason,
    build_tc_packet,
    extract_request_id,
)


def test_set_mode_round_trip() -> None:
    packet = build_tc_packet(
        subtype=pus.SUBTYPE_CMD_SET_MODE, sequence_count=7, args=bytes([SpacecraftMode.PAYLOAD])
    )
    parsed = tc.parse(packet)
    assert parsed.primary.packet_type == TYPE_TC
    assert parsed.primary.apid == APID_TC
    assert parsed.primary.sequence_count == 7
    assert parsed.service_type == pus.SERVICE_COMMAND
    assert parsed.message_subtype == pus.SUBTYPE_CMD_SET_MODE
    assert parsed.args == bytes([SpacecraftMode.PAYLOAD])

    result = tc.validate(parsed)
    assert result.ok
    assert result.mode == SpacecraftMode.PAYLOAD


def test_ping_round_trip_no_args() -> None:
    packet = build_tc_packet(subtype=pus.SUBTYPE_CMD_PING, sequence_count=3)
    parsed = tc.parse(packet)
    assert parsed.message_subtype == pus.SUBTYPE_CMD_PING
    assert parsed.args == b""
    result = tc.validate(parsed)
    assert result.ok
    assert result.mode is None


def test_tc_secondary_header_fields() -> None:
    packet = build_tc_packet(subtype=pus.SUBTYPE_CMD_PING, sequence_count=0)
    parsed = tc.parse(packet)
    sec = parsed.secondary
    assert sec.pus_version == pus.PUS_VERSION_C  # 2
    assert sec.ack_flags == pus.ACK_FLAGS_ACCEPT_COMPLETE  # 0b1001
    assert sec.service_type == pus.SERVICE_COMMAND  # 132
    assert sec.source_id == pus.SOURCE_ID_GROUND  # 0
    # octet0 == (2 << 4) | 0b1001 == 0x29
    assert packet[6] == 0x29


def test_request_id_is_first_four_octets() -> None:
    packet = build_tc_packet(
        subtype=pus.SUBTYPE_CMD_SET_MODE, sequence_count=42, args=bytes([SpacecraftMode.SAFE])
    )
    parsed = tc.parse(packet)
    assert len(parsed.request_id) == REQUEST_ID_LEN == 4
    assert parsed.request_id == packet[:4]
    assert extract_request_id(packet) == packet[:4]
    # The request id encodes the CCSDS packet id (word0) + seq control (word1).
    word0, word1 = struct.unpack(">HH", parsed.request_id)
    assert (word0 & 0x07FF) == APID_TC  # APID in word0
    assert (word1 & 0x3FFF) == 42  # sequence count in word1


def test_validate_rejects_unknown_subtype() -> None:
    packet = build_tc_packet(subtype=99, sequence_count=1)
    result = tc.validate(tc.parse(packet))
    assert not result.ok
    assert result.reason is TcRejectReason.UNKNOWN_SUBTYPE


def test_validate_rejects_unknown_service() -> None:
    # Hand-build a TC with service != 132 but the TC APID/type, so parse() passes.
    sec = pus.PusTcSecondaryHeader(service_type=8, message_subtype=1).pack()
    data_field = sec + bytes([1])
    primary = PrimaryHeader(
        version=0,
        packet_type=TYPE_TC,
        secondary_header_flag=1,
        apid=APID_TC,
        sequence_flags=0b11,
        sequence_count=0,
        packet_data_length=len(data_field) - 1,
    ).pack()
    result = tc.validate(tc.parse(primary + data_field))
    assert not result.ok
    assert result.reason is TcRejectReason.UNKNOWN_SERVICE


def test_validate_rejects_out_of_range_mode() -> None:
    packet = build_tc_packet(subtype=pus.SUBTYPE_CMD_SET_MODE, sequence_count=2, args=bytes([5]))
    result = tc.validate(tc.parse(packet))
    assert not result.ok
    assert result.reason is TcRejectReason.ARG_OUT_OF_RANGE


def test_validate_rejects_set_mode_missing_arg() -> None:
    packet = build_tc_packet(subtype=pus.SUBTYPE_CMD_SET_MODE, sequence_count=2)
    result = tc.validate(tc.parse(packet))
    assert not result.ok
    assert result.reason is TcRejectReason.MISSING_ARG


@pytest.mark.parametrize("mode", list(SpacecraftMode))
def test_validate_accepts_all_valid_modes(mode: SpacecraftMode) -> None:
    packet = build_tc_packet(subtype=pus.SUBTYPE_CMD_SET_MODE, sequence_count=0, args=bytes([mode]))
    result = tc.validate(tc.parse(packet))
    assert result.ok
    assert result.mode == mode


def test_parse_rejects_too_short() -> None:
    with pytest.raises(TcParseError) as exc:
        tc.parse(b"\x00\x01\x02")
    assert exc.value.reason is TcRejectReason.TOO_SHORT


def test_parse_rejects_tm_packet_type() -> None:
    # A TM (type=0) packet on the TC APID must be rejected structurally.
    primary = PrimaryHeader(
        version=0,
        packet_type=0,  # TM
        secondary_header_flag=1,
        apid=APID_TC,
        sequence_flags=0b11,
        sequence_count=0,
        packet_data_length=4,
    ).pack()
    with pytest.raises(TcParseError) as exc:
        tc.parse(primary + b"\x00" * 5)
    assert exc.value.reason is TcRejectReason.BAD_PACKET_TYPE


def test_parse_rejects_wrong_apid() -> None:
    primary = PrimaryHeader(
        version=0,
        packet_type=TYPE_TC,
        secondary_header_flag=1,
        apid=300,  # not the TC APID
        sequence_flags=0b11,
        sequence_count=0,
        packet_data_length=4,
    ).pack()
    with pytest.raises(TcParseError) as exc:
        tc.parse(primary + b"\x00" * 5)
    assert exc.value.reason is TcRejectReason.BAD_APID


def test_extract_request_id_too_short() -> None:
    with pytest.raises(TcParseError):
        extract_request_id(b"\x01\x02")
