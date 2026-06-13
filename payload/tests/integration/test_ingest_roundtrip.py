"""Integration tests — OFFLINE ingest round-trip over committed fixtures.

Exercises the full discover -> download -> verify -> register chain
(REQ-ING-01/02/04) against the synthetic SAFE fixtures, asserting catalogue records
persist and their checksums verify (REQ-ING-03).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdgs.catalogue.models import ProductStatus
from pdgs.catalogue.repository import SqliteCatalogue
from pdgs.ingestion.datastore import OfflineDataStoreClient
from pdgs.ingestion.ingest import ingest
from pdgs.ingestion.integrity import verify_integrity

_L1 = "EO:EUM:DAT:0411"
_L2 = "EO:EUM:DAT:0412"
_START = datetime(2000, 1, 1, tzinfo=UTC)
_END = datetime(2100, 1, 1, tzinfo=UTC)


@pytest.fixture
def client(fixtures_dir: Path) -> OfflineDataStoreClient:
    return OfflineDataStoreClient(fixtures_dir=fixtures_dir)


@pytest.fixture
def catalogue(tmp_path: Path) -> SqliteCatalogue:
    return SqliteCatalogue(tmp_path / "catalogue.sqlite")


@pytest.mark.integration
def test_ingest_l1_roundtrip_registers_and_verifies(
    client: OfflineDataStoreClient,
    catalogue: SqliteCatalogue,
    tmp_path: Path,
) -> None:
    result = ingest(client, _L1, _START, _END, catalogue, dest_dir=tmp_path / "dl")
    assert result.registered == ["l1_rbt_synthetic"]
    assert result.failed == []

    product = catalogue.get("l1_rbt_synthetic")
    assert product is not None
    assert product.status is ProductStatus.REGISTERED
    assert product.product_type == "SL_1_RBT"
    assert product.level == "L1"
    assert product.timeliness == "NTC"
    assert product.size_bytes > 0
    assert product.checksum
    # The persisted checksum verifies against the downloaded product (REQ-ING-03).
    assert verify_integrity(product.local_path, product.checksum) is True


@pytest.mark.integration
def test_ingest_l2_roundtrip_registers(
    client: OfflineDataStoreClient,
    catalogue: SqliteCatalogue,
    tmp_path: Path,
) -> None:
    result = ingest(client, _L2, _START, _END, catalogue, dest_dir=tmp_path / "dl")
    assert result.registered == ["l2_wst_synthetic"]
    product = catalogue.get("l2_wst_synthetic")
    assert product is not None
    assert product.status is ProductStatus.REGISTERED
    assert product.product_type == "SL_2_WST"
    assert product.level == "L2"
    assert verify_integrity(product.local_path, product.checksum) is True


@pytest.mark.integration
def test_ingest_both_collections_persist(
    client: OfflineDataStoreClient,
    catalogue: SqliteCatalogue,
    tmp_path: Path,
) -> None:
    for collection in (_L1, _L2):
        ingest(client, collection, _START, _END, catalogue, dest_dir=tmp_path / "dl")
    registered = catalogue.list(status=ProductStatus.REGISTERED)
    ids = sorted(p.product_id for p in registered)
    assert ids == ["l1_rbt_synthetic", "l2_wst_synthetic"]


@pytest.mark.integration
def test_ingest_corrupt_download_routes_to_failed(
    catalogue: SqliteCatalogue,
    fixtures_dir: Path,
    tmp_path: Path,
) -> None:
    # A client whose download yields a non-existent path => verification fails =>
    # the product is dead-lettered (FAILED) rather than registered.
    from pdgs.ingestion.datastore import ProductRef

    class BrokenClient(OfflineDataStoreClient):
        def download(self, ref: ProductRef, dest_dir: Path) -> Path:  # type: ignore[override]
            super().download(ref, dest_dir)
            # Return a path that does not exist so integrity verification fails.
            return dest_dir / "missing-product"

    broken = BrokenClient(fixtures_dir=fixtures_dir)
    result = ingest(broken, _L1, _START, _END, catalogue, dest_dir=tmp_path / "dl")
    assert result.registered == []
    assert result.failed == ["l1_rbt_synthetic"]
    product = catalogue.get("l1_rbt_synthetic")
    assert product is not None
    assert product.status is ProductStatus.FAILED
