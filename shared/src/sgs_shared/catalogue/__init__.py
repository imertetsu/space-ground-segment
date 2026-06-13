"""Shared catalogue — one query surface over payload products + control references.

The catalogue defines its OWN unified record (:class:`~sgs_shared.catalogue.models.CatalogueEntry`):
it does NOT import the payload's ``Product`` (the dependency rule forbids importing
``pdgs``). Field names are aligned with the payload ``Product``/``Provenance`` shape
where sensible so the Phase 1 mapping is mechanical, but the type is independent.

Every row carries an explicit ``origin`` (``payload``/``control``) and a
``simulated`` flag so unification never erases the real-vs-simulated distinction:
payload data is REAL, control telemetry is SIMULATED.
"""

from __future__ import annotations

from sgs_shared.catalogue.models import CatalogueEntry, Origin
from sgs_shared.catalogue.repository import Catalogue, CatalogueError, PostgresCatalogue

__all__ = [
    "Catalogue",
    "CatalogueEntry",
    "CatalogueError",
    "Origin",
    "PostgresCatalogue",
]
