"""Deterministic synthetic SLSTR fixture generator (SYNTHETIC — NOT real data).

Generates two tiny labelled-synthetic SAFE folders under ``payload/fixtures/``:

* ``l1_rbt_synthetic/`` — an ``SL_1_RBT`` nadir 1 km TIR scene: ``S7/S8/S9
  _BT_in.nc`` (brightness temperature in K, stored scaled so the reader exercises
  ``mask_and_scale``), ``geodetic_in.nc`` (lat/lon), ``flags_in.nc`` (cloud +
  confidence bitmasks) and a minimal ``xfdumanifest.xml``.
* ``l2_wst_synthetic/`` — a matching ``SL_2_WST`` GHRSST L2P single-measurement
  netCDF (``L2P.nc``: ``sea_surface_temperature``, ``quality_level``,
  ``sst_algorithm_type``, ``l2p_flags``, ``lat``, ``lon``) + manifest.

CONSISTENCY FOR LATER PHASES: both products are built from a single hidden
"true SST" field (sea ~270-305 K). The L1 S8/S9 brightness temperatures are
derived from that field via the inverse of a simple split-window so that, in
Phase 2, ``SST ~= a0 + a1*S8 + a2*(S8 - S9)`` recovers the true SST closely. The
L2 WST SST equals the true field (with a tiny offset + reduced quality on cloudy
pixels). A handful of pixels are marked cloudy in ``flags_in`` and have degraded
WST ``quality_level``. See ``fixtures/README.md`` for the exact relation.

Determinism: fixed RNG seed, no wall-clock/``Date.now``. Re-running reproduces the
fixtures byte-for-content-identically.

Run:  python fixtures/generate.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from netCDF4 import Dataset

# --- Deterministic configuration (DO NOT use time/random without a fixed seed) ---
SEED = 20240613
ROWS = 30
COLS = 40
FIXTURES_DIR = Path(__file__).resolve().parent
L1_DIR = FIXTURES_DIR / "l1_rbt_synthetic"
L2_DIR = FIXTURES_DIR / "l2_wst_synthetic"

# Fixed synthetic sensing window (UTC ISO-8601, SAFE-style).
START_TIME = "2024-06-13T10:00:00.000000Z"
STOP_TIME = "2024-06-13T10:03:00.000000Z"

# Synthetic geolocation box (a small open-ocean patch; values are illustrative).
LAT0, LAT1 = 40.0, 41.0
LON0, LON1 = -30.0, -28.5

# Split-window relation used to derive S8/S9 from the true SST, and recovered by
# Phase 2. SST = A0 + A1 * S8 + A2 * (S8 - S9). We invert it on generation.
#   These are SYNTHETIC, self-consistent coefficients for the fixture ONLY — they
#   are NOT the real (TBD, to-be-cited) operational split-window coefficients.
SW_A0 = 1.0
SW_A1 = 1.0
SW_A2 = 2.0

# netCDF scaling for stored brightness temperature (exercises mask_and_scale).
BT_SCALE = 0.01
BT_OFFSET = 280.0
BT_FILL = np.int16(-32768)

SYNTHETIC_TITLE = "SYNTHETIC Sentinel-3 SLSTR fixture — NOT real data (generated for tests)"


def _true_sst_field() -> np.ndarray:
    """Build the hidden true SST field (K), ~270-305 K, deterministically."""
    rng = np.random.default_rng(SEED)
    rows = np.linspace(0.0, 1.0, ROWS)[:, None]
    cols = np.linspace(0.0, 1.0, COLS)[None, :]
    # Smooth large-scale gradient (warm to the south/east) + gentle noise.
    base = 288.0 + 8.0 * cols + 4.0 * (1.0 - rows)
    noise = rng.normal(0.0, 0.15, size=(ROWS, COLS))
    sst = base + noise
    return np.clip(sst, 270.0, 305.0).astype(np.float64)


def _geolocation() -> tuple[np.ndarray, np.ndarray]:
    """Return (lat, lon) 2D grids in degrees."""
    lat = np.linspace(LAT1, LAT0, ROWS)[:, None] * np.ones((1, COLS))
    lon = np.ones((ROWS, 1)) * np.linspace(LON0, LON1, COLS)[None, :]
    return lat.astype(np.float64), lon.astype(np.float64)


def _cloud_mask() -> np.ndarray:
    """Deterministic boolean cloud mask: a few flagged pixels."""
    mask = np.zeros((ROWS, COLS), dtype=bool)
    # A small fixed cloudy blob, plus a couple of scattered cloudy pixels.
    mask[5:8, 10:14] = True
    mask[20, 30] = True
    mask[25, 5] = True
    return mask


def _derive_bt(sst: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Invert the split-window to get S7/S8/S9 brightness temperatures (K).

    We choose a per-pixel atmospheric term ``d = S8 - S9 >= 0`` (12 um is more
    strongly absorbed than 10.8 um), then set S8 so the split-window recovers SST:
        S8 = (SST - A0 - A2 * d) / A1
        S9 = S8 - d
    S7 (~3.7 um) is a plausible nearby BT, not used by the SST retrieval.
    """
    rng = np.random.default_rng(SEED + 1)
    # Atmospheric / water-vapour-like positive term, smooth + small.
    cols = np.linspace(0.0, 1.0, COLS)[None, :]
    d = 0.6 + 0.8 * cols + rng.uniform(0.0, 0.05, size=(ROWS, COLS))
    s8 = (sst - SW_A0 - SW_A2 * d) / SW_A1
    s9 = s8 - d
    s7 = s8 - 6.0 + rng.normal(0.0, 0.1, size=(ROWS, COLS))
    return s7, s8, s9


