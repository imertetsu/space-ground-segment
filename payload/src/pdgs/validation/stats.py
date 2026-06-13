"""Validation statistics from co-located matchups (REQ-VAL-02).

:func:`compute_stats` reduces a :class:`~pdgs.validation.colocation.MatchupSet` to a
FROZEN :class:`ValidationStats` block: match count, bias, RMSE, std, and the
percentage of pairs agreeing within tolerance. These are the persisted comparison
statistics consumed by the threshold gate (REQ-VAL-03) and the report (REQ-VAL-04).

Differences are defined as ``derived - official`` throughout.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pdgs.config.processing import ValidationConfig
from pdgs.validation.colocation import MatchupSet


@dataclass(frozen=True)
class ValidationStats:
    """Comparison statistics for a validation run (FROZEN — REQ-VAL-02).

    All temperatures are in Kelvin; ``diff = derived - official``.

    * ``match_count`` — number of co-located pairs.
    * ``bias_k`` — mean difference (signed; positive ⇒ derived warmer).
    * ``rmse_k`` — root-mean-square difference.
    * ``std_k`` — standard deviation of the differences.
    * ``pct_within_tol`` — % of pairs with ``|diff| <= tolerance_k`` (0-100).
    * ``tolerance_k`` — the tolerance the ``pct_within_tol`` was computed against.

    With zero matchups the numeric fields are NaN / 0 and the gate treats the run
    as inconclusive (below ``min_match_count``).
    """

    match_count: int
    bias_k: float
    rmse_k: float
    std_k: float
    pct_within_tol: float
    tolerance_k: float


def compute_stats(matchups: MatchupSet, cfg: ValidationConfig) -> ValidationStats:
    """Compute :class:`ValidationStats` from ``matchups`` (REQ-VAL-02).

    ``pct_within_tol`` counts pairs with ``|derived - official| <= cfg.tolerance_k``.
    An empty matchup set yields ``match_count = 0`` with NaN numeric fields, which
    the threshold gate reports as inconclusive (below ``min_match_count``).
    """
    count = matchups.count
    if count == 0:
        return ValidationStats(
            match_count=0,
            bias_k=float("nan"),
            rmse_k=float("nan"),
            std_k=float("nan"),
            pct_within_tol=float("nan"),
            tolerance_k=cfg.tolerance_k,
        )

    diff = matchups.derived_k - matchups.reference_k
    bias = float(np.mean(diff))
    rmse = float(np.sqrt(np.mean(diff**2)))
    std = float(np.std(diff))
    within = int(np.count_nonzero(np.abs(diff) <= cfg.tolerance_k))
    pct_within = 100.0 * within / count

    return ValidationStats(
        match_count=count,
        bias_k=bias,
        rmse_k=rmse,
        std_k=std,
        pct_within_tol=pct_within,
        tolerance_k=cfg.tolerance_k,
    )
