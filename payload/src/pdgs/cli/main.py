"""`pdgs` operator CLI entrypoint (REQ-OPS-03).

Subcommands:

* ``ingest`` — OFFLINE by default: discovers, downloads, verifies and registers
  the synthetic L1 (``SL_1_RBT``) and L2 (``SL_2_WST``) fixtures into the catalogue.
* ``process`` — runs the Phase 2 processing chain (cloud screening + simplified
  split-window SST) on an L1 scene, writing a derived ``L2_DERIVED`` netCDF and
  registering it. Offline default uses the committed fixture L1; the offline DEMO
  uses ``--config config/fixture.toml`` (the FIXTURE-ONLY synthetic coefficients).
* ``status`` — prints the processor/config stamp and lists catalogue contents.

Later phases add ``validate``, ``reprocess``.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pdgs import __version__
from pdgs.catalogue.repository import Catalogue, SqliteCatalogue
from pdgs.config.paths import default_download_dir
from pdgs.config.processing import ProcessingConfig, default_config, load_config
from pdgs.config.version import current_stamp
from pdgs.ingestion.datastore import OfflineDataStoreClient, make_client
from pdgs.ingestion.ingest import ingest
from pdgs.processing.product import process_scene

# Default offline L1 scene (the committed synthetic SL_1_RBT fixture).
_DEFAULT_L1_FIXTURE = "l1_rbt_synthetic"

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

    process_p = subparsers.add_parser(
        "process",
        help="Run cloud screening + simplified split-window SST on an L1 scene (Phase 2).",
    )
    process_p.add_argument(
        "--config",
        default="config/default.toml",
        help=(
            "Processing config TOML (default: config/default.toml, the REAL-DATA "
            "config). The offline demo uses config/fixture.toml."
        ),
    )
    process_p.add_argument(
        "--db", default=None, help="Catalogue sqlite path (default: data/catalogue.sqlite)."
    )
    process_p.add_argument(
        "--l1",
        default=None,
        help=("Source L1 SAFE folder (default: the committed offline fixture l1_rbt_synthetic)."),
    )
    process_p.add_argument(
        "--out",
        default=None,
        help="Output directory for the derived netCDF (default: data/products).",
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


def _load_processing_config(config_arg: str | None) -> ProcessingConfig:
    """Load the processing config from ``--config`` or fall back to the built-in."""
    if config_arg is None:
        return default_config()
    return load_config(config_arg)


def _resolve_l1_dir(l1_arg: str | None) -> Path:
    """Resolve the source L1 SAFE folder: ``--l1`` or the committed offline fixture."""
    if l1_arg is not None:
        return Path(l1_arg)
    return OfflineDataStoreClient().fixtures_dir / _DEFAULT_L1_FIXTURE


def _cmd_process(
    catalogue: Catalogue,
    config_arg: str | None,
    l1_arg: str | None,
    out_arg: str | None,
) -> int:
    """Run the Phase 2 processing chain on an L1 scene and register the product."""
    cfg = _load_processing_config(config_arg)
    l1_dir = _resolve_l1_dir(l1_arg)
    out_dir = Path(out_arg) if out_arg is not None else default_download_dir()

    print("PDGS process (cloud screening + simplified split-window SST)")
    print(f"  config:      {config_arg or '<built-in default>'} (v{cfg.config_version})")
    print(f"  coefficients: {cfg.sst.coefficient_set_id}")
    print(f"  source L1:   {l1_dir}")
    if not l1_dir.is_dir():
        print(f"  ERROR: L1 SAFE folder not found: {l1_dir}")
        return 1

    derived = process_scene(l1_dir, cfg, catalogue, out_dir)
    cloudy = int(derived.cloud_mask.sum())
    oor = int(derived.out_of_range.sum())
    total = int(derived.sea_surface_temperature.size)
    print(f"  derived id:  {derived.product_id}")
    print(f"  pixels:      {total} total, {cloudy} cloud-masked, {oor} out-of-range (flagged)")
    print(f"  written:     {derived.product_id}.nc -> {out_dir}")
    print("Done: 1 L2_DERIVED product PROCESSED and registered.")
    return 0


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
    if command == "process":
        return _cmd_process(
            catalogue,
            getattr(args, "config", None),
            getattr(args, "l1", None),
            getattr(args, "out", None),
        )
    return _cmd_status(catalogue)


if __name__ == "__main__":
    raise SystemExit(main())
