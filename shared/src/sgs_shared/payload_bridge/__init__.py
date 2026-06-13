"""Read-only payload (PDGS) SQLite catalogue bridge for the shared catalogue.

This package reads the payload segment's SQLite catalogue **file** read-only and
mirrors each product into the unified shared catalogue as a payload
:class:`~sgs_shared.catalogue.models.CatalogueEntry` (REAL data). It NEVER imports
``pdgs`` code — it reads the data file via the standard-library ``sqlite3`` driver,
so the cross-segment isolation rule (``lint-imports``) is upheld.
"""

from __future__ import annotations

from sgs_shared.payload_bridge.sqlite import (
    PayloadBridgeError,
    PayloadSqliteBridge,
    record_products,
)

__all__ = ["PayloadBridgeError", "PayloadSqliteBridge", "record_products"]
