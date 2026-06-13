"""PUS service-1 command-verification ACK packets (FOS / Epic 2 Phase 3).

SIMULATED telemetry. Builds the PUS service-1 *request verification* reports the
simulator returns after receiving a telecommand (see :mod:`sgs_sim.tc`). These
are CCSDS TM packets (spacecraft -> ground, UDP :10015) that Yamcs decommutates
to drive the command's verification chain.

ACK packet layout (big-endian), CCSDS 133.0-B-2 + ECSS-E-ST-70-41C::

    [ CCSDS primary header  : 6 octets ]   type=0 (TM), secHdrFlag=1, APID=102
    [ PUS-C TM secondary header : 7 octets ] service=1, subtype=1/7/2/8
    [ requestId : 4 octets ]               echoes the verified TC's first 4 octets

The ``requestId`` is the verified TC's *packet id* + *packet sequence control*
(its first 4 octets), per ECSS-E-ST-70-41C service 1. Yamcs correlates an ACK to
its command by matching this id against the command's CCSDS sequence count.

Subtypes used:

    1  acceptance success   (TM[1,1])
    2  acceptance failure   (TM[1,2])
    7  completion success   (TM[1,7])
    8  completion failure   (TM[1,8])
"""

from __future__ import annotations

from sgs_sim import pus
from sgs_sim.ccsds import APID_VERIFICATION, SequenceCounter, build_primary_header
from sgs_sim.pus import MessageTypeCounter, PusTmSecondaryHeader
from sgs_sim.tc import REQUEST_ID_LEN

#: Octets in a service-1 ACK packet = primary(6) + PUS-C TM secondary(7) + requestId(4).
ACK_PACKET_LEN = 6 + pus.SECONDARY_HEADER_LEN + REQUEST_ID_LEN  # 17


def build_ack_packet(
    *,
    subtype: int,
    request_id: bytes,
    seq_counter: SequenceCounter,
    msg_counter: MessageTypeCounter,
) -> bytes:
    """Build a PUS service-1 verification ACK packet (APID 102, 17 octets).

    Args:
        subtype: PUS service-1 subtype — one of SUBTYPE_ACCEPTANCE_SUCCESS (1),
            SUBTYPE_ACCEPTANCE_FAILURE (2), SUBTYPE_COMPLETION_SUCCESS (7),
            SUBTYPE_COMPLETION_FAILURE (8).
        request_id: the verified TC's 4-octet request id (echoed back).
        seq_counter: per-APID CCSDS sequence counter (advanced for APID 102).
        msg_counter: per-service PUS message type counter (advanced for service 1).

    Raises:
        ValueError: if ``request_id`` is not exactly 4 octets.
    """
    if len(request_id) != REQUEST_ID_LEN:
        raise ValueError(f"request_id must be {REQUEST_ID_LEN} octets, got {len(request_id)}")

    sec_header = PusTmSecondaryHeader(
        service_type=pus.SERVICE_VERIFICATION,
        message_subtype=subtype,
        message_type_counter=msg_counter.next(pus.SERVICE_VERIFICATION),
    ).pack()
    data_field = sec_header + bytes(request_id)
    primary = build_primary_header(
        apid=APID_VERIFICATION,
        sequence_count=seq_counter.next(APID_VERIFICATION),
        data_field_len=len(data_field),
    ).pack()
    return primary + data_field


def build_acceptance_success(
    request_id: bytes, seq_counter: SequenceCounter, msg_counter: MessageTypeCounter
) -> bytes:
    """TM[1,1] — acceptance success for the TC with ``request_id``."""
    return build_ack_packet(
        subtype=pus.SUBTYPE_ACCEPTANCE_SUCCESS,
        request_id=request_id,
        seq_counter=seq_counter,
        msg_counter=msg_counter,
    )


def build_acceptance_failure(
    request_id: bytes, seq_counter: SequenceCounter, msg_counter: MessageTypeCounter
) -> bytes:
    """TM[1,2] — acceptance failure for the TC with ``request_id``."""
    return build_ack_packet(
        subtype=pus.SUBTYPE_ACCEPTANCE_FAILURE,
        request_id=request_id,
        seq_counter=seq_counter,
        msg_counter=msg_counter,
    )


def build_completion_success(
    request_id: bytes, seq_counter: SequenceCounter, msg_counter: MessageTypeCounter
) -> bytes:
    """TM[1,7] — completion success for the TC with ``request_id``."""
    return build_ack_packet(
        subtype=pus.SUBTYPE_COMPLETION_SUCCESS,
        request_id=request_id,
        seq_counter=seq_counter,
        msg_counter=msg_counter,
    )


def build_completion_failure(
    request_id: bytes, seq_counter: SequenceCounter, msg_counter: MessageTypeCounter
) -> bytes:
    """TM[1,8] — completion failure for the TC with ``request_id``."""
    return build_ack_packet(
        subtype=pus.SUBTYPE_COMPLETION_FAILURE,
        request_id=request_id,
        seq_counter=seq_counter,
        msg_counter=msg_counter,
    )
