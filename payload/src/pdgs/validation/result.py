"""Validation result + acceptance-threshold gate (REQ-VAL-02, REQ-VAL-03).

This module freezes the **validation-report schema** (the Phase 3 cross-phase
contract consumed by the OPS status CLI and the report renderer):

* :class:`ValidationResult` — the stats, the thresholds applied, the per-threshold
  pass/fail booleans, the overall ``passed`` verdict, and per-run metadata
  (derived/reference product ids, processor + config versions, run timestamp).
* :func:`evaluate` — apply the :class:`~pdgs.config.processing.ValidationConfig`
  thresholds to a :class:`~pdgs.validation.stats.ValidationStats` block, producing a
  :class:`ValidationResult` whose ``passed`` gates CI (REQ-VAL-03).
* :func:`write_result_json` — persist a :class:`ValidationResult` to ``validation.json``
  so runs are reproducible and machine-inspectable (REQ-VAL-02).

A run PASSES only when ALL of: enough matchups, |bias| within bound, RMSE within
bound, and the within-tolerance percentage at/above the minimum. Too few matchups
is treated as a FAILURE (inconclusive, not a pass) per the spec §7.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from pdgs.config.processing import ValidationConfig
from pdgs.validation.stats import ValidationStats


@dataclass(frozen=True)
class ThresholdChecks:
    """Per-threshold pass/fail booleans (each True ⇒ that bound is satisfied)."""

    enough_matchups: bool
    bias_within_bound: bool
    rmse_within_bound: bool
    pct_within_tol_ok: bool


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a validation run (FROZEN — validation-report schema, REQ-VAL-02/03).

    Bundles the computed ``stats``, the ``thresholds`` applied, the per-threshold
    ``checks``, the overall ``passed`` verdict, and the run ``metadata`` (product
    ids + processor/config versions + timestamp). Serialised to ``validation.json``
    for reproducibility and consumed by the report renderer / OPS status CLI.
    """

    stats: ValidationStats
    thresholds: ValidationConfig
    checks: ThresholdChecks
    passed: bool
    derived_product_id: str
    reference_product_id: str
    processor_version: str
    config_version: str
    run_timestamp: datetime
    synthetic_inputs: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable dict of the full result (REQ-VAL-02)."""
        return {
            "passed": self.passed,
            "derived_product_id": self.derived_product_id,
            "reference_product_id": self.reference_product_id,
            "processor_version": self.processor_version,
            "config_version": self.config_version,
            "run_timestamp": self.run_timestamp.isoformat(),
            "synthetic_inputs": self.synthetic_inputs,
            "stats": _stats_to_dict(self.stats),
            "thresholds": asdict(self.thresholds),
            "checks": asdict(self.checks),
        }


def _stats_to_dict(stats: ValidationStats) -> dict[str, object]:
    """Serialise stats with NaN floats rendered as ``None`` (valid JSON)."""
    raw = asdict(stats)
    out: dict[str, object] = {}
    for key, value in raw.items():
        if isinstance(value, float) and math.isnan(value):
            out[key] = None
        else:
            out[key] = value
    return out


def evaluate(
    stats: ValidationStats,
    cfg: ValidationConfig,
    *,
    derived_product_id: str,
    reference_product_id: str,
    processor_version: str,
    config_version: str,
    run_timestamp: datetime,
    synthetic_inputs: bool = False,
) -> ValidationResult:
    """Apply ``cfg`` thresholds to ``stats``, returning a gated :class:`ValidationResult`.

    The overall ``passed`` is the AND of all four checks (REQ-VAL-03). Insufficient
    matchups, or any NaN statistic (an empty/degenerate run), fails the gate — an
    inconclusive run is never a pass.
    """
    enough = stats.match_count >= cfg.min_match_count
    bias_ok = enough and _finite(stats.bias_k) and abs(stats.bias_k) <= cfg.max_abs_bias_k
    rmse_ok = enough and _finite(stats.rmse_k) and stats.rmse_k <= cfg.max_rmse_k
    pct_ok = (
        enough and _finite(stats.pct_within_tol) and stats.pct_within_tol >= cfg.min_pct_within_tol
    )

    checks = ThresholdChecks(
        enough_matchups=enough,
        bias_within_bound=bias_ok,
        rmse_within_bound=rmse_ok,
        pct_within_tol_ok=pct_ok,
    )
    passed = enough and bias_ok and rmse_ok and pct_ok

    return ValidationResult(
        stats=stats,
        thresholds=cfg,
        checks=checks,
        passed=passed,
        derived_product_id=derived_product_id,
        reference_product_id=reference_product_id,
        processor_version=processor_version,
        config_version=config_version,
        run_timestamp=run_timestamp,
        synthetic_inputs=synthetic_inputs,
    )


def _finite(value: float) -> bool:
    """Return True when ``value`` is a finite (non-NaN, non-inf) float."""
    return math.isfinite(value)


def write_result_json(result: ValidationResult, out_dir: str | Path) -> Path:
    """Write ``result`` to ``<out_dir>/validation.json``; return the path (REQ-VAL-02)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "validation.json"
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path
