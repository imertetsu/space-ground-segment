"""Unit tests for the L1/L2 SAFE readers (FROZEN L1-reader contract)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from netCDF4 import Dataset

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


def _write_real_like_wst(safe_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Write a tiny real-product-like GHRSST WST netCDF into ``safe_dir``.

    Mirrors the real ``SL_2_WST`` measurement file: a GHRSST-style filename (NOT
    ``L2P.nc``), a leading singleton ``time`` dim on the (time, nj, ni) fields, 2D
    ``lat``/``lon`` (nj, ni), and ``quality_level`` int8 0-5. Returns the (sst, lat)
    2D arrays written, for the caller to assert against the squeezed read-back.
    """
    safe_dir.mkdir(parents=True, exist_ok=True)
    rows, cols = 3, 4
    sst = (288.0 + np.arange(rows * cols, dtype=np.float32).reshape(rows, cols)).astype(np.float32)
    quality = np.full((rows, cols), 5, dtype=np.int8)
    lat = np.linspace(40.0, 41.0, rows, dtype=np.float32)[:, None] * np.ones((1, cols))
    lon = np.ones((rows, 1)) * np.linspace(-30.0, -28.5, cols, dtype=np.float32)[None, :]

    name = "20260515223233-MAR-L2P_GHRSST-SSTskin-SLSTRA-20260515_223233-v02.0-fv01.0.nc"
    with Dataset(safe_dir / name, "w", format="NETCDF4") as ds:
        ds.title = "real-like GHRSST WST (test)"
        ds.createDimension("time", 1)
        ds.createDimension("nj", rows)
        ds.createDimension("ni", cols)

        sst_v = ds.createVariable("sea_surface_temperature", "f4", ("time", "nj", "ni"))
        sst_v.units = "kelvin"
        sst_v[:] = sst[None, :, :]

        q_v = ds.createVariable("quality_level", "i1", ("time", "nj", "ni"))
        q_v[:] = quality[None, :, :]

        lat_v = ds.createVariable("lat", "f4", ("nj", "ni"))
        lat_v.units = "degrees_north"
        lat_v[:, :] = lat.astype(np.float32)
        lon_v = ds.createVariable("lon", "f4", ("nj", "ni"))
        lon_v.units = "degrees_east"
        lon_v[:, :] = lon.astype(np.float32)

    return sst, lat.astype(np.float32)


def test_l2_wst_reads_real_like_product_and_squeezes_time(tmp_path: Path) -> None:
    safe = tmp_path / "S3A_SL_2_WST____20260515_NT.SEN3"
    expected_sst, expected_lat = _write_real_like_wst(safe)

    ref = read_l2_wst(safe)

    # The leading singleton time dim is squeezed away -> 2D arrays.
    assert ref.sea_surface_temperature.ndim == 2
    assert ref.sea_surface_temperature.shape == (3, 4)
    assert ref.quality_level.shape == (3, 4)
    assert ref.latitudes.shape == (3, 4)
    assert ref.longitudes.shape == (3, 4)
    assert ref.product_id == safe.name
    np.testing.assert_allclose(ref.sea_surface_temperature, expected_sst)
    np.testing.assert_allclose(ref.latitudes, expected_lat)
    assert int(ref.quality_level.max()) == 5


def test_l2_wst_selects_measurement_nc_by_content(tmp_path: Path) -> None:
    # A decoy .nc without sea_surface_temperature must be skipped in favour of the
    # GHRSST measurement file (found by content, not by filename).
    safe = tmp_path / "WST.SEN3"
    _write_real_like_wst(safe)
    with Dataset(safe / "00_decoy.nc", "w", format="NETCDF4") as ds:
        ds.createDimension("x", 2)
        ds.createVariable("not_sst", "f4", ("x",))[:] = np.zeros(2, dtype=np.float32)

    ref = read_l2_wst(safe)
    assert ref.sea_surface_temperature.shape == (3, 4)


def test_l2_wst_no_measurement_nc_raises(tmp_path: Path) -> None:
    safe = tmp_path / "empty.SEN3"
    safe.mkdir()
    with pytest.raises(FileNotFoundError):
        read_l2_wst(safe)