def _write_scaled_bt(group: Dataset, var_name: str, data: np.ndarray) -> None:
    """Write a brightness-temperature variable stored as scaled int16.

    We encode the physical Kelvin values to int16 ourselves and disable netCDF4's
    auto packing on write (otherwise it would re-apply scale/offset and double-
    encode). On read, xarray ``mask_and_scale`` decodes back to K.
    """
    var = group.createVariable(var_name, "i2", ("rows", "columns"), fill_value=BT_FILL, zlib=True)
    var.set_auto_maskandscale(False)
    var.scale_factor = np.float64(BT_SCALE)
    var.add_offset = np.float64(BT_OFFSET)
    var.units = "K"
    var.long_name = f"{var_name} brightness temperature (SYNTHETIC)"
    raw = np.round((data - BT_OFFSET) / BT_SCALE).astype(np.int16)
    var[:, :] = raw


def _set_global_attrs(ds: Dataset, title: str) -> None:
    """Stamp the mandatory SYNTHETIC labels + sensing window on a dataset."""
    ds.title = title
    ds.synthetic = "true"
    ds.comment = "SYNTHETIC test fixture generated by fixtures/generate.py — NOT real EO data."
    ds.start_time = START_TIME
    ds.stop_time = STOP_TIME
    ds.Conventions = "CF-1.7"


def _write_l1(sst: np.ndarray) -> None:
    """Write the synthetic SL_1_RBT SAFE folder."""
    L1_DIR.mkdir(parents=True, exist_ok=True)
    lat, lon = _geolocation()
    cloud = _cloud_mask()
    s7, s8, s9 = _derive_bt(sst)

    for fname, vname, data in (
        ("S7_BT_in.nc", "S7_BT_in", s7),
        ("S8_BT_in.nc", "S8_BT_in", s8),
        ("S9_BT_in.nc", "S9_BT_in", s9),
    ):
        with Dataset(L1_DIR / fname, "w", format="NETCDF4") as ds:
            _set_global_attrs(ds, SYNTHETIC_TITLE)
            ds.createDimension("rows", ROWS)
            ds.createDimension("columns", COLS)
            _write_scaled_bt(ds, vname, data)

    with Dataset(L1_DIR / "geodetic_in.nc", "w", format="NETCDF4") as ds:
        _set_global_attrs(ds, SYNTHETIC_TITLE)
        ds.createDimension("rows", ROWS)
        ds.createDimension("columns", COLS)
        lat_v = ds.createVariable("latitude_in", "f8", ("rows", "columns"), zlib=True)
        lat_v.units = "degrees_north"
        lat_v.long_name = "latitude (SYNTHETIC)"
        lat_v[:, :] = lat
        lon_v = ds.createVariable("longitude_in", "f8", ("rows", "columns"), zlib=True)
        lon_v.units = "degrees_east"
        lon_v.long_name = "longitude (SYNTHETIC)"
        lon_v[:, :] = lon

    with Dataset(L1_DIR / "flags_in.nc", "w", format="NETCDF4") as ds:
        _set_global_attrs(ds, SYNTHETIC_TITLE)
        ds.createDimension("rows", ROWS)
        ds.createDimension("columns", COLS)
        # cloud_in: bit 0 set => cloudy (SYNTHETIC, simplified vs the real bitmask).
        cloud_v = ds.createVariable("cloud_in", "i4", ("rows", "columns"), zlib=True)
        cloud_v.long_name = "cloud flags (SYNTHETIC bitmask; bit0=cloud)"
        cloud_v.flag_masks = np.array([1], dtype=np.int32)
        cloud_v.flag_meanings = "cloud"
        cloud_v[:, :] = cloud.astype(np.int32)
        # confidence_in: a plausible confidence bitmask (bit 1 set over ocean).
        conf_v = ds.createVariable("confidence_in", "i4", ("rows", "columns"), zlib=True)
        conf_v.long_name = "confidence flags (SYNTHETIC bitmask; bit1=ocean)"
        conf_v.flag_masks = np.array([2], dtype=np.int32)
        conf_v.flag_meanings = "ocean"
        conf_v[:, :] = np.full((ROWS, COLS), 2, dtype=np.int32)

    _write_manifest(
        L1_DIR,
        product_type="SL_1_RBT",
        files=["S7_BT_in.nc", "S8_BT_in.nc", "S9_BT_in.nc", "geodetic_in.nc", "flags_in.nc"],
    )


