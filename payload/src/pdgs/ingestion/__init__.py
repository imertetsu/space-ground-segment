"""Ingestion: discover, download and integrity-check SLSTR L1 + official L2, then
register products in the catalogue (REQ-ING).

Phase 1 is OFFLINE-first: :class:`~pdgs.ingestion.datastore.OfflineDataStoreClient`
serves committed synthetic SAFE fixtures and is the default;
:class:`~pdgs.ingestion.datastore.EumdacClient` wraps the real EUMETSAT Data Store
and activates only when credentials are present (see
:func:`~pdgs.ingestion.datastore.make_client`). The FROZEN L1-reader contract
(:class:`~pdgs.ingestion.readers.L1Scene`) and :class:`L2Reference` live here for
Phase 2/3 to consume.
"""

from __future__ import annotations

from pdgs.ingestion.datastore import (
    CONSUMER_KEY_ENV,
    CONSUMER_SECRET_ENV,
    DataStoreClient,
    EumdacClient,
    IngestionError,
    MissingCredentialsError,
    OfflineDataStoreClient,
    ProductRef,
    has_credentials,
    make_client,
)
from pdgs.ingestion.ingest import IngestResult, ingest
from pdgs.ingestion.integrity import (
    compute_sha256,
    product_size_bytes,
    verify_integrity,
)
from pdgs.ingestion.readers import (
    Band,
    L1Scene,
    L2Reference,
    ViewName,
    read_l1_rbt,
    read_l2_wst,
)

__all__ = [
    "CONSUMER_KEY_ENV",
    "CONSUMER_SECRET_ENV",
    "Band",
    "DataStoreClient",
    "EumdacClient",
    "IngestResult",
    "IngestionError",
    "L1Scene",
    "L2Reference",
    "MissingCredentialsError",
    "OfflineDataStoreClient",
    "ProductRef",
    "ViewName",
    "compute_sha256",
    "has_credentials",
    "ingest",
    "make_client",
    "product_size_bytes",
    "read_l1_rbt",
    "read_l2_wst",
    "verify_integrity",
]
