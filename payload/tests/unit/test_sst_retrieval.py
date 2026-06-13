"""Unit tests for simplified split-window SST retrieval (REQ-PRO-02, REQ-PRO-05)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pdgs.config.processing import SstConfig
from pdgs.ingestion.readers import read_l1_rbt, read_l2_wst
from pdgs.processing.sst_retrieval.retrieve import retrieve_sst

# FIXTURE-ONLY synthetic coefficients (match fixtures/generate.py).
_FIXTURE_SST = SstConfig(
    coefficient_set_id="synthetic-fixture",
    a0=1.0,
    a1=1.0,
    a2=2.0,
    output_offset_k=0.0,
    source="SYNTHETIC fixture — not real",
    valid_min_k=271.15,
    valid_max_k=310.0,
)


def test_retrieve_recovers_synthetic_field_clear_sky(l1_safe_dir: Path, l2_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    ref = read_l2_wst(l2_safe_dir)
    cloud_mask = np.zeros(scene.shape, dtype=np.bool_)  # treat all as clear
    res = retrieve_sst(scene, cloud_mask, _FIXTURE_SST)

    assert res.sst_k.dtype == np.float32
    assert res.sst_k.shape == scene.shape
    diff = res.sst_k - ref.sea_surface_temperature
    rmse = float(np.sqrt(np.nanmean(diff**2)))
    # The fixtures are self-consistent: the WST carries a +0.05 K offset, so RMSE
    # is dominated by that tiny bias.
    assert rmse < 0.1


def test_retrieve_sets_cloudy_pixels_to_nan(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    cloud_mask = (scene.cloud_flags & 1) != 0
    res = retrieve_sst(scene, cloud_mask, _FIXTURE_SST)
    # Cloudy pixels are NaN (not computed); clear pixels are finite.
    assert bool(np.all(np.isnan(res.sst_k[cloud_mask])))
    assert bool(np.all(np.isfinite(res.sst_k[~cloud_mask])))


def test_retrieve_does_not_flag_cloudy_pixels_out_of_range(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    cloud_mask = (scene.cloud_flags & 1) != 0
    # A valid range that excludes everything would flag clear pixels but never the
    # cloudy NaN pixels.
    cfg = SstConfig(
        coefficient_set_id="x",
        a0=1.0,
        a1=1.0,
        a2=2.0,
        output_offset_k=0.0,
        source="s",
        valid_min_k=400.0,
        valid_max_k=500.0,
    )
    res = retrieve_sst(scene, cloud_mask, cfg)
    assert not bool(np.any(res.out_of_range[cloud_mask]))


def test_retrieve_flags_out_of_range_without_clamping(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    cloud_mask = np.zeros(scene.shape, dtype=np.bool_)
    # Squeeze the valid window so most pixels fall above valid_max_k.
    cfg = SstConfig(
        coefficient_set_id="x",
        a0=1.0,
        a1=1.0,
        a2=2.0,
        output_offset_k=0.0,
        source="s",
        valid_min_k=271.15,
        valid_max_k=295.0,
    )
    res = retrieve_sst(scene, cloud_mask, cfg)
    assert int(res.out_of_range.sum()) > 0
    # REQ-PRO-05: flagged pixels are NOT clamped — values exceed valid_max_k.
    flagged_vals = res.sst_k[res.out_of_range]
    assert bool(np.any(flagged_vals > 295.0))


def test_retrieve_mismatched_mask_shape_raises(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    bad_mask = np.zeros((3, 3), dtype=np.bool_)
    with pytest.raises(ValueError, match="shape"):
        retrieve_sst(scene, bad_mask, _FIXTURE_SST)
