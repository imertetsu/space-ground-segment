"""Unit tests for nearest-neighbour co-location (REQ-VAL-01)."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import numpy.typing as npt

from pdgs.catalogue.models import Provenance
from pdgs.config.processing import ValidationConfig
from pdgs.ingestion.readers import L2Reference
from pdgs.processing.product import DerivedSstProduct
from pdgs.validation.colocation import colocate


def _grid(rows: int, cols: int) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]]:
    """Return a simple (lat, lon) meshgrid of float32 arrays."""
    lat = np.linspace(0.0, 1.0, rows, dtype=np.float32)
    lon = np.linspace(10.0, 11.0, cols, dtype=np.float32)
    lat2d, lon2d = np.meshgrid(lat, lon, indexing="ij")
    return lat2d.astype(np.float32), lon2d.astype(np.float32)


def _derived(
    sst: npt.NDArray[np.float32],
    lat: npt.NDArray[np.float32],
    lon: npt.NDArray[np.float32],
    *,
    cloud: npt.NDArray[np.bool_] | None = None,
    oor: npt.NDArray[np.bool_] | None = None,
) -> DerivedSstProduct:
    """Build an in-memory DerivedSstProduct for testing."""
    return DerivedSstProduct(
        product_id="DERIVED_TEST",
        sea_surface_temperature=sst,
        cloud_mask=cloud if cloud is not None else np.zeros(sst.shape, dtype=np.bool_),
        out_of_range=oor if oor is not None else np.zeros(sst.shape, dtype=np.bool_),
        latitudes=lat,
        longitudes=lon,
        provenance=Provenance(
            processor_version="t",
            config_version="t",
            input_product_ids=("src",),
            run_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        coefficient_set_id="c",
        source_product_id="src",
    )


def _reference(
    sst: npt.NDArray[np.float32],
    quality: npt.NDArray[np.int32],
    lat: npt.NDArray[np.float32],
    lon: npt.NDArray[np.float32],
) -> L2Reference:
    """Build an in-memory L2Reference for testing."""
    from pathlib import Path

    return L2Reference(
        product_id="REF_TEST",
        sea_surface_temperature=sst,
        quality_level=quality,
        latitudes=lat,
        longitudes=lon,
        safe_dir=Path("."),
    )


def test_same_grid_returns_aligned_pairs() -> None:
    lat, lon = _grid(5, 6)
    der_sst = np.full((5, 6), 290.0, dtype=np.float32)
    ref_sst = np.full((5, 6), 289.5, dtype=np.float32)
    quality = np.full((5, 6), 5, dtype=np.int32)

    derived = _derived(der_sst, lat, lon)
    reference = _reference(ref_sst, quality, lat, lon)

    matchups = colocate(derived, reference, ValidationConfig(min_match_count=1))

    # All 30 pixels are clear, in-range, quality 5 -> 30 aligned pairs.
    assert matchups.count == 30
    assert np.allclose(matchups.derived_k, 290.0)
    assert np.allclose(matchups.reference_k, 289.5)


def test_quality_filter_excludes_low_quality_reference() -> None:
    lat, lon = _grid(4, 4)
    der_sst = np.full((4, 4), 290.0, dtype=np.float32)
    ref_sst = np.full((4, 4), 290.0, dtype=np.float32)
    # Half the reference pixels have quality 2 (< min 3) -> excluded.
    quality = np.full((4, 4), 5, dtype=np.int32)
    quality[:2, :] = 2

    derived = _derived(der_sst, lat, lon)
    reference = _reference(ref_sst, quality, lat, lon)

    matchups = colocate(derived, reference, ValidationConfig(min_quality_level=3))
    # On the same grid, each derived pixel maps to its co-located reference pixel,
    # so only the 8 high-quality reference pixels survive.
    assert matchups.count == 8


def test_cloudy_and_out_of_range_derived_pixels_excluded() -> None:
    lat, lon = _grid(3, 3)
    der_sst = np.full((3, 3), 290.0, dtype=np.float32)
    ref_sst = np.full((3, 3), 290.0, dtype=np.float32)
    quality = np.full((3, 3), 5, dtype=np.int32)

    cloud = np.zeros((3, 3), dtype=np.bool_)
    cloud[0, 0] = True
    der_sst[0, 0] = np.nan  # cloudy pixels are NaN in the real pipeline
    oor = np.zeros((3, 3), dtype=np.bool_)
    oor[1, 1] = True

    derived = _derived(der_sst, lat, lon, cloud=cloud, oor=oor)
    reference = _reference(ref_sst, quality, lat, lon)

    matchups = colocate(derived, reference, ValidationConfig(min_match_count=1))
    # 9 pixels minus 1 cloudy minus 1 out-of-range = 7.
    assert matchups.count == 7


def test_nan_derived_pixels_excluded_even_if_clear() -> None:
    lat, lon = _grid(3, 3)
    der_sst = np.full((3, 3), 290.0, dtype=np.float32)
    der_sst[2, 2] = np.nan
    ref_sst = np.full((3, 3), 290.0, dtype=np.float32)
    quality = np.full((3, 3), 5, dtype=np.int32)

    derived = _derived(der_sst, lat, lon)
    reference = _reference(ref_sst, quality, lat, lon)
    matchups = colocate(derived, reference, ValidationConfig(min_match_count=1))
    assert matchups.count == 8


def test_differing_grids_match_nearest_neighbour() -> None:
    # Reference grid is coarser/offset; KDTree must still find nearest pixels.
    der_lat, der_lon = _grid(4, 4)
    der_sst = np.full((4, 4), 291.0, dtype=np.float32)
    derived = _derived(der_sst, der_lat, der_lon)

    # A single reference pixel near the grid centre.
    ref_lat = np.array([[0.5]], dtype=np.float32)
    ref_lon = np.array([[10.5]], dtype=np.float32)
    ref_sst = np.array([[290.0]], dtype=np.float32)
    quality = np.array([[5]], dtype=np.int32)
    reference = _reference(ref_sst, quality, ref_lat, ref_lon)

    matchups = colocate(derived, reference, ValidationConfig(min_match_count=1))
    # All 16 derived pixels match the one reference pixel.
    assert matchups.count == 16
    assert np.allclose(matchups.reference_k, 290.0)


def test_empty_when_no_reference_passes_quality() -> None:
    lat, lon = _grid(3, 3)
    der_sst = np.full((3, 3), 290.0, dtype=np.float32)
    ref_sst = np.full((3, 3), 290.0, dtype=np.float32)
    quality = np.zeros((3, 3), dtype=np.int32)  # all below min
    derived = _derived(der_sst, lat, lon)
    reference = _reference(ref_sst, quality, lat, lon)
    matchups = colocate(derived, reference, ValidationConfig(min_quality_level=3))
    assert matchups.count == 0


def test_reference_outside_derived_bbox_is_not_matched() -> None:
    # Derived field is a small patch near (0..1, 10..11). The reference grid is much
    # larger and includes far-away pixels; the bbox subset must exclude those so no
    # derived pixel matches a spurious far reference.
    der_lat, der_lon = _grid(4, 4)
    der_sst = np.full((4, 4), 291.0, dtype=np.float32)
    derived = _derived(der_sst, der_lat, der_lon)

    # Reference: one near pixel (inside the derived bbox) at a distinct value, plus
    # a block of far pixels (10 degrees away) which must never be matched.
    ref_lat = np.array(
        [[0.5, 50.0, 50.0], [0.5, 50.0, 50.0]],
        dtype=np.float32,
    )
    ref_lon = np.array(
        [[10.5, 80.0, 80.0], [10.5, 80.0, 80.0]],
        dtype=np.float32,
    )
    ref_sst = np.array(
        [[290.0, 200.0, 200.0], [290.0, 200.0, 200.0]],
        dtype=np.float32,
    )
    quality = np.full((2, 3), 5, dtype=np.int32)
    reference = _reference(ref_sst, quality, ref_lat, ref_lon)

    matchups = colocate(derived, reference, ValidationConfig(min_match_count=1))
    # All 16 derived pixels match the near reference (290.0); none the far 200.0.
    assert matchups.count == 16
    assert np.allclose(matchups.reference_k, 290.0)


def test_empty_when_no_reference_inside_bbox() -> None:
    # Reference entirely outside the derived bbox (+0.5 deg margin) -> no matchups.
    der_lat, der_lon = _grid(3, 3)
    der_sst = np.full((3, 3), 291.0, dtype=np.float32)
    derived = _derived(der_sst, der_lat, der_lon)

    far_lat = np.full((2, 2), 60.0, dtype=np.float32)
    far_lon = np.full((2, 2), 90.0, dtype=np.float32)
    ref_sst = np.full((2, 2), 290.0, dtype=np.float32)
    quality = np.full((2, 2), 5, dtype=np.int32)
    reference = _reference(ref_sst, quality, far_lat, far_lon)

    matchups = colocate(derived, reference, ValidationConfig(min_match_count=1))
    assert matchups.count == 0
