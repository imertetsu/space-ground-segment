"""`pdgs` operator CLI entrypoint (REQ-OPS-03).

Phase 1 subcommands:

* ``ingest`` — OFFLINE by default: discovers, downloads, verifies and registers
  the synthetic L1 (``SL_1_RBT``) and L2 (``SL_2_WST``) fixtures into the catalogue.
* ``status`` — prints the processor/config stamp and lists catalogue contents.

Later phases add ``process``, ``validate``, ``reprocess``.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime

from pdgs import __version__
from pdgs.catalogue.repository import Catalogue, SqliteCatalogue
from pdgs.config.version import current_stamp
from pdgs.ingestion.datastore import make_client
from pdgs.ingestion.ingest import ingest

# Collections ingested by the offline `ingest` command (L1 input + L2 reference).
_INGEST_COLLECTIONS = ("EO:EUM:DAT:0411", "EO:EUM:DAT:0412")

# Wide discovery window so the committed fixtures are always "discovered".
_WINDOW_START = datetime(2000, 1, 1, tzinfo=UTC)
_WINDOW_END = datetime(2100, 1, 1, tzinfo=UTC)


def build_parser() -> argparse.ArgumentParser:
    """Build the operator-CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pdgs",
        description="Payload Data Ground Segment (PDGS) operator CLI.",
    )
    parser.add_argument("--version", action="version", version=f"pdgs {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    ingest_p = subparsers.add_parser(
        "ingest",
        help="Ingest the synthetic L1+L2 fixtures into the catalogue (offline by default).",
    )
    ingest_p.add_argument(
        "--db", default=None, help="Catalogue sqlite path (default: data/catalogue.sqlite)."
    )

    status_p = subparsers.add_parser(
        "status", help="Show the processor/config stamp and list catalogue contents."
    )
    status_p.add_argument(
        "--db", default=None, help="Catalogue sqlite path (default: data/catalogue.sqlite)."
    )

    return parser


def _cmd_ingest(catalogue: Catalogue) -> int:
    """Run the offline fixture ingestion into ``catalogue``."""
    client = make_client()
    print("PDGS ingest (OFFLINE — synthetic fixtures)")
    total_registered = 0
    total_failed = 0
    for collection_id in _INGEST_COLLECTIONS:
        result = ingest(client, collection_id, _WINDOW_START, _WINDOW_END, catalogue)
        total_registered += len(result.registered)
        total_failed += len(result.failed)
        print(
            f"  {collection_id}: {len(result.registered)} registered, {len(result.failed)} failed"
        )
    print(f"Done: {total_registered} registered, {total_failed} failed.")
    return 0 if total_failed == 0 else 1


def _cmd_status(catalogue: Catalogue) -> int:
    """Print the version stamp and list catalogue contents (REQ-OPS-03)."""
    stamp = current_stamp()
    print("PDGS — Payload Data Ground Segment (Epic 1)")
    print(f"Processor version: {stamp.processor_version}")
    print(f"Config version:    {stamp.config_version}")
    products = catalogue.list()
    if not products:
        print("Catalogue: empty (run `pdgs ingest`).")
        return 0
    print(f"Catalogue: {len(products)} product(s)")
    for product in products:
        print(
            f"  {product.product_id}  "
            f"[{product.product_type}/{product.level}]  "
            f"{product.status.value}  "
            f"{product.sensing_start.isoformat()}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the operator CLI. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    command = args.command or "status"
    db_path = getattr(args, "db", None)
    catalogue: Catalogue = SqliteCatalogue(db_path)
    if command == "ingest":
        return _cmd_ingest(catalogue)
    return _cmd_status(catalogue)


if __name__ == "__main__":
    raise SystemExit(main())
