"""Unit tests for the offline Data Store client and the client factory."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdgs.ingestion.datastore import (
    CONSUMER_KEY_ENV,
    CONSUMER_SECRET_ENV,
    FORCE_OFFLINE_ENV,
    EumdacClient,
    IngestionError,
    MissingCredentialsError,
    OfflineDataStoreClient,
    _filter_product_ids,
    _find_safe_dir,
    _matches_timeliness,
    make_client,
)

_L1 = "EO:EUM:DAT:0411"
_L2 = "EO:EUM:DAT:0412"
_WIDE_START = datetime(2000, 1, 1, tzinfo=UTC)
_WIDE_END = datetime(2100, 1, 1, tzinfo=UTC)


def test_search_discovers_l1_fixture(l1_safe_dir: Path) -> None:
    client = OfflineDataStoreClient(fixtures_dir=l1_safe_dir.parent)
    refs = client.search(_L1, _WIDE_START, _WIDE_END)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.product_id == "l1_rbt_synthetic"
    assert ref.collection_id == _L1
    assert ref.bbox is not None


def test_search_discovers_l2_fixture(l2_safe_dir: Path) -> None:
    client = OfflineDataStoreClient(fixtures_dir=l2_safe_dir.parent)
    refs = client.search(_L2, _WIDE_START, _WIDE_END)
    assert len(refs) == 1
    assert refs[0].product_id == "l2_wst_synthetic"


def test_search_unknown_collection_returns_empty(fixtures_dir: Path) -> None:
    client = OfflineDataStoreClient(fixtures_dir=fixtures_dir)
    assert client.search("EO:EUM:DAT:9999", _WIDE_START, _WIDE_END) == []


def test_search_window_excludes_non_overlapping(fixtures_dir: Path) -> None:
    client = OfflineDataStoreClient(fixtures_dir=fixtures_dir)
    # Fixture sensing window is 2024-06-13; a 2030 window must not discover it.
    far = datetime(2030, 1, 1, tzinfo=UTC)
    later = datetime(2030, 12, 31, tzinfo=UTC)
    assert client.search(_L1, far, later) == []


def test_download_copies_safe_folder(fixtures_dir: Path, tmp_path: Path) -> None:
    client = OfflineDataStoreClient(fixtures_dir=fixtures_dir)
    ref = client.search(_L1, _WIDE_START, _WIDE_END)[0]
    dest = client.download(ref, tmp_path)
    assert dest.is_dir()
    assert (dest / "S8_BT_in.nc").is_file()
    assert (dest / "geodetic_in.nc").is_file()
    assert (dest / "xfdumanifest.xml").is_file()


def test_download_unknown_collection_raises(fixtures_dir: Path, tmp_path: Path) -> None:
    from pdgs.ingestion.datastore import ProductRef

    client = OfflineDataStoreClient(fixtures_dir=fixtures_dir)
    bad = ProductRef("x", "EO:EUM:DAT:9999", _WIDE_START, _WIDE_END)
    with pytest.raises(IngestionError):
        client.download(bad, tmp_path)


def test_make_client_defaults_to_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CONSUMER_KEY_ENV, raising=False)
    monkeypatch.delenv(CONSUMER_SECRET_ENV, raising=False)
    monkeypatch.delenv(FORCE_OFFLINE_ENV, raising=False)
    assert isinstance(make_client(), OfflineDataStoreClient)


def test_make_client_offline_when_forced_even_with_creds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CONSUMER_KEY_ENV, "key")
    monkeypatch.setenv(CONSUMER_SECRET_ENV, "secret")
    monkeypatch.setenv(FORCE_OFFLINE_ENV, "1")
    assert isinstance(make_client(), OfflineDataStoreClient)


def test_eumdac_client_without_credentials_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(CONSUMER_KEY_ENV, raising=False)
    monkeypatch.delenv(CONSUMER_SECRET_ENV, raising=False)
    with pytest.raises(MissingCredentialsError):
        EumdacClient()


# --- Pure helpers used by EumdacClient.search/download (no live client) -------

_NT_ID = "S3A_SL_2_WST____20260515T223233_..._MAR_O_NT_F1.SEN3"
_NR_ID = "S3A_SL_2_WST____20260515T223233_..._MAR_O_NR_F1.SEN3"


def test_matches_timeliness_token() -> None:
    assert _matches_timeliness(_NT_ID, "NT") is True
    assert _matches_timeliness(_NR_ID, "NT") is False
    assert _matches_timeliness(_NR_ID, "NR") is True
    # A None filter accepts everything.
    assert _matches_timeliness(_NR_ID, None) is True


def test_filter_product_ids_keeps_only_requested_timeliness() -> None:
    ids = [_NT_ID, _NR_ID, "x_NT_y", "z_NR_w"]
    assert list(_filter_product_ids(ids, "NT")) == [_NT_ID, "x_NT_y"]
    assert list(_filter_product_ids(ids, None)) == ids


def test_filter_product_ids_then_limit_counts_kept_products() -> None:
    import itertools

    ids = [_NR_ID, _NT_ID, "a_NR_b", "c_NT_d", "e_NT_f"]
    # Filter to NT first, then take 2 -> the cap counts kept (NT) products only.
    kept = list(itertools.islice(_filter_product_ids(ids, "NT"), 2))
    assert kept == [_NT_ID, "c_NT_d"]


def test_find_safe_dir_locates_nested_sen3(tmp_path: Path) -> None:
    # Real extraction yields a nested <product_id>.SEN3 folder among other files.
    sen3 = tmp_path / "prod" / "S3A_SL_1_RBT____x.SEN3"
    sen3.mkdir(parents=True)
    (tmp_path / "prod" / "manifest.xml").write_text("x", encoding="utf-8")
    (tmp_path / "prod" / "browse.jpg").write_bytes(b"x")
    assert _find_safe_dir(tmp_path) == sen3


def test_find_safe_dir_when_root_is_sen3(tmp_path: Path) -> None:
    sen3 = tmp_path / "thing.SEN3"
    sen3.mkdir()
    assert _find_safe_dir(sen3) == sen3


def test_find_safe_dir_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(IngestionError):
        _find_safe_dir(tmp_path)


# --- EumdacClient.search / download against an in-memory fake (no network) -----


class _FakeProduct:
    def __init__(self, pid: str) -> None:
        self._pid = pid
        self.sensing_start = _WIDE_START
        self.sensing_end = _WIDE_END

    def __str__(self) -> str:
        return self._pid


class _FakeCollection:
    def __init__(self, products: list[_FakeProduct]) -> None:
        self._products = products
        self.last_search_kw: dict[str, object] = {}

    def search(self, **kw: object) -> list[_FakeProduct]:
        self.last_search_kw = kw
        return self._products


class _FakeDataStore:
    def __init__(self, collection: _FakeCollection) -> None:
        self._collection = collection

    def get_collection(self, collection_id: str) -> _FakeCollection:
        return self._collection


def _eumdac_client_with_fake(monkeypatch: pytest.MonkeyPatch) -> EumdacClient:
    """Build an EumdacClient whose __init__ creds + datastore are stubbed out."""
    monkeypatch.setenv(CONSUMER_KEY_ENV, "key")
    monkeypatch.setenv(CONSUMER_SECRET_ENV, "secret")
    monkeypatch.setattr(EumdacClient, "__init__", lambda self: None)
    return EumdacClient()


def test_eumdac_search_applies_geo_timeliness_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    products = [_FakeProduct(p) for p in (_NR_ID, _NT_ID, "a_NT_b", "c_NT_d")]
    collection = _FakeCollection(products)
    client = _eumdac_client_with_fake(monkeypatch)
    client._datastore = _FakeDataStore(collection)  # type: ignore[attr-defined]

    refs = client.search(
        _L2,
        _WIDE_START,
        _WIDE_END,
        geo="POLYGON((0 0,1 0,1 1,0 1,0 0))",
        timeliness="NT",
        limit=2,
    )

    # geo forwarded to eumdac; timeliness drops the NR product; limit caps to 2 NT.
    assert collection.last_search_kw["geo"] == "POLYGON((0 0,1 0,1 1,0 1,0 0))"
    assert [r.product_id for r in refs] == [_NT_ID, "a_NT_b"]
    assert all(r.collection_id == _L2 for r in refs)


def test_eumdac_search_plain_returns_all(monkeypatch: pytest.MonkeyPatch) -> None:
    products = [_FakeProduct(p) for p in (_NR_ID, _NT_ID)]
    collection = _FakeCollection(products)
    client = _eumdac_client_with_fake(monkeypatch)
    client._datastore = _FakeDataStore(collection)  # type: ignore[attr-defined]

    refs = client.search(_L2, _WIDE_START, _WIDE_END)
    assert {r.product_id for r in refs} == {_NR_ID, _NT_ID}
    assert "geo" not in collection.last_search_kw


class _FakeZipProduct:
    """A fake product whose .open() streams a zip containing a .SEN3 SAFE tree."""

    def __init__(self, zip_bytes: bytes) -> None:
        self._zip_bytes = zip_bytes

    def open(self) -> object:
        import io

        return io.BytesIO(self._zip_bytes)


class _FakeZipDataStore:
    def __init__(self, product: _FakeZipProduct) -> None:
        self._product = product

    def get_product(self, collection_id: str, product_id: str) -> _FakeZipProduct:
        return self._product


def _make_product_zip() -> bytes:
    """Build an in-memory zip mirroring a real product: a nested .SEN3 + extras."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("S3A_SL_1_RBT____x.SEN3/S8_BT_in.nc", b"netcdf-bytes")
        zf.writestr("S3A_SL_1_RBT____x.SEN3/geodetic_in.nc", b"netcdf-bytes")
        zf.writestr("manifest.xml", b"<manifest/>")
        zf.writestr("browse.jpg", b"jpeg")
    return buf.getvalue()


def test_eumdac_download_extracts_and_returns_sen3(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pdgs.ingestion.datastore import ProductRef

    client = _eumdac_client_with_fake(monkeypatch)
    client._datastore = _FakeZipDataStore(_FakeZipProduct(_make_product_zip()))  # type: ignore[attr-defined]

    ref = ProductRef("S3A_SL_1_RBT____x", _L1, _WIDE_START, _WIDE_END)
    safe = client.download(ref, tmp_path)

    assert safe.is_dir()
    assert safe.suffix == ".SEN3"
    assert (safe / "S8_BT_in.nc").is_file()
    assert (safe / "geodetic_in.nc").is_file()
    # The temporary download zip is removed after extraction.
    assert list(tmp_path.glob("*.zip")) == []
