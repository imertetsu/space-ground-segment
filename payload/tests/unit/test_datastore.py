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
