"""Integration tests — Phase 3 validation end-to-end on the fixtures (REQ-VAL-01..04).

Exercises the full ``process_scene`` -> ``validate_product`` flow over the committed
synthetic fixtures with the FIXTURE-ONLY config: a clean run produces a report with
real numbers that PASSES the thresholds (and, via the CLI, sets the derived product
VALIDATED), while a deliberately-degraded derived field TRIPS the gate (REQ-VAL-03).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from pdgs.catalogue.models import ProductStatus
from pdgs.catalogue.repository import SqliteCatalogue
from pdgs.cli.main import main
from pdgs.config.processing import load_config
from pdgs.ingestion.readers import read_l2_wst
from pdgs.processing.product import process_scene
from pdgs.validation.orchestrate import validate_product

_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture
def catalogue(tmp_path: Path) -> SqliteCatalogue:
    return SqliteCatalogue(tmp_path / "catalogue.sqlite")


@pytest.mark.integration
def test_validate_product_passes_on_fixtures(
    l1_safe_dir: Path,
    l2_safe_dir: Path,
    catalogue: SqliteCatalogue,
    tmp_path: Path,
) -> None:
    cfg = load_config(_CONFIG_ROOT / "fixture.toml")
    derived = process_scene(l1_safe_dir, cfg, catalogue, tmp_path / "derived")
    reference = read_l2_wst(l2_safe_dir)

    reports = tmp_path / "reports"
    result = validate_product(
        derived,
        reference,
        cfg.validation,
        reports,
        config_version=cfg.config_version,
        synthetic_inputs=True,
    )

    # --- real numbers that PASS ---
    assert result.passed is True
    assert result.stats.match_count >= cfg.validation.min_match_count
    assert abs(result.stats.bias_k) <= cfg.validation.max_abs_bias_k
    assert result.stats.rmse_k <= cfg.validation.max_rmse_k
    assert result.stats.pct_within_tol >= cfg.validation.min_pct_within_tol
    assert result.config_version == cfg.config_version

    # --- artefacts persisted (REQ-VAL-02/04) ---
    assert (reports / "validation.json").is_file()
    assert (reports / "validation.md").is_file()
    assert (reports / "difference.png").is_file()
    data = json.loads((reports / "validation.json").read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert data["synthetic_inputs"] is True
    md = (reports / "validation.md").read_text(encoding="utf-8")
    assert "SYNTHETIC INPUTS" in md


@pytest.mark.integration
def test_degraded_derived_trips_the_gate(
    l1_safe_dir: Path,
    l2_safe_dir: Path,
    catalogue: SqliteCatalogue,
    tmp_path: Path,
) -> None:
    cfg = load_config(_CONFIG_ROOT / "fixture.toml")
    derived = process_scene(l1_safe_dir, cfg, catalogue, tmp_path / "derived")
    reference = read_l2_wst(l2_safe_dir)

    # Inject a large offset (+10 K) into the derived SST -> bias/RMSE explode.
    degraded = replace(
        derived,
        sea_surface_temperature=(derived.sea_surface_temperature + np.float32(10.0)),
    )

    result = validate_product(
        degraded,
        reference,
        cfg.validation,
        tmp_path / "reports",
        config_version=cfg.config_version,
        synthetic_inputs=True,
    )
    assert result.passed is False
    assert result.checks.bias_within_bound is False
    md = (tmp_path / "reports" / "validation.md").read_text(encoding="utf-8")
    assert "Overall verdict: FAIL" in md


@pytest.mark.integration
def test_cli_validate_passes_and_sets_validated(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PDGS_DATA_DIR", str(tmp_path / "data"))
    db = str(tmp_path / "cat.sqlite")
    cfg_path = str(_CONFIG_ROOT / "fixture.toml")
    rc = main(["validate", "--config", cfg_path, "--db", db, "--out", str(tmp_path / "derived")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Validation verdict: PASS" in out
    assert "VALIDATED" in out
    assert "SYNTHETIC" in out

    # The derived product's catalogue status is now VALIDATED.
    catalogue = SqliteCatalogue(db)
    products = catalogue.list(status=ProductStatus.VALIDATED)
    assert len(products) == 1
    assert products[0].level == "L2_DERIVED"


@pytest.mark.integration
def test_cli_validate_fails_gate_returns_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A config whose thresholds are impossible to meet trips the gate via the CLI.
    monkeypatch.setenv("PDGS_DATA_DIR", str(tmp_path / "data"))
    impossible = tmp_path / "impossible.toml"
    # Same FIXTURE-ONLY coefficients, but a near-zero RMSE bound the (near-perfect
    # but not exact) fixture cannot meet -> the gate trips.
    impossible.write_text(
        'config_version = "fixture-1.0.0"\n'
        "[sst]\n"
        'coefficient_set_id = "synthetic-fixture"\n'
        "a0 = 1.0\na1 = 1.0\na2 = 2.0\noutput_offset_k = 0.0\n"
        'source = "SYNTHETIC fixture - not real"\n'
        "valid_min_k = 271.15\nvalid_max_k = 310.0\n"
        "[cloud]\n"
        "bt_cloud_threshold_k = 250.0\nuse_l1_cloud_flag = true\n"
        "[validation]\n"
        "max_rmse_k = 0.0001\n",
        encoding="utf-8",
    )

    db = str(tmp_path / "cat.sqlite")
    rc = main(
        ["validate", "--config", str(impossible), "--db", db, "--out", str(tmp_path / "derived")]
    )
    assert rc == 1
    # The derived product must NOT be VALIDATED after a failed gate.
    catalogue = SqliteCatalogue(db)
    assert catalogue.list(status=ProductStatus.VALIDATED) == []
