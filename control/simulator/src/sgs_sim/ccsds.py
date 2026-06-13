"""CCSDS Space Packet primary header (CCSDS 133.0-B-2).

SIMULATED telemetry framing. This module packs/unpacks the 6-octet CCSDS Space
Packet **primary header** used by every packet this simulator emits. It is the
first half of the FROZEN Phase-1 decode contract (see ``PACKET_FORMAT.md``); the
XTCE MDB (Phase 2) decodes against exactly this layout.

Primary header (6 octets, big-endian / network byte order), CCSDS 133.0-B-2 §4.1::

    word0 (uint16): version(3b) | type(1b) | secondaryHeaderFlag(1b) | APID(11b)
    word1 (uint16): sequenceFlags(2b) | sequenceCount(14b)
    word2 (uint16): packetDataLength = (octets in the packet data field) - 1

This simulator only emits TM (``type=0``) with a secondary header present
(``secondaryHeaderFlag=1``) and unsegmented standalone packets
(``sequenceFlags=0b11``).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# --- Constants fixed by the contract (CCSDS 133.0-B-2) ----------------------

PRIMARY_HEADER_LEN = 6
"""Octets in the CCSDS primary header (fixed by CCSDS 133.0-B-2)."""

VERSION_TM = 0b000
"""Packet Version Number for a CCSDS Space Packet."""

TYPE_TM = 0
"""Packet Type: 0 = telemetry (TM)."""

TYPE_TC = 1
"""Packet Type: 1 = telecommand (TC)."""

SEQ_FLAGS_UNSEGMENTED = 0b11
"""Sequence Flags: 0b11 = unsegmented, standalone packet."""

# Application Process Identifiers (APIDs) frozen in Phase 1.
APID_HK = 100
"""APID for housekeeping (PUS service 3) packets (0x064)."""

APID_EVENT = 101
"""APID for event report (PUS service 5) packets (0x065)."""

# APIDs frozen in Phase 3 (telecommanding).
APID_TC = 200
"""APID for telecommand (TC) packets sent ground->spacecraft (0x0C8)."""

APID_VERIFICATION = 102
"""APID for PUS service-1 command-verification ACK packets (TM, 0x066)."""

# Field widths / wrap values.
APID_MASK = 0x7FF
"""11-bit APID mask."""

SEQ_COUNT_MODULO = 0x4000
"""Packet Sequence Count is 14 bits → wraps mod 16384."""


@dataclass(frozen=True)
class PrimaryHeader:
    """Decoded CCSDS Space Packet primary header.

    All fields are stored as their logical integer values (not packed bits).
    """

    version: int
    packet_type: int
    secondary_header_flag: int
    apid: int
    sequence_flags: int
    sequence_count: int
    packet_data_length: int

    def pack(self) -> bytes:
        """Pack this header into its 6 big-endian octets.

        Raises:
            ValueError: if any field is outside its bit-width.
        """
        if not 0 <= self.version <= 0b111:
            raise ValueError(f"version out of range (3 bits): {self.version}")
        if self.packet_type not in (0, 1):
            raise ValueError(f"packet_type must be 0 or 1: {self.packet_type}")
        if self.secondary_header_flag not in (0, 1):
            raise ValueError(f"secondary_header_flag must be 0 or 1: {self.secondary_header_flag}")
        if not 0 <= self.apid <= APID_MASK:
            raise ValueError(f"apid out of range (11 bits): {self.apid}")
        if not 0 <= self.sequence_flags <= 0b11:
            raise ValueError(f"sequence_flags out of range (2 bits): {self.sequence_flags}")
        if not 0 <= self.sequence_count < SEQ_COUNT_MODULO:
            raise ValueError(f"sequence_count out of range (14 bits): {self.sequence_count}")
        if not 0 <= self.packet_data_length <= 0xFFFF:
            raise ValueError(
                f"packet_data_length out of range (16 bits): {self.packet_data_length}"
            )

        word0 = (
            (self.version << 13)
            | (self.packet_type << 12)
            | (self.secondary_header_flag << 11)
            | (self.apid & APID_MASK)
        )
        word1 = (self.sequence_flags << 14) | (self.sequence_count & (SEQ_COUNT_MODULO - 1))
        word2 = self.packet_data_length
        return struct.pack(">HHH", word0, word1, word2)

    @classmethod
    def unpack(cls, data: bytes) -> PrimaryHeader:
        """Unpack the first 6 octets of ``data`` into a :class:`PrimaryHeader`.

        Raises:
            ValueError: if ``data`` is shorter than 6 octets.
        """
        if len(data) < PRIMARY_HEADER_LEN:
            raise ValueError(f"need >= {PRIMARY_HEADER_LEN} octets, got {len(data)}")
        word0, word1, word2 = struct.unpack_from(">HHH", data, 0)
        return cls(
            version=(word0 >> 13) & 0b111,
            packet_type=(word0 >> 12) & 0b1,
            secondary_header_flag=(word0 >> 11) & 0b1,
            apid=word0 & APID_MASK,
            sequence_flags=(word1 >> 14) & 0b11,
            sequence_count=word1 & (SEQ_COUNT_MODULO - 1),
            packet_data_length=word2,
        )


def build_primary_header(apid: int, sequence_count: int, data_field_len: int) -> PrimaryHeader:
    """Build a TM primary header for an unsegmented packet with a secondary header.

    Args:
        apid: 11-bit Application Process Identifier.
        sequence_count: 14-bit per-APID sequence count.
        data_field_len: octets in the packet data field (secondary header + user
            data). ``packetDataLength`` is set to ``data_field_len - 1`` per
            CCSDS 133.0-B-2.

    Raises:
        ValueError: if ``data_field_len`` is < 1 (the data field must be
            non-empty for ``packetDataLength = len - 1`` to be valid).
    """
    if data_field_len < 1:
        raise ValueError(f"data_field_len must be >= 1, got {data_field_len}")
    return PrimaryHeader(
        version=VERSION_TM,
        packet_type=TYPE_TM,
        secondary_header_flag=1,
        apid=apid,
        sequence_flags=SEQ_FLAGS_UNSEGMENTED,
        sequence_count=sequence_count,
        packet_data_length=data_field_len - 1,
    )


class SequenceCounter:
    """Per-APID CCSDS packet sequence counter (14-bit, wraps mod 16384)."""

    def __init__(self) -> None:
        self._counts: dict[int, int] = {}

    def next(self, apid: int) -> int:
        """Return the current count for ``apid`` then advance it (wrapping)."""
        current = self._counts.get(apid, 0)
        self._counts[apid] = (current + 1) % SEQ_COUNT_MODULO
        return current
