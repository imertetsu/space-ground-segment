"""PUS-C TM secondary header (ECSS-E-ST-70-41C).

SIMULATED telemetry framing. This module packs/unpacks the **PUS-C TM secondary
header** placed at the start of the CCSDS packet data field (after the 6-octet
primary header from :mod:`sgs_sim.ccsds`). It is the second half of the FROZEN
Phase-1 decode contract (see ``PACKET_FORMAT.md``).

Secondary header (7 octets, big-endian / network byte order), ECSS-E-ST-70-41C::

    octet0   : pusVersionNumber(4b)=0b0010 (PUS-C) | spacecraftTimeReferenceStatus(4b)=0
               -> always 0x20
    octet1   : serviceType (uint8)
    octet2   : messageSubtype (uint8)
    octet3-4 : messageTypeCounter (uint16, per-service)
    octet5-6 : destinationId (uint16) = 0 (ground)

DOCUMENTED SIMPLIFICATION: there is **no time field** in this secondary header.
ECSS-E-ST-70-41C allows an optional time field; we omit it because the Yamcs
``MyPacketPreprocessor`` ingests packets using wallclock (it does not parse a
secondary-header time). This keeps the frozen contract minimal and is recorded in
``PACKET_FORMAT.md`` and the ICD.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# --- Constants fixed by the contract (ECSS-E-ST-70-41C) ---------------------

SECONDARY_HEADER_LEN = 7
"""Octets in the PUS-C TM secondary header (this contract; no time field)."""

PUS_VERSION_C = 0b0010
"""PUS version number nibble: 0b0010 = PUS-C (value 2)."""

SPACECRAFT_TIME_REF_STATUS = 0
"""Spacecraft time reference status nibble (0 here)."""

PUS_HEADER_OCTET0 = (PUS_VERSION_C << 4) | SPACECRAFT_TIME_REF_STATUS
"""First octet of the PUS-C secondary header: 0x20."""

DESTINATION_ID_GROUND = 0
"""destinationId for ground (0)."""

# --- PUS service / subtype constants (the services this FOS uses) ------------

SERVICE_HK = 3
"""PUS service 3 — housekeeping."""

SUBTYPE_HK_PARAM_REPORT = 25
"""PUS service 3 subtype 25 — housekeeping parameter report (TM[3,25])."""

SERVICE_EVENT = 5
"""PUS service 5 — event reporting."""

# Event severity → message subtype (ECSS-E-ST-70-41C service 5 convention).
SUBTYPE_EVENT_INFO = 1
"""TM[5,1] — informative event report."""

SUBTYPE_EVENT_LOW = 2
"""TM[5,2] — low-severity anomaly event report."""

SUBTYPE_EVENT_MEDIUM = 3
"""TM[5,3] — medium-severity anomaly event report."""

SUBTYPE_EVENT_HIGH = 4
"""TM[5,4] — high-severity anomaly event report."""

# --- Service 1 — request verification (ECSS-E-ST-70-41C) ---------------------

SERVICE_VERIFICATION = 1
"""PUS service 1 — request (telecommand) verification."""

SUBTYPE_ACCEPTANCE_SUCCESS = 1
"""TM[1,1] — successful acceptance verification report."""

SUBTYPE_ACCEPTANCE_FAILURE = 2
"""TM[1,2] — failed acceptance verification report."""

SUBTYPE_COMPLETION_SUCCESS = 7
"""TM[1,7] — successful completion-of-execution verification report."""

SUBTYPE_COMPLETION_FAILURE = 8
"""TM[1,8] — failed completion-of-execution verification report."""

# --- Telecommanding (TC) — the private command service this FOS accepts -------

SERVICE_COMMAND = 132
"""Private/custom PUS service 132 — SGS spacecraft commanding.

