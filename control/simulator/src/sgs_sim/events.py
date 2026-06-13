"""PUS-5 event report generation + the frozen eventId catalogue.

SIMULATED telemetry. Generates PUS service-5 event reports on threshold crossings
and mode changes. Severity selects the message subtype (TM[5,1..4]); the
``eventId`` catalogue below is part of the FROZEN Phase-1 contract (see
``PACKET_FORMAT.md``).

EVENT packet data field (after the PUS-C secondary header, big-endian)::

    [ eventId : uint16 ]
    [ context : int16  ]   the offending raw value, or 0

EventId catalogue (frozen):

    1  EVT_BATTERY_UNDERVOLTAGE   battery_voltage below its soft_min   subtype 3 (medium)
    2  EVT_OBC_OVERTEMP           obc_temp above its soft_max          subtype 4 (high)
    3  EVT_RW_OVERSPEED           reaction_wheel_speed above soft_max  subtype 3 (medium)
    4  EVT_MODE_CHANGE            spacecraft_mode changed              subtype 1 (info)
    5  EVT_MODE_SAFE             spacecraft entered SAFE mode          subtype 2 (low)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from sgs_sim import pus
from sgs_sim.ccsds import APID_EVENT, SequenceCounter, build_primary_header
from sgs_sim.pus import MessageTypeCounter, PusTmSecondaryHeader

#: ``struct`` format for the EVENT user data: eventId(uint16) + context(int16).
EVENT_USER_DATA_FORMAT = ">Hh"

EVENT_USER_DATA_LEN = struct.calcsize(EVENT_USER_DATA_FORMAT)
"""Octets in the EVENT user data = 4."""

EVENT_DATA_FIELD_LEN = pus.SECONDARY_HEADER_LEN + EVENT_USER_DATA_LEN
"""Octets in the EVENT packet data field (secondary header + user data) = 11."""

EVENT_PACKET_LEN = 6 + EVENT_DATA_FIELD_LEN
"""Total octets in an EVENT packet = 17."""

#: int16 range used to clamp the ``context`` value defensively.
_CONTEXT_MIN = -0x8000
_CONTEXT_MAX = 0x7FFF


class EventId(IntEnum):
    """Frozen eventId catalogue (uint16)."""

    BATTERY_UNDERVOLTAGE = 1
    OBC_OVERTEMP = 2
    RW_OVERSPEED = 3
    MODE_CHANGE = 4
    MODE_SAFE = 5


#: eventId -> PUS service-5 message subtype (severity), frozen.
EVENT_SEVERITY: dict[EventId, int] = {
    EventId.BATTERY_UNDERVOLTAGE: pus.SUBTYPE_EVENT_MEDIUM,
    EventId.OBC_OVERTEMP: pus.SUBTYPE_EVENT_HIGH,
    EventId.RW_OVERSPEED: pus.SUBTYPE_EVENT_MEDIUM,
    EventId.MODE_CHANGE: pus.SUBTYPE_EVENT_INFO,
    EventId.MODE_SAFE: pus.SUBTYPE_EVENT_LOW,
}


@dataclass(frozen=True)
class Event:
    """A pending event to emit (eventId + offending raw context value)."""

    event_id: EventId
    context: int = 0

    @property
    def subtype(self) -> int:
        """The PUS service-5 message subtype (severity) for this event."""
        return EVENT_SEVERITY[self.event_id]


def _clamp_context(context: int) -> int:
    if context < _CONTEXT_MIN:
        return _CONTEXT_MIN
    if context > _CONTEXT_MAX:
        return _CONTEXT_MAX
    return context


def build_event_packet(
    event: Event,
    seq_counter: SequenceCounter,
    msg_counter: MessageTypeCounter,
) -> bytes:
    """Build a complete PUS service-5 event-report CCSDS packet (17 octets)."""
    user_data = struct.pack(
        EVENT_USER_DATA_FORMAT, int(event.event_id), _clamp_context(event.context)
    )
    sec_header = PusTmSecondaryHeader(
        service_type=pus.SERVICE_EVENT,
        message_subtype=event.subtype,
        message_type_counter=msg_counter.next(pus.SERVICE_EVENT),
    ).pack()
    data_field = sec_header + user_data
    primary = build_primary_header(
        apid=APID_EVENT,
        sequence_count=seq_counter.next(APID_EVENT),
        data_field_len=len(data_field),
    ).pack()
    return primary + data_field


@dataclass(frozen=True)
class DecodedEventPacket:
    """A fully decoded EVENT packet (for tests / verification)."""

    secondary_header: PusTmSecondaryHeader
    event_id: int
    context: int


def decode_event_packet(packet: bytes) -> DecodedEventPacket:
    """Decode an EVENT packet's data field (after the primary header).

    Raises:
        ValueError: if the packet is too short.
    """
    if len(packet) < EVENT_PACKET_LEN:
        raise ValueError(f"EVENT packet too short: {len(packet)} < {EVENT_PACKET_LEN}")
    data_field = packet[6:]
    sec_header = PusTmSecondaryHeader.unpack(data_field)
    event_id, context = struct.unpack_from(
        EVENT_USER_DATA_FORMAT, data_field, pus.SECONDARY_HEADER_LEN
    )
    return DecodedEventPacket(secondary_header=sec_header, event_id=event_id, context=context)
