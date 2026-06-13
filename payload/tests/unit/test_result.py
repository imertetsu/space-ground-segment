"""Unit tests for the validation result + acceptance-threshold gate (REQ-VAL-02/03)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pdgs.config.processing import ValidationConfig
from pdgs.validation.result import evaluate, write_result_json
from pdgs.validation.stats import ValidationStats

_TS = datetime(2026, 6, 13, tzinfo=UTC)


def _stats(
    *,
    count: int = 200,
    bias: float = 0.2,
    rmse: float = 0.5,
    std: float = 0.4,
    pct: float = 99.0,
    tol: float = 2.0,
) -> ValidationStats:
    return ValidationStats(
        match_count=count,
        bias_k=bias,
        rmse_k=rmse,
        std_k=std,
        pct_within_tol=pct,
        tolerance_k=tol,
    )


def _evaluate(stats: ValidationStats, cfg: ValidationConfig) -> object:
    return evaluate(
        stats,
        cfg,
        derived_product_id="D",
        reference_product_id="R",
        processor_version="1.2.3",
        config_version="cv",
        run_timestamp=_TS,
    )


def test_good_case_passes() -> None:
    result = _evaluate(_stats(), ValidationConfig())
    assert result.passed is True
    assert result.checks.enough_matchups
    assert result.checks.bias_within_bound
    assert result.checks.rmse_within_bound
    assert result.checks.pct_within_tol_ok


def test_fails_on_excessive_bias() -> None:
    result = _evaluate(_stats(bias=2.5), ValidationConfig())
    assert result.passed is False
    assert result.checks.bias_within_bound is False
    # Other checks still pass independently.
    assert result.checks.rmse_within_bound is True


def test_fails_on_negative_bias_magnitude() -> None:
    result = _evaluate(_stats(bias=-1.5), ValidationConfig())
    assert result.passed is False
    assert result.checks.bias_within_bound is False


def test_fails_on_excessive_rmse() -> None:
    result = _evaluate(_stats(rmse=3.0), ValidationConfig())
    assert result.passed is False
    assert result.checks.rmse_within_bound is False


def test_fails_on_low_pct_within_tol() -> None:
    result = _evaluate(_stats(pct=50.0), ValidationConfig())
    assert result.passed is False
    assert result.checks.pct_within_tol_ok is False


def test_fails_on_too_few_matchups() -> None:
    result = _evaluate(_stats(count=10), ValidationConfig(min_match_count=100))
    assert result.passed is False
    assert result.checks.enough_matchups is False
    # Too few matchups => other checks are also reported as not-satisfied.
    assert result.checks.bias_within_bound is False


def test_nan_stats_fail_the_gate() -> None:
    nan_stats = ValidationStats(
        match_count=0,
        bias_k=float("nan"),
        rmse_k=float("nan"),
        std_k=float("nan"),
        pct_within_tol=float("nan"),
        tolerance_k=2.0,
    )
    result = _evaluate(nan_stats, ValidationConfig())
    assert result.passed is False


def test_metadata_recorded() -> None:
    result = _evaluate(_stats(), ValidationConfig())
    assert result.derived_product_id == "D"
    assert result.reference_product_id == "R"
    assert result.processor_version == "1.2.3"
    assert result.config_version == "cv"
    assert result.run_timestamp == _TS


def test_write_result_json_roundtrips(tmp_path: Path) -> None:
    result = _evaluate(_stats(), ValidationConfig())
    path = write_result_json(result, tmp_path)
    assert path.name == "validation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert data["derived_product_id"] == "D"
    assert data["stats"]["match_count"] == 200
    assert data["thresholds"]["min_match_count"] == 100
    assert data["checks"]["bias_within_bound"] is True


def test_write_result_json_nan_serialised_as_null(tmp_path: Path) -> None:
    nan_stats = ValidationStats(
        match_count=0,
        bias_k=float("nan"),
        rmse_k=float("nan"),
        std_k=float("nan"),
        pct_within_tol=float("nan"),
        tolerance_k=2.0,
    )
    result = _evaluate(nan_stats, ValidationConfig())
    path = write_result_json(result, tmp_path)
    raw = path.read_text(encoding="utf-8")
    assert "NaN" not in raw  # valid JSON, not Python's NaN literal
    data = json.loads(raw)
    assert data["stats"]["bias_k"] is None
