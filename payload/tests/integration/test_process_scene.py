"""Integration test — Phase 2 processing chain end-to-end on the fixtures.

Exercises :func:`pdgs.processing.product.process_scene` over the committed
synthetic L1 fixture with the FIXTURE-ONLY config: it must write a derived netCDF
carrying a full provenance block (REQ-PRO-03 / REQ-CFG-02), register a PROCESSED
``L2_DERIVED`` product, and recover the synthetic WST field within tight tolerance
over clear-sky pixels (proving the end-to-end mechanics).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from netCDF4 import Dataset

from pdgs.catalogue.models import ProductStatus
from pdgs.catalogue.repository import SqliteCatalogue
from pdgs.config.processing import load_config
from pdgs.ingestion.readers import read_l2_wst
from pdgs.processing.product import process_scene

_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture
def catalogue(tmp_path: Path) -> SqliteCatalogue:
    return SqliteCatalogue(tmp_path / "catalogue.sqlite")


@pytest.mark.integration
def test_process_scene_writes_product_and_registers(
    l1_safe_dir: Path,
    l2_safe_dir: Path,
    catalogue: SqliteCatalogue,
    tmp_path: Path,
) -> None:
    cfg = load_config(_CONFIG_ROOT / "fixture.toml")
    out_dir = tmp_path / "derived"

    derived = process_scene(l1_safe_dir, cfg, catalogue, out_dir)

    # --- in-memory product carries the masks + provenance ---
    assert derived.source_product_id == "l1_rbt_synthetic"
    assert derived.coefficient_set_id == cfg.sst.coefficient_set_id
    assert derived.provenance.config_version == cfg.config_version
    assert derived.provenance.input_product_ids == ("l1_rbt_synthetic",)
    assert derived.provenance.processor_version
    assert int(derived.cloud_mask.sum()) == 14  # the fixture's flagged pixels

    # --- a PROCESSED L2_DERIVED product is registered with provenance ---
    product = catalogue.get(derived.product_id)
    assert product is not None
    assert product.status is ProductStatus.PROCESSED
    assert product.level == "L2_DERIVED"
    assert product.product_type == "SST_L2_DERIVED"
    assert product.provenance is not None
    assert product.provenance.config_version == cfg.config_version
    assert product.provenance.input_product_ids == ("l1_rbt_synthetic",)

    # --- derived netCDF exists and carries the full provenance block as attrs ---
    nc_path = out_dir / f"{derived.product_id}.nc"
    assert nc_path.is_file()
    with Dataset(nc_path, "r") as ds:
        assert ds.processing_level == "L2"
        assert ds.product_type == "SST_L2_DERIVED"
        assert ds.config_version == cfg.config_version
        assert ds.input_product_ids == "l1_rbt_synthetic"
        assert ds.coefficient_set_id == cfg.sst.coefficient_set_id
        assert str(ds.processor_version)
        assert str(ds.run_timestamp)
        for var in ("sea_surface_temperature", "cloud_mask", "out_of_range", "lat", "lon"):
            assert var in ds.variables

    # --- end-to-end recovery: derived SST ~= official WST over clear sky ---
    ref = read_l2_wst(l2_safe_dir)
    clear = ~derived.cloud_mask
    diff = derived.sea_surface_temperature[clear] - ref.sea_surface_temperature[clear]
    rmse = float(np.sqrt(np.nanmean(diff**2)))
    assert rmse < 0.1


@pytest.mark.integration
def test_process_scene_links_catalogued_l1_source(
    l1_safe_dir: Path,
    catalogue: SqliteCatalogue,
    tmp_path: Path,
) -> None:
    # Register the L1 source first so process_scene links to the catalogued id.
    from datetime import UTC, datetime

    from pdgs.catalogue.models import Product

    now = datetime(2024, 6, 13, tzinfo=UTC)
    catalogue.register(
        Product(
            product_id="l1_rbt_synthetic",
            collection_id="EO:EUM:DAT:0411",
            product_type="SL_1_RBT",
            level="L1",
            timeliness="NTC",
            sensing_start=now,
            sensing_end=now,
            bbox=None,
            local_path=str(l1_safe_dir),
            checksum="abc",
            size_bytes=1,
            status=ProductStatus.REGISTERED,
            provenance=None,
            created_at=now,
            updated_at=now,
        )
    )

    cfg = load_config(_CONFIG_ROOT / "fixture.toml")
    derived = process_scene(l1_safe_dir, cfg, catalogue, tmp_path / "derived")
    assert derived.provenance.input_product_ids == ("l1_rbt_synthetic",)
