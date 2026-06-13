"""Tests for the HK parameter field-map (frozen contract)."""

from __future__ import annotations

import pytest

from sgs_sim import hk, pus
from sgs_sim.ccsds import APID_HK, PrimaryHeader, SequenceCounter
from sgs_sim.hk import HkParameters, SpacecraftMode, build_hk_packet, decode_hk_packet
from sgs_sim.pus import MessageTypeCounter


def _sample_params() -> HkParameters:
    return HkParameters(
        battery_voltage=7800,
        battery_current=1000,
        obc_temp=2000,
        battery_temp=1500,
        reaction_wheel_speed=3000,
        spacecraft_mode=SpacecraftMode.NOMINAL,
    )


def test_user_data_round_trip() -> None:
    params = _sample_params()
    assert HkParameters.decode_user_data(params.encode_user_data()) == params


def test_full_packet_round_trip() -> None:
    params = _sample_params()
    packet = build_hk_packet(params, SequenceCounter(), MessageTypeCounter())
    decoded = decode_hk_packet(packet)
    assert decoded.parameters == params
    assert decoded.secondary_header.service_type == pus.SERVICE_HK
    assert decoded.secondary_header.message_subtype == pus.SUBTYPE_HK_PARAM_REPORT


def test_total_packet_length_is_25() -> None:
    packet = build_hk_packet(_sample_params(), SequenceCounter(), MessageTypeCounter())
    assert len(packet) == 25 == hk.HK_PACKET_LEN


def test_primary_header_in_packet() -> None:
    packet = build_hk_packet(_sample_params(), SequenceCounter(), MessageTypeCounter())
    ph = PrimaryHeader.unpack(packet)
    assert ph.apid == APID_HK
    assert ph.secondary_header_flag == 1
    assert ph.packet_data_length == 18  # 19 - 1


def test_raw_to_engineering_conversions() -> None:
    params = HkParameters(
        battery_voltage=7800,
        battery_current=1500,
        obc_temp=2000,
        battery_temp=1500,
        reaction_wheel_speed=3000,
        spacecraft_mode=SpacecraftMode.PAYLOAD,
    )
    assert params.battery_voltage_eng() == pytest.approx(7.8)
    assert params.battery_current_eng() == pytest.approx(1.5)
    assert params.obc_temp_eng() == pytest.approx(20.0)
    assert params.battery_temp_eng() == pytest.approx(15.0)
    assert params.reaction_wheel_speed_eng() == pytest.approx(3000.0)


def test_conversion_factors_match_contract() -> None:
    assert hk.VOLTAGE_FACTOR == 0.001
    assert hk.CURRENT_FACTOR == 0.001
    assert hk.OBC_TEMP_FACTOR == 0.01
    assert hk.BATTERY_TEMP_FACTOR == 0.01
    assert hk.RW_SPEED_FACTOR == 1.0


def test_signed_int16_fields_round_trip() -> None:
    params = HkParameters(
        battery_voltage=0,
        battery_current=0,
        obc_temp=-2000,
        battery_temp=-500,
        reaction_wheel_speed=-4000,
        spacecraft_mode=SpacecraftMode.SAFE,
    )
    decoded = HkParameters.decode_user_data(params.encode_user_data())
    assert decoded.obc_temp == -2000
    assert decoded.battery_temp == -500
    assert decoded.reaction_wheel_speed == -4000
    assert decoded.obc_temp_eng() == pytest.approx(-20.0)


def test_enum_bounds() -> None:
    assert SpacecraftMode.SAFE == 0
    assert SpacecraftMode.NOMINAL == 1
    assert SpacecraftMode.PAYLOAD == 2
    for mode in SpacecraftMode:
        params = HkParameters(
            battery_voltage=7800,
            battery_current=1000,
            obc_temp=2000,
            battery_temp=1500,
            reaction_wheel_speed=3000,
            spacecraft_mode=mode,
        )
        decoded = HkParameters.decode_user_data(params.encode_user_data())
        assert decoded.spacecraft_mode == mode


def test_decode_rejects_bad_structure_id() -> None:
    # Hand-craft user data with structureId = 9.
    bad = bytes([9]) + b"\x00" * (hk.HK_USER_DATA_LEN - 1)
    with pytest.raises(ValueError):
        HkParameters.decode_user_data(bad)


def test_decode_rejects_invalid_mode() -> None:
    params = _sample_params()
    data = bytearray(params.encode_user_data())
    data[-1] = 9  # invalid spacecraft_mode
    with pytest.raises(ValueError):
        HkParameters.decode_user_data(bytes(data))
