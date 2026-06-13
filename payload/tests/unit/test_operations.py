"""Unit tests for the operations layer — dead-letter + reprocess (REQ-OPS-01/02).

Exercise the orchestration in :mod:`pdgs.operations.reprocess` directly (without the
CLI argparse layer): dead-letter listing, source-L1 resolution for derived/L1/FAILED
products, on-demand reprocessing refreshing the record in place, optional
re-validation, and clear errors on an unknown/unresolvable id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdgs.catalogue.models import Product, ProductStatus
from pdgs.catalogue.repository import SqliteCatalogue
from pdgs.config.processing import ProcessingConfig, load_config
from pdgs.ingestion.datastore import OfflineDataStoreClient
from pdgs.ingestion.ingest import ingest
from pdgs.operations.reprocess import (
    ReprocessError,
    list_dead_letter,
    reprocess_product,
    resolve_source_l1_dir,
)
from pdgs.processing.product import process_scene

_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"
_L1_COLLECTION = "EO:EUM:DAT:0411"
_L2_COLLECTION = "EO:EUM:DAT:0412"
_WINDOW_START = datetime(2000, 1, 1, tzinfo=UTC)
_WINDOW_END = datetime(2100, 1, 1, tzinfo=UTC)


@pytest.fixture
def catalogue(tmp_path: Path) -> SqliteCatalogue:
    return SqliteCatalogue(tmp_path / "catalogue.sqlite")


@pytest.fixture
def cfg() -> ProcessingConfig:
    return load_config(_CONFIG_ROOT / "fixture.toml")


def _ingest_l1(catalogue: SqliteCatalogue, fixtures_dir: Path, dest: Path) -> None:
    """Ingest the synthetic L1 fixture so it is a catalogued source product."""
    client = OfflineDataStoreClient(fixtures_dir=fixtures_dir)
    ingest(client, _L1_COLLECTION, _WINDOW_START, _WINDOW_END, catalogue, dest_dir=dest)


def _failed_stub(product_id: str) -> Product:
    now = datetime(2024, 6, 1, tzinfo=UTC)
    return Product(
        product_id=product_id,
        collection_id=_L1_COLLECTION,
        product_type="SL_1_RBT",
        level="L1",
        timeliness="NTC",
        sensing_start=now,
        sensing_end=now,
        bbox=None,
        local_path="",
        checksum="",
        size_bytes=0,
        status=ProductStatus.FAILED,
        provenance=None,
        created_at=now,
        updated_at=now,
    )


# --- dead-letter listing (REQ-OPS-01) --------------------------------------


def test_list_dead_letter_empty(catalogue: SqliteCatalogue) -> None:
    assert list_dead_letter(catalogue) == []


def test_list_dead_letter_returns_failed_products(catalogue: SqliteCatalogue) -> None:
    catalogue.register(_failed_stub("broken-l1"))
    failed = list_dead_letter(catalogue)
    assert [p.product_id for p in failed] == ["broken-l1"]
    assert failed[0].status is ProductStatus.FAILED


def test_list_dead_letter_excludes_healthy_products(
    catalogue: SqliteCatalogue, fixtures_dir: Path, tmp_path: Path
) -> None:
    _ingest_l1(catalogue, fixtures_dir, tmp_path / "dl")
    catalogue.register(_failed_stub("broken-l1"))
    failed = list_dead_letter(catalogue)
    # Only the FAILED product is dead-lettered, not the REGISTERED L1.
    assert [p.product_id for p in failed] == ["broken-l1"]


# --- source-L1 resolution --------------------------------------------------


def test_resolve_for_l1_product_uses_its_local_path(
    catalogue: SqliteCatalogue, fixtures_dir: Path, tmp_path: Path
) -> None:
    _ingest_l1(catalogue, fixtures_dir, tmp_path / "dl")
    source_id, l1_dir = resolve_source_l1_dir(catalogue, "l1_rbt_synthetic")
    assert source_id == "l1_rbt_synthetic"
    assert l1_dir.is_dir()


def test_resolve_for_derived_product_routes_through_provenance(
    catalogue: SqliteCatalogue, fixtures_dir: Path, tmp_path: Path, cfg: ProcessingConfig
) -> None:
    _ingest_l1(catalogue, fixtures_dir, tmp_path / "dl")
    derived = process_scene(
        catalogue.get("l1_rbt_synthetic").local_path,  # type: ignore[union-attr]
        cfg,
        catalogue,
        tmp_path / "out",
    )
    source_id, l1_dir = resolve_source_l1_dir(catalogue, derived.product_id)
    assert source_id == "l1_rbt_synthetic"
    assert l1_dir.is_dir()


def test_resolve_unknown_id_raises(catalogue: SqliteCatalogue) -> None:
    with pytest.raises(ReprocessError, match="unknown product id"):
        resolve_source_l1_dir(catalogue, "does-not-exist")


def test_resolve_failed_ingestion_without_local_path_raises(catalogue: SqliteCatalogue) -> None:
    # A dead-lettered ingestion has no local product to reprocess from.
    catalogue.register(_failed_stub("broken-l1"))
    with pytest.raises(ReprocessError, match="no local path"):
        resolve_source_l1_dir(catalogue, "broken-l1")


# --- on-demand reprocessing (REQ-OPS-02) -----------------------------------


def test_reprocess_derived_refreshes_record_in_place(
    catalogue: SqliteCatalogue, fixtures_dir: Path, tmp_path: Path, cfg: ProcessingConfig
) -> None:
    _ingest_l1(catalogue, fixtures_dir, tmp_path / "dl")
    l1_path = catalogue.get("l1_rbt_synthetic").local_path  # type: ignore[union-attr]
    derived = process_scene(l1_path, cfg, catalogue, tmp_path / "out")
    product_id = derived.product_id

    # Advance past PROCESSED to prove the reprocess resets the record.
    catalogue.update_status(product_id, ProductStatus.VALIDATED)

    outcome = reprocess_product(catalogue, product_id, cfg, tmp_path / "out2")
    assert outcome.source_l1_id == "l1_rbt_synthetic"
    assert outcome.derived.product_id == product_id
    assert outcome.validation is None

    # No duplicate row; the single record is refreshed back to PROCESSED.
    derived_rows = catalogue.list(product_type="SST_L2_DERIVED")
    assert len(derived_rows) == 1
    assert derived_rows[0].status is ProductStatus.PROCESSED


def test_reprocess_with_validation_passes_on_fixtures(
    catalogue: SqliteCatalogue,
    fixtures_dir: Path,
    l2_safe_dir: Path,
    tmp_path: Path,
    cfg: ProcessingConfig,
) -> None:
    _ingest_l1(catalogue, fixtures_dir, tmp_path / "dl")
    l1_path = catalogue.get("l1_rbt_synthetic").local_path  # type: ignore[union-attr]
    derived = process_scene(l1_path, cfg, catalogue, tmp_path / "out")

    outcome = reprocess_product(
        catalogue,
        derived.product_id,
        cfg,
        tmp_path / "out2",
        reference_l2_dir=l2_safe_dir,
        reports_dir=tmp_path / "reports",
        synthetic_inputs=True,
    )
    assert outcome.validation is not None
    assert outcome.validation.passed is True
    assert (tmp_path / "reports" / "validation.json").is_file()
    # A PASS advances the derived record to VALIDATED.
    refreshed = catalogue.get(derived.product_id)
    assert refreshed is not None
    assert refreshed.status is ProductStatus.VALIDATED


def test_reprocess_unknown_id_raises(catalogue: SqliteCatalogue, cfg: ProcessingConfig) -> None:
    with pytest.raises(ReprocessError, match="unknown product id"):
        reprocess_product(catalogue, "nope", cfg, "out")


def test_reprocess_l1_product_directly(
    catalogue: SqliteCatalogue, fixtures_dir: Path, tmp_path: Path, cfg: ProcessingConfig
) -> None:
    _ingest_l1(catalogue, fixtures_dir, tmp_path / "dl")
    # Reprocessing the L1 product id directly derives a fresh SST product.
    outcome = reprocess_product(catalogue, "l1_rbt_synthetic", cfg, tmp_path / "out")
    assert outcome.source_l1_id == "l1_rbt_synthetic"
    assert outcome.derived.product_id == "l1_rbt_synthetic__SST_L2_DERIVED"
