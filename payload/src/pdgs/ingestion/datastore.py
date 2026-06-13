"""Data Store client abstraction (REQ-ING-01/02).

Defines the :class:`DataStoreClient` interface (discover + download), the
:class:`ProductRef` discovery result, and two implementations:

* :class:`OfflineDataStoreClient` — discovers/downloads from a local fixtures
  directory of synthetic SAFE products. This is the **default** and what tests use
  (no network, no credentials).
* :class:`EumdacClient` — wraps ``eumdac`` against the real EUMETSAT Data Store.
  Structurally complete but NOT exercised now (no credentials); a missing-credential
  path raises a clear, typed :class:`MissingCredentialsError`.

The :func:`make_client` factory returns the offline client unless credentials are
present AND offline is not forced — i.e. **OFFLINE by default**. Swapping to real
downloads later is a credential + flag change, not a code change at call sites.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import shutil
import tempfile
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from pdgs.catalogue.models import BBox

# Environment variables that carry EUMETSAT Data Store API credentials.
CONSUMER_KEY_ENV = "EUMETSAT_CONSUMER_KEY"
CONSUMER_SECRET_ENV = "EUMETSAT_CONSUMER_SECRET"

# Environment variable that forces offline mode even if credentials are present.
FORCE_OFFLINE_ENV = "PDGS_FORCE_OFFLINE"


class IngestionError(RuntimeError):
    """Base class for ingestion failures."""


class MissingCredentialsError(IngestionError):
    """Raised when the eumdac client is used without Data Store credentials."""


@dataclass(frozen=True)
class ProductRef:
    """A lightweight reference to a discoverable product (pre-download).

    Returned by :meth:`DataStoreClient.search`; resolved to a local SAFE folder by
    :meth:`DataStoreClient.download`. ``bbox`` is the optional footprint
    (west, south, east, north) in degrees.
    """

    product_id: str
    collection_id: str
    sensing_start: datetime
    sensing_end: datetime
    bbox: BBox | None = None


class DataStoreClient(ABC):
    """Discover + download products from a Data Store (real or offline)."""

    @abstractmethod
    def search(
        self,
        collection_id: str,
        start: datetime,
        end: datetime,
        **kw: Any,
    ) -> list[ProductRef]:
        """Discover products in ``collection_id`` over the ``[start, end]`` window."""

    @abstractmethod
    def download(self, ref: ProductRef, dest_dir: Path) -> Path:
        """Download/resolve ``ref`` into ``dest_dir``; return the product's local path."""


def has_credentials() -> bool:
    """Return ``True`` if both EUMETSAT credential env vars are set and non-empty."""
    return bool(os.environ.get(CONSUMER_KEY_ENV)) and bool(os.environ.get(CONSUMER_SECRET_ENV))


def _matches_timeliness(product_id: str, timeliness: str | None) -> bool:
    """Return ``True`` if ``product_id`` carries the ``_<timeliness>_`` token.

    Sentinel-3 product ids embed the timeliness as a delimited token, e.g.
    ``..._NT_...`` (NTC, what the PDGS wants) or ``..._NR_...`` (NRT). A ``None``
    timeliness disables the filter (everything matches).
    """
    if timeliness is None:
        return True
    return f"_{timeliness}_" in product_id


def _filter_product_ids(product_ids: Iterable[str], timeliness: str | None) -> Iterator[str]:
    """Yield only the product ids matching ``timeliness`` (pure, testable helper)."""
    return (pid for pid in product_ids if _matches_timeliness(pid, timeliness))


def _find_safe_dir(extracted_root: Path) -> Path:
    """Return the inner ``*.SEN3`` SAFE directory under an extracted product tree.

    Real products extract to a tree that contains a ``<product_id>.SEN3/`` folder
    (the SAFE dir holding the netCDFs), possibly nested below intermediate folders.
    The shallowest ``*.SEN3`` directory found is returned.
    """
    if extracted_root.is_dir() and extracted_root.suffix == ".SEN3":
        return extracted_root
    candidates = sorted(
        (p for p in extracted_root.rglob("*.SEN3") if p.is_dir()),
        key=lambda p: len(p.relative_to(extracted_root).parts),
    )
    if not candidates:
        raise IngestionError(f"no .SEN3 SAFE directory found under: {extracted_root}")
    return candidates[0]


