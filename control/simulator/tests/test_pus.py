"""Tests for the PUS-C TM secondary header (frozen contract)."""

from __future__ import annotations

import pytest

from sgs_sim import pus
from sgs_sim.pus import MessageTypeCounter, PusTmSecondaryHeader


def test_secondary_header_round_trip() -> None:
    sh = PusTmSecondaryHeader(
        service_type=3,
        message_subtype=25,
        message_type_counter=7,
        destination_id=0,
    )
    assert PusTmSecondaryHeader.unpack(sh.pack()) == sh


def test_secondary_header_is_seven_octets() -> None:
    sh = PusTmSecondaryHeader(service_type=5, message_subtype=4, message_type_counter=0)
    assert len(sh.pack()) == pus.SECONDARY_HEADER_LEN == 7


def test_first_byte_is_0x20() -> None:
    sh = PusTmSecondaryHeader(service_type=3, message_subtype=25, message_type_counter=0)
    assert sh.pack()[0] == 0x20 == pus.PUS_HEADER_OCTET0


def test_service_and_subtype_placement() -> None:
    sh = PusTmSecondaryHeader(service_type=3, message_subtype=25, message_type_counter=0x1234)
    packed = sh.pack()
    assert packed[1] == 3  # service type
    assert packed[2] == 25  # message subtype
    assert int.from_bytes(packed[3:5], "big") == 0x1234  # message type counter
    assert int.from_bytes(packed[5:7], "big") == 0  # destination id (ground)


def test_pus_version_is_c() -> None:
    sh = PusTmSecondaryHeader(service_type=3, message_subtype=25, message_type_counter=0)
    assert sh.pus_version == pus.PUS_VERSION_C == 0b0010
    decoded = PusTmSecondaryHeader.unpack(sh.pack())
    assert decoded.pus_version == 0b0010
    assert decoded.time_ref_status == 0


def test_service_subtype_constants() -> None:
    assert pus.SERVICE_HK == 3
    assert pus.SUBTYPE_HK_PARAM_REPORT == 25
    assert pus.SERVICE_EVENT == 5
    assert pus.SUBTYPE_EVENT_INFO == 1
    assert pus.SUBTYPE_EVENT_LOW == 2
    assert pus.SUBTYPE_EVENT_MEDIUM == 3
    assert pus.SUBTYPE_EVENT_HIGH == 4


def test_message_type_counter_per_service() -> None:
    counter = MessageTypeCounter()
    assert counter.next(3) == 0
    assert counter.next(3) == 1
    assert counter.next(5) == 0  # independent per service
    assert counter.next(3) == 2


def test_pack_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        PusTmSecondaryHeader(service_type=256, message_subtype=0, message_type_counter=0).pack()


def test_unpack_rejects_short_buffer() -> None:
    with pytest.raises(ValueError):
        PusTmSecondaryHeader.unpack(b"\x20\x03")
