"""Product and provenance catalogue access (REQ-ING-04).

FROZEN Phase 1 contract. The domain types
(:class:`~pdgs.catalogue.models.Product`, :class:`~pdgs.catalogue.models.ProductStatus`,
:class:`~pdgs.catalogue.models.Provenance`) and the
:class:`~pdgs.catalogue.repository.Catalogue` repository interface are consumed by
Phases 2/3/4. The default implementation is stdlib-sqlite3
(:class:`~pdgs.catalogue.repository.SqliteCatalogue`); the shared PostgreSQL
catalogue arrives in Epic 3 behind the same :class:`Catalogue` interface.
"""

from __future__ import annotations

from pdgs.catalogue.models import (
    BBox,
    Product,
    ProductLevel,
    ProductStatus,
    Provenance,
)
from pdgs.catalogue.repository import (
    Catalogue,
    CatalogueError,
    SqliteCatalogue,
)

__all__ = [
    "BBox",
    "Catalogue",
    "CatalogueError",
    "Product",
    "ProductLevel",
    "ProductStatus",
    "Provenance",
    "SqliteCatalogue",
]