def _write_l2(sst: np.ndarray) -> None:
    """Write the synthetic SL_2_WST GHRSST L2P SAFE folder."""
    L2_DIR.mkdir(parents=True, exist_ok=True)
    lat, lon = _geolocation()
    cloud = _cloud_mask()

    # Official WST SST = true field + a tiny constant offset (sensor/algorithm).
    wst_sst = sst + 0.05
    # quality_level 0-5: 5 over clear ocean, 2 over cloudy pixels (low quality).
    quality = np.full((ROWS, COLS), 5, dtype=np.int8)
    quality[cloud] = 2

    with Dataset(L2_DIR / "L2P.nc", "w", format="NETCDF4") as ds:
        _set_global_attrs(ds, SYNTHETIC_TITLE.replace("SLSTR fixture", "SLSTR L2 WST fixture"))
        ds.createDimension("nj", ROWS)
        ds.createDimension("ni", COLS)

        sst_v = ds.createVariable("sea_surface_temperature", "f4", ("nj", "ni"), zlib=True)
        sst_v.units = "K"
        sst_v.long_name = "sea surface temperature (SYNTHETIC)"
        sst_v[:, :] = wst_sst.astype(np.float32)

        q_v = ds.createVariable("quality_level", "i1", ("nj", "ni"), zlib=True)
        q_v.long_name = "GHRSST quality level (SYNTHETIC, 0-5)"
        q_v.valid_min = np.int8(0)
        q_v.valid_max = np.int8(5)
        q_v[:, :] = quality

        algo_v = ds.createVariable("sst_algorithm_type", "i1", ("nj", "ni"), zlib=True)
        algo_v.long_name = "SST algorithm type (SYNTHETIC)"
        algo_v[:, :] = np.full((ROWS, COLS), 1, dtype=np.int8)

        l2p_v = ds.createVariable("l2p_flags", "i2", ("nj", "ni"), zlib=True)
        l2p_v.long_name = "L2P flags (SYNTHETIC bitmask; bit1=cloud)"
        l2p_v[:, :] = cloud.astype(np.int16) << 1

        lat_v = ds.createVariable("lat", "f4", ("nj", "ni"), zlib=True)
        lat_v.units = "degrees_north"
        lat_v.long_name = "latitude (SYNTHETIC)"
        lat_v[:, :] = lat.astype(np.float32)

        lon_v = ds.createVariable("lon", "f4", ("nj", "ni"), zlib=True)
        lon_v.units = "degrees_east"
        lon_v.long_name = "longitude (SYNTHETIC)"
        lon_v[:, :] = lon.astype(np.float32)

    _write_manifest(L2_DIR, product_type="SL_2_WST", files=["L2P.nc"])


def _write_manifest(safe_dir: Path, product_type: str, files: list[str]) -> None:
    """Write a minimal SYNTHETIC xfdumanifest.xml listing the data files."""
    data_objects = "\n".join(
        f'    <dataObject ID="{Path(f).stem}">'
        f'<byteStream><fileLocation href="./{f}"/></byteStream></dataObject>'
        for f in files
    )
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- SYNTHETIC fixture manifest — NOT a real SAFE manifest. -->\n"
        '<xfdu:XFDU xmlns:xfdu="urn:ccsds:schema:xfdu:1">\n'
        "  <metadataSection>\n"
        f"    <productType>{product_type}</productType>\n"
        f"    <synthetic>true</synthetic>\n"
        f"    <startTime>{START_TIME}</startTime>\n"
        f"    <stopTime>{STOP_TIME}</stopTime>\n"
        "  </metadataSection>\n"
        "  <dataObjectSection>\n"
        f"{data_objects}\n"
        "  </dataObjectSection>\n"
        "</xfdu:XFDU>\n"
    )
    (safe_dir / "xfdumanifest.xml").write_text(manifest, encoding="utf-8")


def main() -> None:
    """Generate both synthetic SAFE fixtures deterministically."""
    sst = _true_sst_field()
    _write_l1(sst)
    _write_l2(sst)
    print(f"Wrote synthetic L1 fixture: {L1_DIR}")
    print(f"Wrote synthetic L2 fixture: {L2_DIR}")


if __name__ == "__main__":
    main()
