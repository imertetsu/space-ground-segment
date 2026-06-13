"""Unit tests for validation statistics (REQ-VAL-02)."""

from __future__ import annotations

import math

import numpy as np

from pdgs.config.processing import ValidationConfig
from pdgs.validation.colocation import MatchupSet
from pdgs.validation.stats import compute_stats


def _matchups(derived: list[float], reference: list[float]) -> MatchupSet:
    n = len(derived)
    return MatchupSet(
        derived_k=np.array(derived, dtype=np.float64),
        reference_k=np.array(reference, dtype=np.float64),
        latitudes=np.zeros(n, dtype=np.float64),
        longitudes=np.zeros(n, dtype=np.float64),
    )


def test_known_bias_and_rmse() -> None:
    # diffs = +1, +1, +1, +1  -> bias 1.0, rmse 1.0, std 0.0
    matchups = _matchups([291.0, 292.0, 293.0, 294.0], [290.0, 291.0, 292.0, 293.0])
    stats = compute_stats(matchups, ValidationConfig())
    assert stats.match_count == 4
    assert math.isclose(stats.bias_k, 1.0)
    assert math.isclose(stats.rmse_k, 1.0)
    assert math.isclose(stats.std_k, 0.0, abs_tol=1e-12)


def test_known_mixed_diffs() -> None:
    # diffs = +2, -2 -> bias 0, rmse 2, std 2
    matchups = _matchups([292.0, 288.0], [290.0, 290.0])
    stats = compute_stats(matchups, ValidationConfig())
    assert math.isclose(stats.bias_k, 0.0, abs_tol=1e-12)
    assert math.isclose(stats.rmse_k, 2.0)
    assert math.isclose(stats.std_k, 2.0)


def test_pct_within_tolerance() -> None:
    # diffs: 0.5, 1.5, 2.5, 3.0 ; tolerance 2.0 -> 2 of 4 within = 50%
    matchups = _matchups([290.5, 291.5, 292.5, 293.0], [290.0, 290.0, 290.0, 290.0])
    stats = compute_stats(matchups, ValidationConfig(tolerance_k=2.0))
    assert math.isclose(stats.pct_within_tol, 50.0)
    assert stats.tolerance_k == 2.0


def test_within_tolerance_boundary_inclusive() -> None:
    # diff exactly == tolerance counts as within.
    matchups = _matchups([292.0], [290.0])
    stats = compute_stats(matchups, ValidationConfig(tolerance_k=2.0))
    assert math.isclose(stats.pct_within_tol, 100.0)


def test_empty_matchups_gives_nan_stats() -> None:
    empty = MatchupSet(
        derived_k=np.empty(0, dtype=np.float64),
        reference_k=np.empty(0, dtype=np.float64),
        latitudes=np.empty(0, dtype=np.float64),
        longitudes=np.empty(0, dtype=np.float64),
    )
    stats = compute_stats(empty, ValidationConfig())
    assert stats.match_count == 0
    assert math.isnan(stats.bias_k)
    assert math.isnan(stats.rmse_k)
    assert math.isnan(stats.pct_within_tol)
