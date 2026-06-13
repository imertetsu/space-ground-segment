"""L1/L2 SAFE readers — FROZEN L1-reader contract (Phase 1).

:class:`L1Scene` is the in-memory representation the Phase 2 processing layer
consumes; freezing it here is what lets cloud-screening and SST retrieval be built
in parallel. :func:`read_l1_rbt` opens the relevant ``SL_1_RBT`` netCDFs with
xarray (relying on ``mask_and_scale`` to decode scaled brightness temperature to
Kelvin). :class:`L2Reference` / :func:`read_l2_wst` expose the official L2 WST SST
field for Phase 3 validation.

Per the ICD, the nadir 1 km TIR bands used by the MVP are S7/S8/S9 (``*_BT_in.nc``,
brightness temperature in K), geolocation from ``geodetic_in.nc``, cloud flags from
``flags_in.nc``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
import xarray as xr

from pdgs.ingestion.metadata import fixture_metadata

# Brightness-temperature bands available on the nadir 1 km TIR grid (MVP).
Band = Literal["S7", "S8", "S9"]
ViewName = Literal["nadir"]

# Band -> (netCDF filename, variable name) for the nadir 1 km grid ("in" suffix).
_L1_BAND_FILES: dict[str, tuple[str, str]] = {
    "S7": ("S7_BT_in.nc", "S7_BT_in"),
    "S8": ("S8_BT_in.nc", "S8_BT_in"),
    "S9": ("S9_BT_in.nc", "S9_BT_in"),
}
_L1_GEO_FILE = ("geodetic_in.nc", "latitude_in", "longitude_in")
_L1_FLAGS_FILE = ("flags_in.nc", "cloud_in")


@dataclass
class L1Scene:
    """In-memory L1 ``SL_1_RBT`` nadir scene consumed by processing (FROZEN).

    ``latitudes``/``longitudes`` are 2D geolocation grids (deg). Brightness
    temperature is read lazily per band via :meth:`brightness_temperature`, decoded
    to float32 Kelvin. ``cloud_flags`` is the raw cloud bitmask from ``flags_in``.
    """

    product_id: str
    sensing_start: datetime
    sensing_end: datetime
    latitudes: npt.NDArray[np.float32]
    longitudes: npt.NDArray[np.float32]
    cloud_flags: npt.NDArray[np.int32]
    safe_dir: Path
    view: ViewName = "nadir"

    @property
    def shape(self) -> tuple[int, ...]:
        """Pixel grid shape (rows, cols) of the scene."""
        return self.latitudes.shape

    def brightness_temperature(self, band: str) -> npt.NDArray[np.float32]:
        """Return the decoded brightness temperature (K) for ``band`` as float32.

        ``band`` must be one of ``S7``, ``S8``, ``S9``. Values are decoded from the
        stored scaled integers via xarray ``mask_and_scale`` (scale_factor /
        add_offset), with fill values surfaced as NaN.
        """
        try:
            filename, var = _L1_BAND_FILES[band]
        except KeyError as exc:
            raise ValueError(
                f"unknown L1 band {band!r}; expected one of {sorted(_L1_BAND_FILES)}"
            ) from exc
        path = self.safe_dir / filename
        with xr.open_dataset(path, mask_and_scale=True) as ds:
            data = ds[var].to_numpy()
        return cast(npt.NDArray[np.float32], np.asarray(data, dtype=np.float32))


@dataclass
class L2Reference:
    """In-memory official L2 ``SL_2_WST`` reference (SST in K) for validation.

    ``quality_level`` (0-5) is used in Phase 3 to filter reference pixels.
    Geolocation arrays are deg.
    """

    product_id: str
    sea_surface_temperature: npt.NDArray[np.float32]
    quality_level: npt.NDArray[np.int32]
    latitudes: npt.NDArray[np.float32]
    longitudes: npt.NDArray[np.float32]
    safe_dir: Path

    @property
    def shape(self) -> tuple[int, ...]:
        """Pixel grid shape (rows, cols) of the reference field."""
        return self.sea_surface_temperature.shape


def read_l1_rbt(safe_dir: str | Path, view: str = "nadir") -> L1Scene:
    """Read an ``SL_1_RBT`` SAFE folder into an :class:`L1Scene` (nadir, MVP).

    Only ``view="nadir"`` is supported in the MVP (oblique deferred). Geolocation
    and cloud flags are read eagerly; brightness temperature is read on demand.
    """
    if view != "nadir":
        raise ValueError(f"unsupported view {view!r}; MVP supports only 'nadir'")
    safe = Path(safe_dir)
    if not safe.is_dir():
        raise FileNotFoundError(f"SAFE folder not found: {safe}")

    geo_file, lat_var, lon_var = _L1_GEO_FILE
    with xr.open_dataset(safe / geo_file, mask_and_scale=True) as ds:
        latitudes: npt.NDArray[np.float32] = np.asarray(ds[lat_var].to_numpy(), dtype=np.float32)
        longitudes: npt.NDArray[np.float32] = np.asarray(ds[lon_var].to_numpy(), dtype=np.float32)

    flags_file, cloud_var = _L1_FLAGS_FILE
    with xr.open_dataset(safe / flags_file, mask_and_scale=False) as ds:
        cloud_flags: npt.NDArray[np.int32] = np.asarray(ds[cloud_var].to_numpy(), dtype=np.int32)

    start, end, _ = fixture_metadata(safe)
    return L1Scene(
        product_id=safe.name,
        sensing_start=start,
        sensing_end=end,
        latitudes=latitudes,
        longitudes=longitudes,
        cloud_flags=cloud_flags,
        safe_dir=safe,
        view="nadir",
    )


def read_l2_wst(safe_dir: str | Path) -> L2Reference:
    """Read an ``SL_2_WST`` SAFE folder into an :class:`L2Reference` (SST in K)."""
    safe = Path(safe_dir)
    if not safe.is_dir():
        raise FileNotFoundError(f"SAFE folder not found: {safe}")
    measurement = safe / "L2P.nc"
    with xr.open_dataset(measurement, mask_and_scale=True) as ds:
        sst: npt.NDArray[np.float32] = np.asarray(
            ds["sea_surface_temperature"].to_numpy(), dtype=np.float32
        )
        quality: npt.NDArray[np.int32] = np.asarray(ds["quality_level"].to_numpy(), dtype=np.int32)
        lat: npt.NDArray[np.float32] = np.asarray(ds["lat"].to_numpy(), dtype=np.float32)
        lon: npt.NDArray[np.float32] = np.asarray(ds["lon"].to_numpy(), dtype=np.float32)
    return L2Reference(
        product_id=safe.name,
        sea_surface_temperature=sst,
        quality_level=quality,
        latitudes=lat,
        longitudes=lon,
        safe_dir=safe,
    )