ECSS-E-ST-70-41C reserves service types >= 128 for mission-private services; this
FOS uses 132 for its (SIMULATED) command set. Documented as private/custom.
"""

SUBTYPE_CMD_SET_MODE = 1
"""TC[132,1] — SET_MODE (arg: mode enum 0=SAFE/1=NOMINAL/2=PAYLOAD)."""

SUBTYPE_CMD_PING = 2
"""TC[132,2] — PING (no args)."""


@dataclass(frozen=True)
class PusTmSecondaryHeader:
    """Decoded PUS-C TM secondary header (no time field — see module docstring)."""

    service_type: int
    message_subtype: int
    message_type_counter: int
    destination_id: int = DESTINATION_ID_GROUND
    pus_version: int = PUS_VERSION_C
    time_ref_status: int = SPACECRAFT_TIME_REF_STATUS

    def pack(self) -> bytes:
        """Pack this secondary header into its 7 big-endian octets.

        Raises:
            ValueError: if any field is outside its width.
        """
        if not 0 <= self.pus_version <= 0xF:
            raise ValueError(f"pus_version out of range (4 bits): {self.pus_version}")
        if not 0 <= self.time_ref_status <= 0xF:
            raise ValueError(f"time_ref_status out of range (4 bits): {self.time_ref_status}")
        if not 0 <= self.service_type <= 0xFF:
            raise ValueError(f"service_type out of range (8 bits): {self.service_type}")
        if not 0 <= self.message_subtype <= 0xFF:
            raise ValueError(f"message_subtype out of range (8 bits): {self.message_subtype}")
        if not 0 <= self.message_type_counter <= 0xFFFF:
            raise ValueError(
                f"message_type_counter out of range (16 bits): {self.message_type_counter}"
            )
        if not 0 <= self.destination_id <= 0xFFFF:
            raise ValueError(f"destination_id out of range (16 bits): {self.destination_id}")

        octet0 = (self.pus_version << 4) | self.time_ref_status
        return struct.pack(
            ">BBBHH",
            octet0,
            self.service_type,
            self.message_subtype,
            self.message_type_counter,
            self.destination_id,
        )

    @classmethod
    def unpack(cls, data: bytes) -> PusTmSecondaryHeader:
        """Unpack the first 7 octets of ``data`` into a secondary header.

        Raises:
            ValueError: if ``data`` is shorter than 7 octets.
        """
        if len(data) < SECONDARY_HEADER_LEN:
            raise ValueError(f"need >= {SECONDARY_HEADER_LEN} octets, got {len(data)}")
        octet0, service_type, message_subtype, message_type_counter, destination_id = (
            struct.unpack_from(">BBBHH", data, 0)
        )
        return cls(
            service_type=service_type,
            message_subtype=message_subtype,
            message_type_counter=message_type_counter,
            destination_id=destination_id,
            pus_version=(octet0 >> 4) & 0xF,
            time_ref_status=octet0 & 0xF,
        )


# --- PUS-C TC secondary header (ECSS-E-ST-70-41C) ----------------------------

TC_SECONDARY_HEADER_LEN = 5
"""Octets in the PUS-C TC secondary header (this contract; no time field)."""

ACK_FLAG_ACCEPTANCE = 0b0001
"""Acknowledgement-flags bit: report on acceptance."""

ACK_FLAG_START = 0b0010
"""Acknowledgement-flags bit: report on start of execution."""

ACK_FLAG_PROGRESS = 0b0100
"""Acknowledgement-flags bit: report on progress of execution."""

ACK_FLAG_COMPLETION = 0b1000
"""Acknowledgement-flags bit: report on completion of execution."""

ACK_FLAGS_ACCEPT_COMPLETE = ACK_FLAG_ACCEPTANCE | ACK_FLAG_COMPLETION
"""Default acknowledgement flags for this FOS: acceptance + completion = 0b1001."""

SOURCE_ID_GROUND = 0
"""sourceId for the ground (origin of telecommands) = 0."""


@dataclass(frozen=True)
class PusTcSecondaryHeader:
    """Decoded PUS-C TC secondary header (5 octets; no time field).

    Layout (ECSS-E-ST-70-41C), big-endian::

        octet0   : pusVersionNumber(4b) | acknowledgementFlags(4b)
        octet1   : serviceType (uint8)
        octet2   : messageSubtype (uint8)
        octet3-4 : sourceId (uint16)

    DOCUMENTED SIMPLIFICATION: no time field (mirrors the TM secondary header).
    """

    service_type: int
    message_subtype: int
    ack_flags: int = ACK_FLAGS_ACCEPT_COMPLETE
    source_id: int = SOURCE_ID_GROUND
    pus_version: int = PUS_VERSION_C

    def pack(self) -> bytes:
        """Pack this TC secondary header into its 5 big-endian octets.

        Raises:
            ValueError: if any field is outside its width.
        """
        if not 0 <= self.pus_version <= 0xF:
            raise ValueError(f"pus_version out of range (4 bits): {self.pus_version}")
        if not 0 <= self.ack_flags <= 0xF:
            raise ValueError(f"ack_flags out of range (4 bits): {self.ack_flags}")
        if not 0 <= self.service_type <= 0xFF:
            raise ValueError(f"service_type out of range (8 bits): {self.service_type}")
        if not 0 <= self.message_subtype <= 0xFF:
            raise ValueError(f"message_subtype out of range (8 bits): {self.message_subtype}")
        if not 0 <= self.source_id <= 0xFFFF:
            raise ValueError(f"source_id out of range (16 bits): {self.source_id}")

        octet0 = (self.pus_version << 4) | self.ack_flags
        return struct.pack(
            ">BBBH",
            octet0,
            self.service_type,
            self.message_subtype,
            self.source_id,
        )

    @classmethod
    def unpack(cls, data: bytes) -> PusTcSecondaryHeader:
        """Unpack the first 5 octets of ``data`` into a TC secondary header.

        Raises:
            ValueError: if ``data`` is shorter than 5 octets.
        """
        if len(data) < TC_SECONDARY_HEADER_LEN:
            raise ValueError(f"need >= {TC_SECONDARY_HEADER_LEN} octets, got {len(data)}")
        octet0, service_type, message_subtype, source_id = struct.unpack_from(">BBBH", data, 0)
        return cls(
            service_type=service_type,
            message_subtype=message_subtype,
            ack_flags=octet0 & 0xF,
            source_id=source_id,
            pus_version=(octet0 >> 4) & 0xF,
        )


class MessageTypeCounter:
    """Per-service PUS message type counter (16-bit, wraps mod 65536)."""

    def __init__(self) -> None:
        self._counts: dict[int, int] = {}

    def next(self, service_type: int) -> int:
        """Return the current counter for ``service_type`` then advance it."""
        current = self._counts.get(service_type, 0)
        self._counts[service_type] = (current + 1) % 0x10000
        return current
