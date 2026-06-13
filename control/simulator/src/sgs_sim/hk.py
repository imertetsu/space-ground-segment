"""HK (housekeeping) parameter model + frozen field-map (PUS TM[3,25]).

SIMULATED telemetry. This module defines the FROZEN housekeeping parameter
field-map (the decode contract the XTCE MDB consumes) and the documented
raw <-> engineering conversions. See ``PACKET_FORMAT.md`` for the authoritative
spec.

HK data field (after the 6-octet CCSDS primary header):

    [ PUS-C secondary header : 7 octets ]   (see :mod:`sgs_sim.pus`)
    [ structureId      : uint8  ]  = 1
    [ battery_voltage  : uint16 ]  raw; eng V   = raw * 0.001
    [ battery_current  : uint16 ]  raw; eng A   = raw * 0.001
    [ obc_temp         : int16  ]  raw; eng degC = raw * 0.01
    [ battery_temp     : int16  ]  raw; eng degC = raw * 0.01
    [ reaction_wheel_speed : int16 ]  raw; eng RPM = raw * 1
    [ spacecraft_mode  : uint8  ]  enum 0=SAFE 1=NOMINAL 2=PAYLOAD

Data field length after the primary header = 7 + 1 + (2+2+2+2+2+1) = 19 octets.
Total packet = 6 + 19 = 25 octets; packetDataLength = 19 - 1 = 18.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from sgs_sim import pus
from sgs_sim.ccsds import APID_HK, SequenceCounter, build_primary_header
from sgs_sim.pus import MessageTypeCounter, PusTmSecondaryHeader

# --- Frozen contract constants ----------------------------------------------

STRUCTURE_ID = 1
"""HK structure id (uint8) — identifies this fixed HK report layout."""

#: ``struct`` format for the HK user-data fields after the PUS secondary header.
#: B = structureId(uint8); H H = voltage/current(uint16); h h h = temps + RW(int16);
#: B = spacecraft_mode(uint8). Big-endian.
HK_USER_DATA_FORMAT = ">BHHhhhB"

HK_USER_DATA_LEN = struct.calcsize(HK_USER_DATA_FORMAT)
"""Octets in the HK user data (after the PUS secondary header) = 12."""

HK_DATA_FIELD_LEN = pus.SECONDARY_HEADER_LEN + HK_USER_DATA_LEN
"""Octets in the full HK packet data field (secondary header + user data) = 19."""

HK_PACKET_LEN = 6 + HK_DATA_FIELD_LEN
"""Total octets in an HK packet (primary header + data field) = 25."""

# --- Raw <-> engineering conversion factors (frozen; calibrated in the MDB) ---

VOLTAGE_FACTOR = 0.001
"""battery_voltage: engineering V = raw * 0.001."""

CURRENT_FACTOR = 0.001
"""battery_current: engineering A = raw * 0.001."""

OBC_TEMP_FACTOR = 0.01
"""obc_temp: engineering degC = raw * 0.01."""

BATTERY_TEMP_FACTOR = 0.01
"""battery_temp: engineering degC = raw * 0.01."""

RW_SPEED_FACTOR = 1.0
"""reaction_wheel_speed: engineering RPM = raw * 1."""


class SpacecraftMode(IntEnum):
    """spacecraft_mode enum (uint8)."""

    SAFE = 0
    NOMINAL = 1
    PAYLOAD = 2


@dataclass(frozen=True)
class HkParameters:
    """Raw-count HK parameter values (the encoded-on-the-wire integers)."""

    battery_voltage: int  # uint16
    battery_current: int  # uint16
    obc_temp: int  # int16
    battery_temp: int  # int16
    reaction_wheel_speed: int  # int16
    spacecraft_mode: SpacecraftMode  # uint8

    def encode_user_data(self) -> bytes:
        """Encode the HK user-data fields (structureId + parameters).

        Returns the 12-octet user-data block that follows the PUS secondary
        header. Raises :class:`struct.error` if a raw value is out of range for
        its field width (a programming error — dynamics/anomalies must clamp).
        """
        return struct.pack(
            HK_USER_DATA_FORMAT,
            STRUCTURE_ID,
            self.battery_voltage,
            self.battery_current,
            self.obc_temp,
            self.battery_temp,
            self.reaction_wheel_speed,
            int(self.spacecraft_mode),
        )

    @classmethod
    def decode_user_data(cls, data: bytes) -> HkParameters:
        """Decode the HK user-data block (after the PUS secondary header).

        Raises:
            ValueError: if ``structureId`` is not the expected value, or
                ``spacecraft_mode`` is not a valid enum member.
        """
        (
            structure_id,
            battery_voltage,
            battery_current,
            obc_temp,
            battery_temp,
            reaction_wheel_speed,
            spacecraft_mode,
        ) = struct.unpack_from(HK_USER_DATA_FORMAT, data, 0)
        if structure_id != STRUCTURE_ID:
            raise ValueError(f"unexpected structureId: {structure_id} (want {STRUCTURE_ID})")
        return cls(
            battery_voltage=battery_voltage,
            battery_current=battery_current,
            obc_temp=obc_temp,
            battery_temp=battery_temp,
            reaction_wheel_speed=reaction_wheel_speed,
            spacecraft_mode=SpacecraftMode(spacecraft_mode),
        )

    # --- documented raw -> engineering conversions ---------------------------

    def battery_voltage_eng(self) -> float:
        """Engineering battery voltage in volts."""
        return self.battery_voltage * VOLTAGE_FACTOR

    def battery_current_eng(self) -> float:
        """Engineering battery current in amperes."""
        return self.battery_current * CURRENT_FACTOR

    def obc_temp_eng(self) -> float:
        """Engineering OBC temperature in degrees Celsius."""
        return self.obc_temp * OBC_TEMP_FACTOR

    def battery_temp_eng(self) -> float:
        """Engineering battery temperature in degrees Celsius."""
        return self.battery_temp * BATTERY_TEMP_FACTOR

    def reaction_wheel_speed_eng(self) -> float:
        """Engineering reaction-wheel speed in RPM."""
        return self.reaction_wheel_speed * RW_SPEED_FACTOR


def build_hk_packet(
    params: HkParameters,
    seq_counter: SequenceCounter,
    msg_counter: MessageTypeCounter,
) -> bytes:
    """Build a complete HK (TM[3,25]) CCSDS/PUS packet.

    Args:
        params: the raw-count HK parameter values.
        seq_counter: per-APID CCSDS sequence counter (advanced for APID_HK).
        msg_counter: per-service PUS message type counter (advanced for service 3).

    Returns:
        A 25-octet ``bytes`` packet (1 UDP datagram).
    """
    user_data = params.encode_user_data()
    sec_header = PusTmSecondaryHeader(
        service_type=pus.SERVICE_HK,
        message_subtype=pus.SUBTYPE_HK_PARAM_REPORT,
        message_type_counter=msg_counter.next(pus.SERVICE_HK),
    ).pack()
    data_field = sec_header + user_data
    primary = build_primary_header(
        apid=APID_HK,
        sequence_count=seq_counter.next(APID_HK),
        data_field_len=len(data_field),
    ).pack()
    return primary + data_field


@dataclass(frozen=True)
class DecodedHkPacket:
    """A fully decoded HK packet (for tests / verification)."""

    secondary_header: PusTmSecondaryHeader
    parameters: HkParameters


def decode_hk_packet(packet: bytes) -> DecodedHkPacket:
    """Decode an HK packet's data field (after the primary header).

    Does not re-validate the primary header (use :func:`sgs_sim.ccsds.PrimaryHeader.unpack`
    for that); this decodes the PUS secondary header + HK user data.

    Raises:
        ValueError: if the packet is too short or the structure id is wrong.
    """
    if len(packet) < HK_PACKET_LEN:
        raise ValueError(f"HK packet too short: {len(packet)} < {HK_PACKET_LEN}")
    data_field = packet[6:]
    sec_header = PusTmSecondaryHeader.unpack(data_field)
    params = HkParameters.decode_user_data(data_field[pus.SECONDARY_HEADER_LEN :])
    return DecodedHkPacket(secondary_header=sec_header, parameters=params)
