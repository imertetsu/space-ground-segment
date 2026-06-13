"""`pdgs` operator CLI entrypoint (REQ-OPS-03).

Phase 0: prints operator status only. Subcommands (ingest, process, validate,
reprocess, status) are added in later phases.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from pdgs import __version__
from pdgs.config.version import current_stamp


def build_parser() -> argparse.ArgumentParser:
    """Build the operator-CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pdgs",
        description="Payload Data Ground Segment (PDGS) operator CLI.",
    )
    parser.add_argument("--version", action="version", version=f"pdgs {__version__}")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["status"],
        help="Operator command (Phase 0: only 'status').",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the operator CLI. Returns a process exit code."""
    build_parser().parse_args(argv)
    stamp = current_stamp()
    print("PDGS — Payload Data Ground Segment (Epic 1)")
    print("Status: Phase 0 skeleton — no products processed yet.")
    print(f"Processor version: {stamp.processor_version}")
    print(f"Config version:    {stamp.config_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
