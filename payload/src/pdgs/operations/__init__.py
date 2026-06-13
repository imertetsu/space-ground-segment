"""Operations layer — operator-facing pipeline actions (REQ-OPS-01/02).

This package holds the orchestration logic behind the operator CLI (dead-letter
inspection, on-demand reprocessing) so it is unit-testable independently of the
argparse plumbing in :mod:`pdgs.cli`.

Layering: ``operations`` sits between ``cli`` and ``validation`` in the layered
architecture (``cli > operations > validation > processing > ingestion >
catalogue > config``). It composes the ``processing`` and ``validation`` layers
(both lower) and never imports ``cli`` (the only higher layer), keeping the
``import-linter`` layers contract satisfied.
"""

from __future__ import annotations

from pdgs.operations.reprocess import (
    ReprocessError,
    ReprocessOutcome,
    list_dead_letter,
    reprocess_product,
    resolve_source_l1_dir,
)

__all__ = [
    "ReprocessError",
    "ReprocessOutcome",
    "list_dead_letter",
    "reprocess_product",
    "resolve_source_l1_dir",
]
