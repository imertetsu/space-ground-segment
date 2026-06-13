"""OBT↔UTC correlation — the shared time base (Epic 3, Phase 3, REQ-INT-01).

Both halves of the ground segment must agree on time so a payload product and a
control telemetry reference can be ordered and compared on ONE base. That base is
**UTC** (timezone-aware, ISO-8601): payload products already carry UTC, and control
telemetry **references** carry UTC (the bridge's ingest/trigger times). This module
adds the missing piece — turning a spacecraft **on-board time (OBT)** into that same
UTC base, and back.

The correlation is the standard linear model used by a PUS service-9 time report::

    utc = utc_at_epoch + rate * (obt - obt_epoch)

where ``(obt_epoch, utc_at_epoch)`` is one correlation pair and ``rate`` is UTC
seconds per OBT second (``1.0`` for an ideal clock; a value off 1.0 models on-board
clock drift).

DOCUMENTED SIMPLIFICATION (carried from the operations guide "Time correlation
(PUS-9)"): in this portfolio the simulator does **not** emit a PUS time field and
Yamcs stamps packet time from its own wall clock, so there is no live service-9
report to derive the pair from. :func:`default_correlation` therefore returns a
**seeded** pair (OBT 0 s at a fixed mission epoch, ``rate=1.0``). This is a clearly
labelled seed — NOT an operational time-correlation service. Callers that have a
real correlation pair (e.g. from a future live PUS-9 report) pass their own
:class:`TimeCorrelation`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Fixed mission reference epoch for the SEEDED correlation (OBT 0 s ↔ this UTC).
# A portfolio mission reference, not a real spacecraft epoch (documented simplification).
MISSION_EPOCH_UTC = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


def _as_utc(value: datetime) -> datetime:
    """Normalise a datetime to timezone-aware UTC (assume UTC if naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class TimeCorrelation:
    """A linear OBT↔UTC correlation pair (the shared time base mapping).

    - ``obt_epoch``: on-board time (seconds) at the reference point.
    - ``utc_at_epoch``: the UTC instant corresponding to ``obt_epoch`` (tz-aware UTC).
    - ``rate``: UTC seconds per OBT second. ``1.0`` is an ideal clock; values off
      1.0 model on-board clock drift. Must be non-zero.

    Frozen: a correlation describes a fixed relationship; derive a new one rather
    than mutating.
    """

    obt_epoch: float
    utc_at_epoch: datetime
    rate: float = 1.0

    def __post_init__(self) -> None:
        if self.rate == 0:
            raise ValueError("TimeCorrelation.rate must be non-zero")


def default_correlation() -> TimeCorrelation:
    """Return the SEEDED correlation: OBT 0 s at :data:`MISSION_EPOCH_UTC`, rate 1.0.

    A documented simplification (no live PUS-9 report in this portfolio); see the
    module docstring. Use a real :class:`TimeCorrelation` when one is available.
    """
    return TimeCorrelation(obt_epoch=0.0, utc_at_epoch=MISSION_EPOCH_UTC, rate=1.0)


def obt_to_utc(obt: float, corr: TimeCorrelation | None = None) -> datetime:
    """Convert an on-board time ``obt`` (seconds) to UTC on the shared base.

    Uses ``corr`` (defaulting to :func:`default_correlation`). Returns a tz-aware
    UTC datetime: ``utc_at_epoch + rate * (obt - obt_epoch)`` seconds.
    """
    c = corr if corr is not None else default_correlation()
    return _as_utc(c.utc_at_epoch) + timedelta(seconds=c.rate * (obt - c.obt_epoch))


def utc_to_obt(utc: datetime, corr: TimeCorrelation | None = None) -> float:
    """Convert a UTC instant to on-board time (seconds) — the inverse of :func:`obt_to_utc`.

    Uses ``corr`` (defaulting to :func:`default_correlation`). Naive datetimes are
    assumed UTC.
    """
    c = corr if corr is not None else default_correlation()
    delta = (_as_utc(utc) - _as_utc(c.utc_at_epoch)).total_seconds()
    return c.obt_epoch + delta / c.rate
