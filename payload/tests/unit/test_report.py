"""Unit tests for the validation report + difference plot (REQ-VAL-04)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from pdgs.config.processing import ValidationConfig
from pdgs.validation.colocation import MatchupSet
from pdgs.validation.report import render_difference_plot, render_markdown_report
from pdgs.validation.result import evaluate
from pdgs.validation.stats import ValidationStats

_TS = datetime(2026, 6, 13, tzinfo=UTC)


def _matchups(n: int = 50) -> MatchupSet:
    rng = np.random.default_rng(0)
    ref = np.full(n, 290.0, dtype=np.float64)
    der = ref + rng.normal(0.1, 0.2, size=n)
    lat = np.linspace(0.0, 1.0, n, dtype=np.float64)
    lon = np.linspace(10.0, 11.0, n, dtype=np.float64)
    return MatchupSet(derived_k=der, reference_k=ref, latitudes=lat, longitudes=lon)


def _result(
    stats: ValidationStats,
    cfg: ValidationConfig,
    *,
    synthetic: bool = True,
) -> object:
    return evaluate(
        stats,
        cfg,
        derived_product_id="D__SST_L2_DERIVED",
        reference_product_id="REF",
        processor_version="1.2.3",
        config_version="cv",
        run_timestamp=_TS,
        synthetic_inputs=synthetic,
    )


def _stats_from(matchups: MatchupSet, cfg: ValidationConfig) -> ValidationStats:
    from pdgs.validation.stats import compute_stats

    return compute_stats(matchups, cfg)


def test_difference_plot_png_written(tmp_path: Path) -> None:
    cfg = ValidationConfig(min_match_count=1)
    matchups = _matchups()
    stats = _stats_from(matchups, cfg)
    result = _result(stats, cfg)
    path = render_difference_plot(matchups, result, tmp_path)  # type: ignore[arg-type]
    assert path.name == "difference.png"
    assert path.is_file()
    assert path.stat().st_size > 0
    # PNG magic number.
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_difference_plot_handles_empty_matchups(tmp_path: Path) -> None:
    cfg = ValidationConfig()
    empty = MatchupSet(
        derived_k=np.empty(0, dtype=np.float64),
        reference_k=np.empty(0, dtype=np.float64),
        latitudes=np.empty(0, dtype=np.float64),
        longitudes=np.empty(0, dtype=np.float64),
    )
    stats = _stats_from(empty, cfg)
    result = _result(stats, cfg)
    path = render_difference_plot(empty, result, tmp_path)  # type: ignore[arg-type]
    assert path.is_file()


def test_markdown_report_written_and_labels_synthetic(tmp_path: Path) -> None:
    cfg = ValidationConfig(min_match_count=1)
    matchups = _matchups()
    stats = _stats_from(matchups, cfg)
    result = _result(stats, cfg, synthetic=True)
    md_path = render_markdown_report(result, "difference.png", tmp_path)  # type: ignore[arg-type]
    assert md_path.name == "validation.md"
    text = md_path.read_text(encoding="utf-8")
    assert "SYNTHETIC INPUTS" in text
    assert "Overall verdict: PASS" in text
    assert "Matchup count" in text
    assert "REQ-VAL-03" in text
    assert "![" in text and "difference.png" in text  # plot embedded
    assert "1.2.3" in text  # processor version recorded
    assert "cv" in text  # config version recorded


def test_markdown_report_non_synthetic_label(tmp_path: Path) -> None:
    cfg = ValidationConfig(min_match_count=1)
    matchups = _matchups()
    stats = _stats_from(matchups, cfg)
    result = _result(stats, cfg, synthetic=False)
    md_path = render_markdown_report(result, "difference.png", tmp_path)  # type: ignore[arg-type]
    text = md_path.read_text(encoding="utf-8")
    assert "SYNTHETIC INPUTS" not in text
    assert "Simplifications apply" in text


def test_markdown_report_shows_fail_verdict(tmp_path: Path) -> None:
    cfg = ValidationConfig()
    # Too few matchups -> FAIL.
    bad_stats = ValidationStats(
        match_count=5,
        bias_k=0.1,
        rmse_k=0.2,
        std_k=0.1,
        pct_within_tol=100.0,
        tolerance_k=2.0,
    )
    result = _result(bad_stats, cfg)
    md_path = render_markdown_report(result, "difference.png", tmp_path)  # type: ignore[arg-type]
    text = md_path.read_text(encoding="utf-8")
    assert "Overall verdict: FAIL" in text
