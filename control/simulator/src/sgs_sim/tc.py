"""Telecommand (TC) parsing + validation (FOS / Epic 2 Phase 3).

SIMULATED telecommanding. This module parses a received CCSDS/PUS-C telecommand
(ground -> spacecraft) and validates it against the FROZEN Phase-3 command set.
The simulator's TC receiver (:mod:`sgs_sim.sender`) feeds raw UDP datagrams here;
on a valid TC it applies the command and the verification layer
(:mod:`sgs_sim.verification`) builds the PUS service-1 ACKs.

TC packet layout (big-endian), CCSDS 133.0-B-2 + ECSS-E-ST-70-41C::

    [ CCSDS primary header  : 6 octets ]   type=1 (TC), secHdrFlag=1, APID=200
    [ PUS-C TC secondary header : 5 octets ] (see :class:`sgs_sim.pus.PusTcSecondaryHeader`)
    [ application data (args) : 0..n octets ]

The **request id** (per ECSS-E-ST-70-41C service 1) is the TC's first 4 octets =
CCSDS *packet id* (word0) + *packet sequence control* (word1). The verification
ACKs echo it back so the ground (Yamcs) can correlate the chain.

Command set (private PUS service 132 — ECSS reserves service types >= 128 for
mission-private services; documented as private/custom):

    SET_MODE  TC[132,1]  arg mode (uint8 enum: 0=SAFE/1=NOMINAL/2=PAYLOAD), 0..2
    PING      TC[132,2]  no args
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sgs_sim import pus
from sgs_sim.ccsds import APID_TC, PRIMARY_HEADER_LEN, TYPE_TC, PrimaryHeader
from sgs_sim.hk import SpacecraftMode
from sgs_sim.pus import PusTcSecondaryHeader

REQUEST_ID_LEN = 4
"""Octets in the TC request id (CCSDS packet id + packet sequence control)."""

#: Offset of the application data (args) inside a TC packet.
TC_ARGS_OFFSET = PRIMARY_HEADER_LEN + pus.TC_SECONDARY_HEADER_LEN  # 6 + 5 = 11

#: Valid spacecraft_mode values for SET_MODE (0=SAFE, 1=NOMINAL, 2=PAYLOAD).
_VALID_MODES = {int(m) for m in SpacecraftMode}


class TcRejectReason(Enum):
    """Why a TC failed validation (drives the acceptance-failure ACK)."""

    TOO_SHORT = "packet too short"
    BAD_PACKET_TYPE = "not a TC (CCSDS packet type != 1)"
    BAD_APID = "unexpected APID (not the TC APID)"
    UNKNOWN_SERVICE = "unknown PUS service"
    UNKNOWN_SUBTYPE = "unknown command subtype"
    MISSING_ARG = "required argument missing"
    ARG_OUT_OF_RANGE = "argument out of range"


@dataclass(frozen=True)
class ParsedTc:
    """A structurally-parsed telecommand (headers + request id + raw args).

    Structural parsing succeeds as long as the primary + TC secondary headers
    are present; semantic validity (known command, in-range args) is decided by
    :func:`validate`.
    """

    primary: PrimaryHeader
    secondary: PusTcSecondaryHeader
    request_id: bytes
    """The TC's first 4 octets (packet id + packet sequence control)."""
    args: bytes
    """Raw application-data octets after the TC secondary header."""

    @property
    def service_type(self) -> int:
        return self.secondary.service_type

    @property
    def message_subtype(self) -> int:
        return self.secondary.message_subtype


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of validating a :class:`ParsedTc`."""

    ok: bool
    reason: TcRejectReason | None = None
    detail: str = ""
    mode: SpacecraftMode | None = None
    """For a valid SET_MODE: the requested target mode."""


class TcParseError(ValueError):
    """Raised when a datagram cannot be structurally parsed as a TC."""

    def __init__(self, reason: TcRejectReason, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.value}: {detail}" if detail else reason.value)


def extract_request_id(packet: bytes) -> bytes:
    """Return the TC request id = the first 4 octets of ``packet``.

    Raises:
        TcParseError: if ``packet`` is shorter than 4 octets.
    """
    if len(packet) < REQUEST_ID_LEN:
        raise TcParseError(TcRejectReason.TOO_SHORT, f"{len(packet)} < {REQUEST_ID_LEN}")
    return bytes(packet[:REQUEST_ID_LEN])


def parse(packet: bytes) -> ParsedTc:
    """Structurally parse a received datagram as a CCSDS/PUS-C telecommand.

    Validates only the framing (lengths, packet type = TC, expected APID). The
    command set / argument ranges are checked by :func:`validate`.

    Raises:
        TcParseError: if the datagram is too short or is not a TC for this FOS.
    """
    if len(packet) < TC_ARGS_OFFSET:
        raise TcParseError(TcRejectReason.TOO_SHORT, f"{len(packet)} < {TC_ARGS_OFFSET} (headers)")
    primary = PrimaryHeader.unpack(packet)
    if primary.packet_type != TYPE_TC:
        raise TcParseError(TcRejectReason.BAD_PACKET_TYPE, f"packet_type={primary.packet_type}")
    if primary.apid != APID_TC:
        raise TcParseError(TcRejectReason.BAD_APID, f"apid={primary.apid}")

    secondary = PusTcSecondaryHeader.unpack(packet[PRIMARY_HEADER_LEN:])
    request_id = bytes(packet[:REQUEST_ID_LEN])
    args = bytes(packet[TC_ARGS_OFFSET:])
    return ParsedTc(primary=primary, secondary=secondary, request_id=request_id, args=args)


def validate(tc: ParsedTc) -> ValidationResult:
    """Validate a parsed TC against the frozen command set.

    Returns a :class:`ValidationResult`; ``ok=False`` carries the
    :class:`TcRejectReason` that drives the acceptance-failure ACK.
    """
    if tc.service_type != pus.SERVICE_COMMAND:
        return ValidationResult(
            ok=False,
            reason=TcRejectReason.UNKNOWN_SERVICE,
            detail=f"service={tc.service_type}",
        )

    if tc.message_subtype == pus.SUBTYPE_CMD_SET_MODE:
        return _validate_set_mode(tc)
    if tc.message_subtype == pus.SUBTYPE_CMD_PING:
        # PING takes no arguments; tolerate trailing padding but require none.
        return ValidationResult(ok=True)

    return ValidationResult(
        ok=False,
        reason=TcRejectReason.UNKNOWN_SUBTYPE,
        detail=f"subtype={tc.message_subtype}",
    )


def _validate_set_mode(tc: ParsedTc) -> ValidationResult:
    if len(tc.args) < 1:
        return ValidationResult(
            ok=False, reason=TcRejectReason.MISSING_ARG, detail="SET_MODE needs 1 arg (mode)"
        )
    mode_raw = tc.args[0]
    if mode_raw not in _VALID_MODES:
        return ValidationResult(
            ok=False,
            reason=TcRejectReason.ARG_OUT_OF_RANGE,
            detail=f"mode={mode_raw} not in 0..2",
        )
    return ValidationResult(ok=True, mode=SpacecraftMode(mode_raw))


def build_tc_packet(
    *,
    subtype: int,
    sequence_count: int,
    args: bytes = b"",
    ack_flags: int = pus.ACK_FLAGS_ACCEPT_COMPLETE,
) -> bytes:
    """Build a complete TC packet (for tests / a TC sender).

    Mirrors the ground side: CCSDS TC primary header (type=1, APID=200) + PUS-C
    TC secondary header (service 132) + args. ``packetDataLength`` is set
    correctly here (in flight, Yamcs' postprocessor finalizes it + the seq count).

    Args:
        subtype: PUS message subtype (e.g. SUBTYPE_CMD_SET_MODE / SUBTYPE_CMD_PING).
        sequence_count: 14-bit CCSDS sequence count to embed.
        args: application data octets after the TC secondary header.
        ack_flags: 4-bit acknowledgement flags (default acceptance + completion).
    """
    secondary = PusTcSecondaryHeader(
        service_type=pus.SERVICE_COMMAND,
        message_subtype=subtype,
        ack_flags=ack_flags,
    ).pack()
    data_field = secondary + args
    primary = PrimaryHeader(
        version=0,
        packet_type=TYPE_TC,
        secondary_header_flag=1,
        apid=APID_TC,
        sequence_flags=0b11,
        sequence_count=sequence_count,
        packet_data_length=len(data_field) - 1,
    ).pack()
    return primary + data_field
