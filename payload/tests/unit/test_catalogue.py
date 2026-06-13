"""Unit tests for the catalogue repository (REQ-ING-04)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdgs.catalogue.models import Product, ProductStatus, Provenance
from pdgs.catalogue.repository import CatalogueError, SqliteCatalogue


def _utc(year: int = 2024, month: int = 6, day: int = 13) -> datetime:
    return datetime(year, month, day, 10, 0, 0, tzinfo=UTC)


def _make_product(product_id: str = "PROD-1", **overrides: object) -> Product:
    base: dict[str, object] = {
        "product_id": product_id,
        "collection_id": "EO:EUM:DAT:0411",
        "product_type": "SL_1_RBT",
        "level": "L1",
        "timeliness": "NTC",
        "sensing_start": _utc(),
        "sensing_end": _utc(),
        "bbox": (-30.0, 40.0, -28.5, 41.0),
        "local_path": "/data/products/PROD-1",
        "checksum": "abc123",
        "size_bytes": 1024,
        "status": ProductStatus.REGISTERED,
        "provenance": None,
        "created_at": _utc(),
        "updated_at": _utc(),
    }
    base.update(overrides)
    return Product(**base)  # type: ignore[arg-type]


@pytest.fixture
def catalogue(tmp_path: Path) -> SqliteCatalogue:
    return SqliteCatalogue(tmp_path / "catalogue.sqlite")


def test_init_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "cat.sqlite"
    SqliteCatalogue(db)
    # Constructing again over the same file must not error.
    second = SqliteCatalogue(db)
    assert second.list() == []


def test_register_and_get_roundtrip(catalogue: SqliteCatalogue) -> None:
    product = _make_product()
    catalogue.register(product)
    fetched = catalogue.get("PROD-1")
    assert fetched is not None
    assert fetched.product_id == "PROD-1"
    assert fetched.collection_id == "EO:EUM:DAT:0411"
    assert fetched.bbox == (-30.0, 40.0, -28.5, 41.0)
    assert fetched.status is ProductStatus.REGISTERED
    assert fetched.sensing_start == _utc()


def test_get_missing_returns_none(catalogue: SqliteCatalogue) -> None:
    assert catalogue.get("NOPE") is None


def test_register_is_upsert(catalogue: SqliteCatalogue) -> None:
    catalogue.register(_make_product(status=ProductStatus.DISCOVERED))
    catalogue.register(_make_product(status=ProductStatus.REGISTERED))
    fetched = catalogue.get("PROD-1")
    assert fetched is not None
    assert fetched.status is ProductStatus.REGISTERED
    assert len(catalogue.list()) == 1


def test_list_filters_by_status(catalogue: SqliteCatalogue) -> None:
    catalogue.register(_make_product("A", status=ProductStatus.REGISTERED))
    catalogue.register(_make_product("B", status=ProductStatus.FAILED))
    registered = catalogue.list(status=ProductStatus.REGISTERED)
    assert [p.product_id for p in registered] == ["A"]
    failed = catalogue.list(status=ProductStatus.FAILED)
    assert [p.product_id for p in failed] == ["B"]


def test_list_filters_by_product_type(catalogue: SqliteCatalogue) -> None:
    catalogue.register(_make_product("L1", product_type="SL_1_RBT"))
    catalogue.register(
        _make_product(
            "L2",
            product_type="SL_2_WST",
            collection_id="EO:EUM:DAT:0412",
            level="L2",
        )
    )
    wst = catalogue.list(product_type="SL_2_WST")
    assert [p.product_id for p in wst] == ["L2"]


def test_update_status(catalogue: SqliteCatalogue) -> None:
    catalogue.register(_make_product(status=ProductStatus.DISCOVERED))
    catalogue.update_status("PROD-1", ProductStatus.VERIFIED)
    fetched = catalogue.get("PROD-1")
    assert fetched is not None
    assert fetched.status is ProductStatus.VERIFIED


def test_update_status_unknown_raises(catalogue: SqliteCatalogue) -> None:
    with pytest.raises(CatalogueError):
        catalogue.update_status("MISSING", ProductStatus.FAILED)


def test_set_provenance(catalogue: SqliteCatalogue) -> None:
    catalogue.register(_make_product())
    prov = Provenance(
        processor_version="1.2.3",
        config_version="0.4.0",
        input_product_ids=("SRC-A", "SRC-B"),
        run_timestamp=_utc(),
    )
    catalogue.set_provenance("PROD-1", prov)
    fetched = catalogue.get("PROD-1")
    assert fetched is not None
    assert fetched.provenance is not None
    assert fetched.provenance.processor_version == "1.2.3"
    assert fetched.provenance.input_product_ids == ("SRC-A", "SRC-B")
    assert fetched.provenance.run_timestamp == _utc()


def test_set_provenance_unknown_raises(catalogue: SqliteCatalogue) -> None:
    prov = Provenance("1.0.0", "0.0.0", (), _utc())
    with pytest.raises(CatalogueError):
        catalogue.set_provenance("MISSING", prov)


def test_bbox_none_roundtrip(catalogue: SqliteCatalogue) -> None:
    catalogue.register(_make_product(bbox=None))
    fetched = catalogue.get("PROD-1")
    assert fetched is not None
    assert fetched.bbox is None
