"""Shared time service (Epic 3, Phase 3) — OBT↔UTC correlation.

Re-exports the time-correlation surface so both segments and the operator surface
stamp/compare against one UTC base. See :mod:`sgs_shared.time_service.correlation`.
"""

from __future__ import annotations

from sgs_shared.time_service.correlation import (
    MISSION_EPOCH_UTC,
    TimeCorrelation,
    default_correlation,
    obt_to_utc,
    utc_to_obt,
)

__all__ = [
    "MISSION_EPOCH_UTC",
    "TimeCorrelation",
    "default_correlation",
    "obt_to_utc",
    "utc_to_obt",
]
