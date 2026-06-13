"""Tests for PUS-5 event generation + the eventId catalogue."""

from __future__ import annotations

from collections.abc import Callable

from sgs_sim import pus
from sgs_sim.anomalies import Model
from sgs_sim.ccsds import APID_EVENT, PrimaryHeader, SequenceCounter
from sgs_sim.config import AnomalyConfig, SimConfig
from sgs_sim.events import (
    EVENT_PACKET_LEN,
    Event,
    EventId,
    build_event_packet,
    decode_event_packet,
)
from sgs_sim.pus import MessageTypeCounter

MAX_TICKS = 50

WithAnomaly = Callable[..., SimConfig]


def _collect_event_ids(model: Model, ticks: int) -> list[EventId]:
    ids: list[EventId] = []
    for _ in range(ticks):
        ids += [e.event_id for e in model.step().events]
    return ids


def test_event_packet_round_trip() -> None:
    event = Event(EventId.OBC_OVERTEMP, context=5123)
    packet = build_event_packet(event, SequenceCounter(), MessageTypeCounter())
    assert len(packet) == EVENT_PACKET_LEN == 17

    ph = PrimaryHeader.unpack(packet)
    assert ph.apid == APID_EVENT
    assert ph.secondary_header_flag == 1
    assert ph.packet_data_length == 10  # 11 - 1

    decoded = decode_event_packet(packet)
    assert decoded.secondary_header.service_type == pus.SERVICE_EVENT
    assert decoded.secondary_header.message_subtype == pus.SUBTYPE_EVENT_HIGH
    assert decoded.event_id == EventId.OBC_OVERTEMP
    assert decoded.context == 5123


def test_severity_subtypes_per_event() -> None:
    cases = {
        EventId.BATTERY_UNDERVOLTAGE: pus.SUBTYPE_EVENT_MEDIUM,
        EventId.OBC_OVERTEMP: pus.SUBTYPE_EVENT_HIGH,
        EventId.RW_OVERSPEED: pus.SUBTYPE_EVENT_MEDIUM,
        EventId.MODE_CHANGE: pus.SUBTYPE_EVENT_INFO,
        EventId.MODE_SAFE: pus.SUBTYPE_EVENT_LOW,
    }
    for event_id, subtype in cases.items():
        assert Event(event_id).subtype == subtype


def test_battery_undervoltage_emits_event(
    default_config: SimConfig, with_anomaly: WithAnomaly
) -> None:
    cfg = with_anomaly(default_config, battery_undervoltage=AnomalyConfig(enabled=True, rate=80))
    ids = _collect_event_ids(Model(cfg), MAX_TICKS)
    assert EventId.BATTERY_UNDERVOLTAGE in ids


def test_obc_overtemp_emits_high_severity(
    default_config: SimConfig, with_anomaly: WithAnomaly
) -> None:
    cfg = with_anomaly(default_config, obc_overtemp=AnomalyConfig(enabled=True, rate=200))
    model = Model(cfg)
    event_packet: bytes | None = None
    seq, msg = SequenceCounter(), MessageTypeCounter()
    for _ in range(MAX_TICKS):
        for e in model.step().events:
            if e.event_id == EventId.OBC_OVERTEMP:
                event_packet = build_event_packet(e, seq, msg)
                break
        if event_packet is not None:
            break
    assert event_packet is not None
    decoded = decode_event_packet(event_packet)
    assert decoded.secondary_header.message_subtype == pus.SUBTYPE_EVENT_HIGH
    assert decoded.event_id == EventId.OBC_OVERTEMP
    # context carries the offending raw value (above soft_max).
    assert decoded.context > default_config.parameters["obc_temp"].soft_max


def test_mode_change_emits_event(default_config: SimConfig, with_anomaly: WithAnomaly) -> None:
    cfg = with_anomaly(default_config, mode_to_safe=AnomalyConfig(enabled=True, rate=0))
    ids = _collect_event_ids(Model(cfg), 1)
    assert EventId.MODE_CHANGE in ids
    assert EventId.MODE_SAFE in ids


def test_event_is_edge_triggered_not_repeated(
    default_config: SimConfig, with_anomaly: WithAnomaly
) -> None:
    # mode_to_safe holds SAFE every tick, but MODE_CHANGE must fire only once.
    cfg = with_anomaly(default_config, mode_to_safe=AnomalyConfig(enabled=True, rate=0))
    ids = _collect_event_ids(Model(cfg), MAX_TICKS)
    assert ids.count(EventId.MODE_CHANGE) == 1
    assert ids.count(EventId.MODE_SAFE) == 1


def test_nominal_stream_emits_no_events(default_config: SimConfig) -> None:
    ids = _collect_event_ids(Model(default_config), MAX_TICKS)
    assert ids == []
