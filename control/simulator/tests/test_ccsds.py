"""Tests for the CCSDS primary header (frozen contract)."""

from __future__ import annotations

import pytest

from sgs_sim import ccsds
from sgs_sim.ccsds import (
    APID_HK,
    SEQ_COUNT_MODULO,
    PrimaryHeader,
    SequenceCounter,
    build_primary_header,
)


def test_primary_header_round_trip() -> None:
    hdr = PrimaryHeader(
        version=0,
        packet_type=0,
        secondary_header_flag=1,
        apid=APID_HK,
        sequence_flags=0b11,
        sequence_count=1234,
        packet_data_length=18,
    )
    assert PrimaryHeader.unpack(hdr.pack()) == hdr


def test_primary_header_is_six_octets() -> None:
    hdr = build_primary_header(apid=APID_HK, sequence_count=0, data_field_len=19)
    assert len(hdr.pack()) == ccsds.PRIMARY_HEADER_LEN == 6


def test_field_widths_and_masks() -> None:
    # APID occupies the low 11 bits of word0; type/version/sec-hdr are above it.
    hdr = build_primary_header(apid=0x7FF, sequence_count=0, data_field_len=1)
    word0 = int.from_bytes(hdr.pack()[0:2], "big")
    assert word0 & 0x7FF == 0x7FF  # APID mask
    assert (word0 >> 11) & 0b1 == 1  # secondary header flag
    assert (word0 >> 12) & 0b1 == 0  # TM
    assert (word0 >> 13) & 0b111 == 0  # version


def test_secondary_header_flag_set_by_builder() -> None:
    hdr = build_primary_header(apid=APID_HK, sequence_count=0, data_field_len=19)
    assert hdr.secondary_header_flag == 1
    assert hdr.packet_type == 0  # TM
    assert hdr.sequence_flags == 0b11  # unsegmented


def test_packet_data_length_math() -> None:
    # packetDataLength = data field octets - 1.
    for data_field_len in (1, 11, 19, 65536):
        if data_field_len > 0x10000:
            continue
        hdr = build_primary_header(apid=APID_HK, sequence_count=0, data_field_len=data_field_len)
        assert hdr.packet_data_length == data_field_len - 1


def test_build_rejects_empty_data_field() -> None:
    with pytest.raises(ValueError):
        build_primary_header(apid=APID_HK, sequence_count=0, data_field_len=0)


def test_sequence_count_wraps_mod_16384() -> None:
    counter = SequenceCounter()
    # Drive APID_HK up to the wrap boundary.
    for expected in range(SEQ_COUNT_MODULO):
        assert counter.next(APID_HK) == expected
    # Next one wraps back to 0.
    assert counter.next(APID_HK) == 0


def test_sequence_counter_is_per_apid() -> None:
    counter = SequenceCounter()
    assert counter.next(100) == 0
    assert counter.next(100) == 1
    assert counter.next(101) == 0  # independent stream
    assert counter.next(100) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"version": 8},  # > 3 bits
        {"packet_type": 2},
        {"secondary_header_flag": 2},
        {"apid": 0x800},  # > 11 bits
        {"sequence_flags": 4},
        {"sequence_count": SEQ_COUNT_MODULO},
        {"packet_data_length": 0x10000},
    ],
)
def test_pack_rejects_out_of_range_fields(kwargs: dict[str, int]) -> None:
    base = {
        "version": 0,
        "packet_type": 0,
        "secondary_header_flag": 1,
        "apid": 100,
        "sequence_flags": 0b11,
        "sequence_count": 0,
        "packet_data_length": 18,
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        PrimaryHeader(**base).pack()


def test_unpack_rejects_short_buffer() -> None:
    with pytest.raises(ValueError):
        PrimaryHeader.unpack(b"\x00\x00\x00")
