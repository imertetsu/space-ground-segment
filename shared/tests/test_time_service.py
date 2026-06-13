"""Unit tests (no DB) for the shared OBT↔UTC time service (REQ-INT-01)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sgs_shared.time_service import (
    MISSION_EPOCH_UTC,
    TimeCorrelation,
    obt_to_utc,
    utc_to_obt,
)


def test_default_correlation_maps_obt_zero_to_mission_epoch() -> None:
    assert obt_to_utc(0.0) == MISSION_EPOCH_UTC


def test_default_correlation_advances_one_second_per_obt_second() -> None:
    assert obt_to_utc(3600.0) == datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)


def test_round_trip_obt_utc_obt() -> None:
    for obt in (0.0, 1.0, 1234.5, 86_400.0, 1_000_000.25):
        assert utc_to_obt(obt_to_utc(obt)) == pytest.approx(obt)


def test_round_trip_utc_obt_utc() -> None:
    utc = datetime(2026, 6, 13, 9, 30, 15, tzinfo=UTC)
    assert obt_to_utc(utc_to_obt(utc)) == utc


def test_custom_correlation_pair() -> None:
    corr = TimeCorrelation(
        obt_epoch=100.0,
        utc_at_epoch=datetime(2026, 6, 13, 0, 0, 0, tzinfo=UTC),
        rate=1.0,
    )
    assert obt_to_utc(160.0, corr) == datetime(2026, 6, 13, 0, 1, 0, tzinfo=UTC)
    assert utc_to_obt(datetime(2026, 6, 13, 0, 1, 0, tzinfo=UTC), corr) == pytest.approx(160.0)


def test_rate_models_clock_drift() -> None:
    # rate = 1.0001 UTC s per OBT s: 10_000 OBT s elapse 10_001 UTC s.
    corr = TimeCorrelation(obt_epoch=0.0, utc_at_epoch=MISSION_EPOCH_UTC, rate=1.0001)
    utc = obt_to_utc(10_000.0, corr)
    assert (utc - MISSION_EPOCH_UTC).total_seconds() == pytest.approx(10_001.0)
    assert utc_to_obt(utc, corr) == pytest.approx(10_000.0)


def test_naive_utc_assumed_utc() -> None:
    naive = datetime(2026, 1, 1, 0, 0, 0)  # intentional naive input (assumed UTC)
    assert utc_to_obt(naive) == pytest.approx(0.0)


def test_zero_rate_rejected() -> None:
    with pytest.raises(ValueError, match="rate must be non-zero"):
        TimeCorrelation(obt_epoch=0.0, utc_at_epoch=MISSION_EPOCH_UTC, rate=0.0)