def make_client(
    *,
    fixtures_dir: Path | None = None,
    force_offline: bool | None = None,
) -> DataStoreClient:
    """Return a :class:`DataStoreClient`, defaulting to OFFLINE.

    Returns an :class:`EumdacClient` only when credentials are present AND offline
    is not forced; otherwise an :class:`OfflineDataStoreClient`. ``force_offline``
    defaults to the ``PDGS_FORCE_OFFLINE`` env var being truthy.
    """
    if force_offline is None:
        force_offline = bool(os.environ.get(FORCE_OFFLINE_ENV))
    if not force_offline and has_credentials():
        return EumdacClient()
    return OfflineDataStoreClient(fixtures_dir=fixtures_dir)


class OfflineDataStoreClient(DataStoreClient):
    """Offline Data Store backed by a local fixtures directory.

    "Discovery" scans the fixtures directory for SAFE folders matching the
    collection's product type; "download" copies the matched SAFE folder into the
    destination directory. This mirrors the real client's contract exactly so the
    orchestration code is identical online and offline.
    """

    #: Map collection id -> (product_type, fixture sub-directory name).
    _COLLECTION_FIXTURES: ClassVar[dict[str, tuple[str, str]]] = {
        "EO:EUM:DAT:0411": ("SL_1_RBT", "l1_rbt_synthetic"),
        "EO:EUM:DAT:0412": ("SL_2_WST", "l2_wst_synthetic"),
    }

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self.fixtures_dir: Path = (
            fixtures_dir if fixtures_dir is not None else _default_fixtures_dir()
        )

    def search(
        self,
        collection_id: str,
        start: datetime,
        end: datetime,
        **kw: Any,
    ) -> list[ProductRef]:
        mapping = self._COLLECTION_FIXTURES.get(collection_id)
        if mapping is None:
            return []
        _product_type, subdir = mapping
        safe_dir = self.fixtures_dir / subdir
        if not safe_dir.is_dir():
            return []
        sensing_start, sensing_end, bbox = _read_fixture_metadata(safe_dir)
        # Honour the requested window: only "discover" if the fixture overlaps it.
        if sensing_end < start or sensing_start > end:
            return []
        return [
            ProductRef(
                product_id=safe_dir.name,
                collection_id=collection_id,
                sensing_start=sensing_start,
                sensing_end=sensing_end,
                bbox=bbox,
            )
        ]

    def download(self, ref: ProductRef, dest_dir: Path) -> Path:
        mapping = self._COLLECTION_FIXTURES.get(ref.collection_id)
        if mapping is None:
            raise IngestionError(f"unknown collection for offline download: {ref.collection_id!r}")
        _, subdir = mapping
        src = self.fixtures_dir / subdir
        if not src.is_dir():
            raise IngestionError(f"fixture not found: {src}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / ref.product_id
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        return dest


class EumdacClient(DataStoreClient):
    """Real EUMETSAT Data Store client wrapping ``eumdac``.

    Reads credentials from ``EUMETSAT_CONSUMER_KEY`` / ``EUMETSAT_CONSUMER_SECRET``.
    Structurally complete but not exercised in Phase 1 (no credentials available):
    construction raises :class:`MissingCredentialsError` when either env var is
    missing, so callers fail clearly rather than hitting an opaque auth error later.
    """

    def __init__(self) -> None:
        key = os.environ.get(CONSUMER_KEY_ENV)
        secret = os.environ.get(CONSUMER_SECRET_ENV)
        if not key or not secret:
            raise MissingCredentialsError(
                "EUMETSAT Data Store credentials missing: set "
                f"{CONSUMER_KEY_ENV} and {CONSUMER_SECRET_ENV}. "
                "Use the offline client (the default) for fixture-based work."
            )
        # Imported lazily so the module loads without eumdac credentials/runtime.
        from eumdac.datastore import DataStore
        from eumdac.token import AccessToken

        self._token = AccessToken((key, secret))
        self._datastore = DataStore(self._token)

    def search(
        self,
        collection_id: str,
        start: datetime,
        end: datetime,
        *,
        geo: str | None = None,
        timeliness: str | None = None,
        limit: int | None = None,
        **kw: Any,
    ) -> list[ProductRef]:
        """Discover products, honouring optional AOI / timeliness / limit filters.

        * ``geo`` — a WKT polygon passed straight to ``eumdac`` as a spatial filter.
        * ``timeliness`` — keep only products whose id carries ``_<timeliness>_``
          (e.g. ``"NT"`` for NTC); applied client-side after the eumdac search.
        * ``limit`` — cap the number of returned refs (applied to the filtered
          stream so the cap counts kept products).
        """
        collection = self._datastore.get_collection(collection_id)
        search_kw: dict[str, Any] = dict(kw)
        if geo is not None:
            search_kw["geo"] = geo
        results = collection.search(dtstart=start, dtend=end, **search_kw)

        kept: Iterator[Any] = (
            product for product in results if _matches_timeliness(str(product), timeliness)
        )
        if limit is not None:
            kept = itertools.islice(kept, limit)

        refs: list[ProductRef] = []
        for product in kept:
            refs.append(
                ProductRef(
                    product_id=str(product),
                    collection_id=collection_id,
                    sensing_start=product.sensing_start,
                    sensing_end=product.sensing_end,
                    bbox=None,
                )
            )
        return refs

    def download(self, ref: ProductRef, dest_dir: Path) -> Path:
        """Download ``ref`` as a zip, extract it, and return the inner SAFE dir.

        Real ``SL_1_RBT`` / ``SL_2_WST`` products arrive as a zip whose extraction
        yields a ``<product_id>.SEN3/`` SAFE directory (containing the netCDFs)
        alongside the manifest/browse files. The product stream is written to a
        temporary ``.zip``, extracted into ``dest_dir``, the temp zip removed, and
        the resolved ``*.SEN3`` directory returned (matching the offline client's
        contract of returning a local SAFE folder).
        """
        product = self._datastore.get_product(
            collection_id=ref.collection_id, product_id=ref.product_id
        )
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Extract into a SHORT per-product subdir (hashed) — the product id already
        # ends in ".SEN3" and the zip contains a "<id>.SEN3/" folder, so extracting
        # under the id would double-nest and blow past the Windows MAX_PATH (260).
        extract_root = dest_dir / hashlib.sha1(ref.product_id.encode("utf-8")).hexdigest()[:10]
        if extract_root.exists():
            shutil.rmtree(extract_root)
        extract_root.mkdir(parents=True)

        fd, tmp_zip_name = tempfile.mkstemp(suffix=".zip", dir=dest_dir)
        tmp_zip = Path(tmp_zip_name)
        try:
            with os.fdopen(fd, "wb") as out, product.open() as src:
                shutil.copyfileobj(src, out)
            with zipfile.ZipFile(tmp_zip) as zf:
                zf.extractall(extract_root)
        finally:
            tmp_zip.unlink(missing_ok=True)

        return _find_safe_dir(extract_root)


def _default_fixtures_dir() -> Path:
    """Return the committed ``payload/fixtures`` directory."""
    # datastore.py -> ingestion -> pdgs -> src -> payload
    return Path(__file__).resolve().parents[3] / "fixtures"


def _read_fixture_metadata(safe_dir: Path) -> tuple[datetime, datetime, BBox | None]:
    """Read sensing window + bbox from a fixture's geodetic/geolocation netCDF.

    Kept dependency-light: imports xarray lazily and falls back to a fixed
    deterministic window if attributes are absent (they are present in our
    generated fixtures).
    """
    from pdgs.ingestion.metadata import fixture_metadata

    return fixture_metadata(safe_dir)
