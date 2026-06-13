"""Derived L2 SST product model, netCDF writer, and orchestration — FROZEN (Phase 2).

This module freezes the **product / provenance model** that Phase 3 (validation)
and the ``viz`` consumer read:

* :class:`DerivedSstProduct` — the in-memory derived SST product (SST + masks +
  geolocation + provenance + coefficient-set id + source product id).
* :func:`write_derived_product` — writes a CF-ish netCDF carrying the data fields
  and the full provenance block as global attributes (REQ-PRO-03, REQ-CFG-02).
* :func:`process_scene` — orchestration: read L1 → cloud screen → retrieve SST →
  stamp :class:`~pdgs.catalogue.models.Provenance` → write netCDF → register a
  ``L2_DERIVED`` :class:`~pdgs.catalogue.models.Product` (status PROCESSED).

The two processors (:func:`~pdgs.processing.cloud_screening.screen.screen_clouds`,
:func:`~pdgs.processing.sst_retrieval.retrieve.retrieve_sst`) are pure and have no
cross-import (REQ-PRO-04); this orchestrator composes them.

SIMPLIFICATION: the derived SST uses a simplified split-window with a cited,
non-operational coefficient set (see :mod:`pdgs.config.processing`); it is NOT the
operational SLSTR SST product.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt
from netCDF4 import Dataset

from pdgs.catalogue.models import Product, ProductLevel, ProductStatus, Provenance
from pdgs.catalogue.repository import Catalogue
from pdgs.config.processing import ProcessingConfig
from pdgs.config.version import PROCESSOR_VERSION
from pdgs.ingestion.readers import L1Scene, read_l1_rbt
from pdgs.processing.cloud_screening.screen import screen_clouds
from pdgs.processing.sst_retrieval.retrieve import retrieve_sst

# Catalogue classification for products this pipeline derives.
_DERIVED_LEVEL: ProductLevel = "L2_DERIVED"
_DERIVED_PRODUCT_TYPE = "SST_L2_DERIVED"
_DERIVED_COLLECTION = "PDGS:DERIVED:SST"
_TIMELINESS = "NTC"


@dataclass(frozen=True)
class DerivedSstProduct:
    """In-memory derived L2 SST product (FROZEN — Phase 3 + viz consume it).

    ``sea_surface_temperature`` is in Kelvin (NaN over cloudy pixels). ``cloud_mask``
    (True = cloud) and ``out_of_range`` (True = SST outside the valid range, flagged
    not clamped — REQ-PRO-05) accompany it. ``provenance`` carries the auditable run
    metadata (REQ-PRO-03); ``coefficient_set_id`` and ``source_product_id`` record
    which coefficients and which L1 scene produced it.
    """

    product_id: str
    sea_surface_temperature: npt.NDArray[np.float32]
    cloud_mask: npt.NDArray[np.bool_]
    out_of_range: npt.NDArray[np.bool_]
    latitudes: npt.NDArray[np.float32]
    longitudes: npt.NDArray[np.float32]
    provenance: Provenance
    coefficient_set_id: str
    source_product_id: str

    @property
    def shape(self) -> tuple[int, ...]:
        """Pixel grid shape (rows, cols) of the derived SST field."""
        return self.sea_surface_temperature.shape


def _derived_product_id(source_product_id: str) -> str:
    """Derive a stable product id for the SST product from its L1 source id."""
    return f"{source_product_id}__SST_L2_DERIVED"


def write_derived_product(product: DerivedSstProduct, out_dir: str | Path) -> Path:
    """Write ``product`` to a CF-ish netCDF under ``out_dir``; return the path.

    Variables: ``sea_surface_temperature`` (K), ``cloud_mask`` (0/1),
    ``out_of_range`` (0/1), ``lat``, ``lon``. The full provenance block is written
    as global attributes (``processor_version``, ``config_version``,
    ``input_product_ids``, ``coefficient_set_id``, ``run_timestamp``) per
    REQ-PRO-03 / REQ-CFG-02. The product is marked derived L2 (``title``,
    ``processing_level``), and labelled a documented simplification.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{product.product_id}.nc"

    sst = np.asarray(product.sea_surface_temperature, dtype=np.float32)
    rows, cols = sst.shape

    with Dataset(path, "w", format="NETCDF4") as ds:
        ds.title = (
            "PDGS derived L2 Sea Surface Temperature (SIMPLIFIED split-window — NOT operational)"
        )
        ds.processing_level = "L2"
        ds.product_type = _DERIVED_PRODUCT_TYPE
        ds.Conventions = "CF-1.7"
        ds.comment = (
            "Derived from L1 SLSTR S8/S9 via a simplified split-window (cited, "
            "non-operational coefficients). A simplification, never operational."
        )
        ds.source = "Sentinel-3 SLSTR SL_1_RBT (nadir TIR S8/S9)"
        # --- Provenance as global attributes (REQ-PRO-03, REQ-CFG-02) ---
        prov = product.provenance
        ds.processor_version = prov.processor_version
        ds.config_version = prov.config_version
        ds.input_product_ids = ",".join(prov.input_product_ids)
        ds.coefficient_set_id = product.coefficient_set_id
        ds.source_product_id = product.source_product_id
        ds.run_timestamp = prov.run_timestamp.astimezone(UTC).isoformat()

        ds.createDimension("rows", rows)
        ds.createDimension("columns", cols)

        sst_v = ds.createVariable("sea_surface_temperature", "f4", ("rows", "columns"), zlib=True)
        sst_v.units = "K"
        sst_v.long_name = "derived sea surface temperature (simplified split-window)"
        sst_v.standard_name = "sea_surface_temperature"
        sst_v[:, :] = sst

        cloud_v = ds.createVariable("cloud_mask", "i1", ("rows", "columns"), zlib=True)
        cloud_v.long_name = "cloud mask (1 = cloud, threshold-based simplification)"
        cloud_v.flag_values = np.array([0, 1], dtype=np.int8)
        cloud_v.flag_meanings = "clear cloud"
        cloud_v[:, :] = np.asarray(product.cloud_mask, dtype=np.int8)

        oor_v = ds.createVariable("out_of_range", "i1", ("rows", "columns"), zlib=True)
        oor_v.long_name = "SST out-of-range flag (1 = outside configured valid range)"
        oor_v.flag_values = np.array([0, 1], dtype=np.int8)
        oor_v.flag_meanings = "in_range out_of_range"
        oor_v[:, :] = np.asarray(product.out_of_range, dtype=np.int8)

        lat_v = ds.createVariable("lat", "f4", ("rows", "columns"), zlib=True)
        lat_v.units = "degrees_north"
        lat_v.long_name = "latitude"
        lat_v.standard_name = "latitude"
        lat_v[:, :] = np.asarray(product.latitudes, dtype=np.float32)

        lon_v = ds.createVariable("lon", "f4", ("rows", "columns"), zlib=True)
        lon_v.units = "degrees_east"
        lon_v.long_name = "longitude"
        lon_v.standard_name = "longitude"
        lon_v[:, :] = np.asarray(product.longitudes, dtype=np.float32)

    return path


