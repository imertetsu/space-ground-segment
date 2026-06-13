"""Catalogue domain types — FROZEN contract (Phase 1).

These types are the cross-phase catalogue schema frozen in Phase 1 and consumed by
Phase 2 (processing), Phase 3 (validation) and Phase 4 (operations). Changing the
field set or semantics here is a breaking change for downstream phases.

All datetimes are timezone-aware UTC. Persistence (sqlite/PostgreSQL) lives in
``pdgs.catalogue.repository``; this module is storage-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

# Product abstraction level. ``L2_DERIVED`` is the SST product this pipeline
# computes from L1; ``L2`` is the official EUMETSAT reference (SL_2_WST).
ProductLevel = Literal["L1", "L2", "L2_DERIVED"]

# Bounding box as (west, south, east, north) in degrees.
BBox = tuple[float, float, float, float]


class ProductStatus(Enum):
    """Lifecycle state of a catalogued product.

    The status advances monotonically through the happy path
    (DISCOVERED -> DOWNLOADED -> VERIFIED -> REGISTERED -> PROCESSED ->
    VALIDATED). ``FAILED`` is the dead-letter state (Phase 4): any product whose
    ingestion or processing fails is routed here for later inspection/reprocessing.
    """

    DISCOVERED = "DISCOVERED"
    DOWNLOADED = "DOWNLOADED"
    VERIFIED = "VERIFIED"
    REGISTERED = "REGISTERED"
    PROCESSED = "PROCESSED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Provenance:
    """Provenance stamped onto a product so reruns are auditable (REQ-PRO-03).

    Frozen because provenance describes a completed run and must not mutate after
    the fact. ``input_product_ids`` is a tuple (hashable, immutable) of the source
    product ids that fed the run.
    """

    processor_version: str
    config_version: str
    input_product_ids: tuple[str, ...]
    run_timestamp: datetime


@dataclass
class Product:
    """A catalogued EO product (L1 input, L2 reference, or derived L2 SST).

    This is the FROZEN per-product catalogue record. ``bbox`` is optional because
    a footprint may be unknown at discovery time. ``provenance`` is ``None`` for
    ingested source products and populated for derived products (Phase 2).
    All datetimes are timezone-aware UTC.
    """

    product_id: str
    collection_id: str
    product_type: str
    level: ProductLevel
    timeliness: str
    sensing_start: datetime
    sensing_end: datetime
    bbox: BBox | None
    local_path: str
    checksum: str
    size_bytes: int
    status: ProductStatus
    provenance: Provenance | None
    created_at: datetime
    updated_at: datetime
