"""Unit tests for the L1/L2 SAFE readers (FROZEN L1-reader contract)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pdgs.ingestion.readers import read_l1_rbt, read_l2_wst

# Generator grid (see fixtures/generate.py).
_ROWS, _COLS = 30, 40


def test_l1_scene_shapes(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    assert scene.shape == (_ROWS, _COLS)
    assert scene.latitudes.shape == (_ROWS, _COLS)
    assert scene.longitudes.shape == (_ROWS, _COLS)
    assert scene.cloud_flags.shape == (_ROWS, _COLS)
    assert scene.view == "nadir"


def test_l1_brightness_temperature_decoded_to_kelvin(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    for band in ("S7", "S8", "S9"):
        bt = scene.brightness_temperature(band)
        assert bt.shape == (_ROWS, _COLS)
        assert bt.dtype == np.float32
        finite = bt[np.isfinite(bt)]
        # Decoded brightness temperature is physical sea-surface-range Kelvin.
        assert float(finite.min()) > 270.0
        assert float(finite.max()) < 305.0


def test_l1_mask_and_scale_was_applied(l1_safe_dir: Path) -> None:
    # If mask_and_scale were NOT applied, raw int16 codes (~hundreds to thousands)
    # would surface instead of ~285-296 K. Assert we are in the decoded regime.
    scene = read_l1_rbt(l1_safe_dir)
    s8 = scene.brightness_temperature("S8")
    assert 280.0 < float(np.nanmean(s8)) < 300.0


def test_l1_band_ordering_s8_warmer_than_s9(l1_safe_dir: Path) -> None:
    # By construction S8 (10.8 um) >= S9 (12 um) everywhere (atmospheric absorption).
    scene = read_l1_rbt(l1_safe_dir)
    s8 = scene.brightness_temperature("S8")
    s9 = scene.brightness_temperature("S9")
    assert np.all(s8 >= s9 - 1e-3)


def test_l1_unknown_band_raises(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    with pytest.raises(ValueError, match="unknown L1 band"):
        scene.brightness_temperature("S6")


def test_l1_unsupported_view_raises(l1_safe_dir: Path) -> None:
    with pytest.raises(ValueError, match="nadir"):
        read_l1_rbt(l1_safe_dir, view="oblique")


def test_l1_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_l1_rbt(tmp_path / "nope.SAFE")


def test_l1_cloud_flags_present(l1_safe_dir: Path) -> None:
    scene = read_l1_rbt(l1_safe_dir)
    cloudy = int((scene.cloud_flags & 1).sum())
    assert cloudy > 0  # the fixture flags a handful of cloudy pixels


def test_l2_reference_fields(l2_safe_dir: Path) -> None:
    ref = read_l2_wst(l2_safe_dir)
    assert ref.shape == (_ROWS, _COLS)
    assert ref.sea_surface_temperature.dtype == np.float32
    sst = ref.sea_surface_temperature
    finite = sst[np.isfinite(sst)]
    assert float(finite.min()) > 270.0
    assert float(finite.max()) < 305.0
    # quality_level is 0-5; some pixels are low quality (cloud).
    assert int(ref.quality_level.min()) >= 0
    assert int(ref.quality_level.max()) <= 5
    assert int((ref.quality_level < 3).sum()) > 0


def test_split_window_recovers_wst(l1_safe_dir: Path, l2_safe_dir: Path) -> None:
    # The fixtures are built so SST = 1 + S8 + 2*(S8 - S9) recovers the WST field
    # (see fixtures/README.md). Verify the consistency the later phases rely on.
    scene = read_l1_rbt(l1_safe_dir)
    ref = read_l2_wst(l2_safe_dir)
    s8 = scene.brightness_temperature("S8")
    s9 = scene.brightness_temperature("S9")
    recovered = 1.0 + s8 + 2.0 * (s8 - s9)
    diff = recovered - ref.sea_surface_temperature
    rmse = float(np.sqrt(np.nanmean(diff**2)))
    assert rmse < 0.2  # tight: the fixture is self-consistent by construction