def _find_source_l1_id(catalogue: Catalogue, scene: L1Scene) -> str:
    """Return the catalogued L1 product id matching ``scene`` (else the scene id).

    Looks up the L1 ``SL_1_RBT`` products in the catalogue and links by product id
    (the scene id is the SAFE folder name, which the ingester registers as the
    product id). Falls back to the scene's own product id if not yet catalogued.
    """
    for product in catalogue.list(product_type="SL_1_RBT"):
        if product.product_id == scene.product_id:
            return product.product_id
    return scene.product_id


def process_scene(
    l1_safe_dir: str | Path,
    cfg: ProcessingConfig,
    catalogue: Catalogue,
    out_dir: str | Path,
) -> DerivedSstProduct:
    """Process one L1 scene end-to-end into a registered derived SST product.

    Reads the L1 SAFE folder, runs cloud screening then SST retrieval, stamps a
    :class:`~pdgs.catalogue.models.Provenance` block (REQ-PRO-03 — input product
    ids, processor + config versions, run timestamp), writes a derived netCDF
    (:func:`write_derived_product`), and registers a ``L2_DERIVED`` product with
    status ``PROCESSED`` and the provenance attached. Returns the in-memory
    :class:`DerivedSstProduct`.
    """
    scene = read_l1_rbt(l1_safe_dir)
    source_product_id = _find_source_l1_id(catalogue, scene)

    cloud_mask = screen_clouds(scene, cfg.cloud)
    sst_result = retrieve_sst(scene, cloud_mask, cfg.sst)

    run_timestamp = datetime.now(tz=UTC)
    provenance = Provenance(
        processor_version=PROCESSOR_VERSION,
        config_version=cfg.config_version,
        input_product_ids=(source_product_id,),
        run_timestamp=run_timestamp,
    )

    product_id = _derived_product_id(source_product_id)
    derived = DerivedSstProduct(
        product_id=product_id,
        sea_surface_temperature=sst_result.sst_k,
        cloud_mask=cloud_mask,
        out_of_range=sst_result.out_of_range,
        latitudes=scene.latitudes,
        longitudes=scene.longitudes,
        provenance=provenance,
        coefficient_set_id=cfg.sst.coefficient_set_id,
        source_product_id=source_product_id,
    )

    local_path = write_derived_product(derived, out_dir)

    catalogue.register(
        Product(
            product_id=product_id,
            collection_id=_DERIVED_COLLECTION,
            product_type=_DERIVED_PRODUCT_TYPE,
            level=_DERIVED_LEVEL,
            timeliness=_TIMELINESS,
            sensing_start=scene.sensing_start,
            sensing_end=scene.sensing_end,
            bbox=None,
            local_path=str(local_path),
            checksum="",
            size_bytes=local_path.stat().st_size,
            status=ProductStatus.PROCESSED,
            provenance=provenance,
            created_at=run_timestamp,
            updated_at=run_timestamp,
        )
    )

    return derived
