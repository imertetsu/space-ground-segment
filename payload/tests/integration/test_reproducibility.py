"""Integration tests — reproducible reruns + on-demand reprocessing (REQ-CFG-03, REQ-OPS-02).

* REQ-CFG-03: re-running the processing chain with the SAME inputs and the SAME
  processor/config versions yields an equivalent derived product (identical SST
  field and provenance versions) — reruns are deterministic.
* REQ-OPS-02: a previously-processed product can be reprocessed on demand by
  re-running the chain for the selected source; the catalogue record is refreshed
  in place (INSERT OR REPLACE) rather than duplicated.

The Phase 4 ``reprocess`` CLI subcommand and dead-letter inspection are out of
scope for Phase 3; this exercises the underlying reprocessing capability that the
orchestration already provides.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pdgs.catalogue.models import ProductStatus
from pdgs.catalogue.repository import SqliteCatalogue
from pdgs.config.processing import load_config
from pdgs.processing.product import process_scene

_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture
def catalogue(tmp_path: Path) -> SqliteCatalogue:
    return SqliteCatalogue(tmp_path / "catalogue.sqlite")


@pytest.mark.integration
def test_rerun_is_reproducible(
    l1_safe_dir: Path,
    catalogue: SqliteCatalogue,
    tmp_path: Path,
) -> None:
    cfg = load_config(_CONFIG_ROOT / "fixture.toml")
    first = process_scene(l1_safe_dir, cfg, catalogue, tmp_path / "a")
    second = process_scene(l1_safe_dir, cfg, catalogue, tmp_path / "b")

    # Same inputs + same versions => equivalent SST field (bit-for-bit over finite
    # pixels; NaN positions identical) and identical provenance versions (REQ-CFG-03).
    assert second.provenance.processor_version == first.provenance.processor_version
    assert second.provenance.config_version == first.provenance.config_version
    assert second.provenance.input_product_ids == first.provenance.input_product_ids
    a = first.sea_surface_temperature
    b = second.sea_surface_temperature
    assert np.array_equal(np.isnan(a), np.isnan(b))
    assert np.array_equal(a[~np.isnan(a)], b[~np.isnan(b)])
    assert np.array_equal(first.cloud_mask, second.cloud_mask)
    assert np.array_equal(first.out_of_range, second.out_of_range)


@pytest.mark.integration
def test_on_demand_reprocessing_refreshes_in_place(
    l1_safe_dir: Path,
    catalogue: SqliteCatalogue,
    tmp_path: Path,
) -> None:
    cfg = load_config(_CONFIG_ROOT / "fixture.toml")
    derived = process_scene(l1_safe_dir, cfg, catalogue, tmp_path / "out")
    product_id = derived.product_id

    # Mark it past PROCESSED to prove a reprocess resets the record.
    catalogue.update_status(product_id, ProductStatus.VALIDATED)
    assert catalogue.get(product_id) is not None
    assert catalogue.get(product_id).status is ProductStatus.VALIDATED  # type: ignore[union-attr]

    # Reprocess the SAME selected product on demand (REQ-OPS-02).
    reprocessed = process_scene(l1_safe_dir, cfg, catalogue, tmp_path / "out2")
    assert reprocessed.product_id == product_id

    # No duplicate row; the record is refreshed back to PROCESSED.
    all_derived = catalogue.list(product_type="SST_L2_DERIVED")
    assert len(all_derived) == 1
    assert all_derived[0].status is ProductStatus.PROCESSED
