"""Lightweight SAFE-folder metadata extraction (sensing window + bbox).

Used by the offline client to populate :class:`~pdgs.ingestion.datastore.ProductRef`
without parsing the full manifest. Reads the global netCDF attributes our fixtures
carry (``start_time`` / ``stop_time``) and derives the bbox from the geolocation
arrays. Real products carry richer manifests; this is sufficient for the offline
fixture path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xarray as xr

from pdgs.catalogue.models import BBox

# Geolocation files/vars by product type (L1 nadir vs L2 WST), tried in order.
_GEO_CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("geodetic_in.nc", "latitude_in", "longitude_in"),  # L1 SL_1_RBT nadir
    ("L2P.nc", "lat", "lon"),  # L2 SL_2_WST (single measurement nc)
)


def _parse_attr_time(value: str) -> datetime:
    """Parse a SAFE-style time attribute to a UTC datetime."""
    text = value.strip().rstrip("Z")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _find_geo_file(safe_dir: Path) -> tuple[Path, str, str] | None:
    for filename, lat_var, lon_var in _GEO_CANDIDATES:
        path = safe_dir / filename
        if path.is_file():
            return path, lat_var, lon_var
    return None


def fixture_metadata(safe_dir: Path) -> tuple[datetime, datetime, BBox | None]:
    """Return ``(sensing_start, sensing_end, bbox)`` for a SAFE folder.

    Sensing window comes from the geolocation file's global ``start_time`` /
    ``stop_time`` attributes; the bbox from the lat/lon arrays.
    """
    geo = _find_geo_file(safe_dir)
    if geo is None:
        # Deterministic fallback so callers never crash on an unexpected layout.
        epoch = datetime(2024, 1, 1, tzinfo=UTC)
        return epoch, epoch, None

    path, lat_var, lon_var = geo
    with xr.open_dataset(path, mask_and_scale=True) as ds:
        start_raw = ds.attrs.get("start_time")
        stop_raw = ds.attrs.get("stop_time")
        start = _parse_attr_time(str(start_raw)) if start_raw else datetime(2024, 1, 1, tzinfo=UTC)
        stop = _parse_attr_time(str(stop_raw)) if stop_raw else start
        lat = ds[lat_var].to_numpy()
        lon = ds[lon_var].to_numpy()

    bbox: BBox | None = None
    if lat.size and lon.size:
        finite_lat = lat[np.isfinite(lat)]
        finite_lon = lon[np.isfinite(lon)]
        if finite_lat.size and finite_lon.size:
            bbox = (
                float(finite_lon.min()),
                float(finite_lat.min()),
                float(finite_lon.max()),
                float(finite_lat.max()),
            )
    return start, stop, bbox
