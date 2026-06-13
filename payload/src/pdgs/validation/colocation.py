"""Nearest-neighbour co-location of derived SST vs the official L2 (REQ-VAL-01).

:func:`colocate` matches each clear-sky, finite pixel of the derived SST field to
its nearest pixel in the official :class:`~pdgs.ingestion.readers.L2Reference`
grid, using a :class:`scipy.spatial.cKDTree` over (lat, lon). It keeps only pairs
whose reference ``quality_level`` meets the configured minimum (REQ-VAL-01).

SIMPLIFICATION: nearest-neighbour gridding on (lat, lon) — no rigorous resampling
or footprint matching (see SRD §4). For the same-grid synthetic fixtures this
reduces to an aligned comparison, but the KDTree path is exercised regardless so it
also works for the differing real derived / SL_2_WST grids.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.spatial import cKDTree

from pdgs.config.processing import ValidationConfig
from pdgs.ingestion.readers import L2Reference
from pdgs.processing.product import DerivedSstProduct


@dataclass(frozen=True)
class MatchupSet:
    """Co-located derived/official SST pairs (Kelvin) plus their geolocation.

    All arrays are 1D and parallel: ``derived_k[i]`` was matched to
    ``reference_k[i]`` at ``(latitudes[i], longitudes[i])`` (the derived pixel's
    location). ``count`` is the number of pairs.
    """

    derived_k: npt.NDArray[np.float64]
    reference_k: npt.NDArray[np.float64]
    latitudes: npt.NDArray[np.float64]
    longitudes: npt.NDArray[np.float64]

    @property
    def count(self) -> int:
        """Number of co-located pairs."""
        return int(self.derived_k.size)


def colocate(
    derived: DerivedSstProduct,
    reference: L2Reference,
    cfg: ValidationConfig,
) -> MatchupSet:
    """Nearest-neighbour matchup of ``derived`` against ``reference`` (REQ-VAL-01).

    Selects derived pixels that are clear-sky (``cloud_mask`` False), not flagged
    out-of-range, and finite. For each, finds the nearest reference pixel by
    (lat, lon) via a :class:`scipy.spatial.cKDTree`. A pair is kept only when the
    reference value is finite and its ``quality_level`` ≥ ``cfg.min_quality_level``.

    Returns a :class:`MatchupSet` of the kept pairs (possibly empty).
    """
    ref_lat = np.asarray(reference.latitudes, dtype=np.float64).ravel()
    ref_lon = np.asarray(reference.longitudes, dtype=np.float64).ravel()
    ref_sst = np.asarray(reference.sea_surface_temperature, dtype=np.float64).ravel()
    ref_quality = np.asarray(reference.quality_level, dtype=np.int64).ravel()

    # Reference pixels usable as match targets: finite SST and a finite location.
    ref_usable = np.isfinite(ref_sst) & np.isfinite(ref_lat) & np.isfinite(ref_lon)
    if not bool(np.any(ref_usable)):
        return _empty_matchup()

    ref_idx = np.flatnonzero(ref_usable)
    tree = cKDTree(np.column_stack((ref_lat[ref_idx], ref_lon[ref_idx])))

    der_sst = np.asarray(derived.sea_surface_temperature, dtype=np.float64).ravel()
    der_lat = np.asarray(derived.latitudes, dtype=np.float64).ravel()
    der_lon = np.asarray(derived.longitudes, dtype=np.float64).ravel()
    cloud = np.asarray(derived.cloud_mask, dtype=np.bool_).ravel()
    oor = np.asarray(derived.out_of_range, dtype=np.bool_).ravel()

    # Candidate derived pixels: clear sky, in-range, and finite (value + location).
    der_usable = ~cloud & ~oor & np.isfinite(der_sst) & np.isfinite(der_lat) & np.isfinite(der_lon)
    if not bool(np.any(der_usable)):
        return _empty_matchup()

    der_sel = np.flatnonzero(der_usable)
    query_points = np.column_stack((der_lat[der_sel], der_lon[der_sel]))
    # cKDTree.query returns (distances, indices) into the tree's point array.
    _distances, nn = tree.query(query_points, k=1)
    nn = np.asarray(nn, dtype=np.int64).ravel()

    # Map tree indices back to the original reference flat indices.
    matched_ref = ref_idx[nn]
    keep = (ref_quality[matched_ref] >= cfg.min_quality_level) & np.isfinite(ref_sst[matched_ref])

    der_keep = der_sel[keep]
    ref_keep = matched_ref[keep]

    return MatchupSet(
        derived_k=der_sst[der_keep],
        reference_k=ref_sst[ref_keep],
        latitudes=der_lat[der_keep],
        longitudes=der_lon[der_keep],
    )


def _empty_matchup() -> MatchupSet:
    """Return an empty :class:`MatchupSet` (no co-located pairs)."""
    empty = np.empty(0, dtype=np.float64)
    return MatchupSet(
        derived_k=empty,
        reference_k=empty.copy(),
        latitudes=empty.copy(),
        longitudes=empty.copy(),
    )
