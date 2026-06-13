"""``sgs-ops`` — the cross-segment operator CLI (Phase 0).

Subcommands:

- ``status``  : list the shared catalogue across both origins (payload + control),
  each row labelled by origin, control rows tagged SIMULATED, sorted by ingest time.
  Behind the ``SGS_SHARED`` **dark flag** — if unset/empty, prints a one-line
  "dark" notice and exits 0 (Epic 3 ships dark; the flag flips at the epic's close).
- ``bridge``  : poll a running Yamcs server (read-only REST) and record control
  telemetry/alarm references into the shared catalogue. Also dark-flag-gated.
- ``seed-demo`` (hidden): register one payload + one control demo row (Phase-0 demo).

The DSN comes from ``--db`` (override) or the ``PDGS_PG_DSN`` env var. The CLI is a
read-only consumer of the shared catalogue and imports NO segment code.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING

from sgs_shared.catalogue.repository import CatalogueError, PostgresCatalogue
from sgs_shared.catalogue.seed import seed_demo
from sgs_shared.control_bridge.yamcs import (
    BridgeError,
    YamcsControlBridge,
    record_references,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sgs_shared.catalogue.models import CatalogueEntry

# Dark flag (CLAUDE.md §8): the shared operator surface stays dark until Epic 3 close.
DARK_FLAG_ENV = "SGS_SHARED"

DARK_MESSAGE = "shared operator surface is dark (set SGS_SHARED=1)"


def _flag_is_on() -> bool:
    """True iff the ``SGS_SHARED`` dark flag is set and non-empty."""
    return bool(os.environ.get(DARK_FLAG_ENV))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sgs-ops",
        description="Cross-segment operator surface for the Mini Space Ground Segment.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser(
        "status",
        help="List the shared catalogue across both segments (dark flag: SGS_SHARED).",
    )
    status.add_argument(
        "--db",
        dest="dsn",
        default=None,
        help="PostgreSQL DSN override (default: $PDGS_PG_DSN).",
    )

    bridge = sub.add_parser(
        "bridge",
        help="Record control references from Yamcs into the catalogue (dark flag: SGS_SHARED).",
    )
    bridge.add_argument(
        "--db",
        dest="dsn",
        default=None,
        help="PostgreSQL DSN override (default: $PDGS_PG_DSN).",
    )
    bridge.add_argument(
        "--yamcs-url",
        dest="yamcs_url",
        default="http://localhost:8090",
        help="Yamcs HTTP base URL (default: http://localhost:8090).",
    )
    bridge.add_argument(
        "--instance",
        dest="instance",
        default="myproject",
        help="Yamcs instance name (default: myproject).",
    )
    bridge.add_argument(
        "--processor",
        dest="processor",
        default="realtime",
        help="Yamcs processor name (default: realtime).",
    )

    # Hidden Phase-0 demo seeder: no help= => argparse omits it from the listing,
    # keeping it off the public operator surface while still invokable.
    seed = sub.add_parser("seed-demo")
    seed.add_argument(
        "--db",
        dest="dsn",
        default=None,
        help="PostgreSQL DSN override (default: $PDGS_PG_DSN).",
    )

    return parser


def _format_row(entry: CatalogueEntry) -> str:
    """Render one catalogue row for the operator listing."""
    sensing = entry.sensing_time.isoformat() if entry.sensing_time is not None else "-"
    source_version = entry.provenance.source_version or "-"
    return (
        f"{entry.ingest_time.isoformat()}  "
        f"[{entry.origin_label()}]  "
        f"{entry.entry_id}  "
        f"{entry.product_type}  "
        f"status={entry.status}  "
        f"sensing={sensing}  "
        f"src={source_version}  "
        f"ref={entry.reference}"
    )


def _cmd_status(dsn: str | None) -> int:
    if not _flag_is_on():
        print(DARK_MESSAGE)
        return 0
    try:
        catalogue = PostgresCatalogue(dsn=dsn)
        entries = catalogue.list()  # both origins, sorted by ingest_time
    except CatalogueError as exc:
        print(f"sgs-ops: {exc}", file=sys.stderr)
        return 1

    if not entries:
        print("(catalogue empty - run 'sgs-ops seed-demo' for the Phase-0 demo rows)")
        return 0

    payload_n = sum(1 for e in entries if e.origin == "payload")
    control_n = sum(1 for e in entries if e.origin == "control")
    print(f"shared catalogue: {len(entries)} entries ({payload_n} payload, {control_n} control):")
    for entry in entries:
        print(_format_row(entry))
    return 0


def _cmd_bridge(dsn: str | None, yamcs_url: str, instance: str, processor: str) -> int:
    if not _flag_is_on():
        print(DARK_MESSAGE)
        return 0
    try:
        catalogue = PostgresCatalogue(dsn=dsn)
        bridge = YamcsControlBridge(
            base_url=yamcs_url,
            instance=instance,
            processor=processor,
        )
        count = record_references(catalogue, bridge)
    except (CatalogueError, BridgeError) as exc:
        print(f"sgs-ops: {exc}", file=sys.stderr)
        return 1
    print(f"recorded {count} control reference(s) from Yamcs into the shared catalogue")
    return 0


def _cmd_seed_demo(dsn: str | None) -> int:
    if not _flag_is_on():
        print(DARK_MESSAGE)
        return 0
    try:
        catalogue = PostgresCatalogue(dsn=dsn)
        payload_entry, control_entry = seed_demo(catalogue)
    except CatalogueError as exc:
        print(f"sgs-ops: {exc}", file=sys.stderr)
        return 1
    print(f"seeded payload entry: {payload_entry.entry_id} [{payload_entry.origin_label()}]")
    print(f"seeded control entry: {control_entry.entry_id} [{control_entry.origin_label()}]")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "status":
        return _cmd_status(args.dsn)
    if args.command == "bridge":
        return _cmd_bridge(args.dsn, args.yamcs_url, args.instance, args.processor)
    if args.command == "seed-demo":
        return _cmd_seed_demo(args.dsn)
    parser.error(f"unknown command: {args.command!r}")  # pragma: no cover - argparse guards


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
