"""Regenerate ``viz/public/data/snapshot.json`` from the LIVE shared catalogue.

READ-ONLY exporter. It lists the Epic 3 shared catalogue and anomaly store and
serialises them to the canned snapshot schema the static viz app reads. It performs
**no writes** to any segment — only ``.list()`` calls — and the viz runtime never
imports a segment: it reads only the produced JSON. This tool exists to prove the
snapshot is honestly data-driven and to refresh it on demand.

Run it from the shared virtualenv (which already has ``sgs_shared`` + ``psycopg``),
with the catalogue DSN in the environment::

    # from the repo root, on Windows PowerShell
    $env:PDGS_PG_DSN = "postgresql://sgs:change-me@localhost:5432/sgs_catalogue"
    shared\\.venv\\Scripts\\python.exe viz\\tools\\export_snapshot.py

Options:
    --out  PATH   output file (default: viz/public/data/snapshot.json)
    --dsn  DSN    PostgreSQL DSN (default: $PDGS_PG_DSN)

The ``platform`` block is filled from the committed TLE file (the satellite name is
read from its first line; NORAD id 41335; ``tle_file`` points at the runtime path).
All datetimes are emitted as ISO-8601 with a trailing ``Z`` (UTC); the ``simulated``
flag is preserved on every row so the data-honesty labels never get lost.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sgs_shared.anomaly.repository import PostgresAnomalyStore
from sgs_shared.catalogue.repository import PostgresCatalogue

# Repo-relative paths. This file is viz/tools/export_snapshot.py, so:
#   parents[0] = viz/tools, parents[1] = viz, parents[2] = repo root.
_VIZ_DIR = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _VIZ_DIR / "public" / "data" / "snapshot.json"
_TLE_FILE = _VIZ_DIR / "public" / "data" / "sentinel3a.tle"
_NORAD_ID = 41335
_TLE_RUNTIME_PATH = "data/sentinel3a.tle"


def _iso_z(value: datetime | None) -> str | None:
    """Serialise a datetime as ISO-8601 UTC with a trailing ``Z`` (or ``None``)."""
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _platform_block() -> dict[str, Any]:
    """Build the platform block, reading the satellite name from the TLE file."""
    name = "SENTINEL-3A"
    try:
        first_line = _TLE_FILE.read_text(encoding="utf-8").splitlines()[0].strip()
        if first_line and not first_line.startswith("1 "):
            name = first_line
    except (OSError, IndexError):
        # Fall back to the default name if the TLE file is missing/odd; the static
        # app still loads the real TLE at runtime regardless of this label.
        pass
    return {"name": name, "norad_id": _NORAD_ID, "tle_file": _TLE_RUNTIME_PATH}


def export(dsn: str) -> dict[str, Any]:
    """List the live catalogue + anomalies (read-only) and build the snapshot dict."""
    catalogue = PostgresCatalogue(dsn=dsn)
    anomalies = PostgresAnomalyStore(dsn=dsn)

    cat_rows: list[dict[str, Any]] = []
    for entry in catalogue.list():
        prov = entry.provenance
        cat_rows.append(
            {
                "entry_id": entry.entry_id,
                "origin": entry.origin,
                "simulated": entry.simulated,
                "product_type": entry.product_type,
                "status": entry.status,
                "sensing_time": _iso_z(entry.sensing_time),
                "ingest_time": _iso_z(entry.ingest_time),
                "reference": entry.reference,
                "source_version": prov.source_version,
                "source_refs": list(prov.source_refs),
                "detail": entry.detail,
            }
        )

    anom_rows: list[dict[str, Any]] = []
    for anom in anomalies.list():
        anom_rows.append(
            {
                "anomaly_id": anom.anomaly_id,
                "origin": anom.origin,
                "simulated": anom.simulated,
                "kind": anom.kind,
                "severity": anom.severity,
                "state": anom.state.value,
                "source_ref": anom.source_ref,
                "opened_at": _iso_z(anom.opened_at),
                "updated_at": _iso_z(anom.updated_at),
                "detail": anom.detail,
            }
        )

    return {
        "generated_at": _iso_z(datetime.now(tz=UTC)),
        "note": (
            "Exported from the live shared catalogue by viz/tools/export_snapshot.py "
            "(read-only). Payload rows are REAL EUMETSAT products; control rows are "
            "SIMULATED Yamcs telemetry references; orbit comes from the REAL TLE."
        ),
        "platform": _platform_block(),
        "catalogue": cat_rows,
        "anomalies": anom_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_OUT,
        help="output snapshot path (default: viz/public/data/snapshot.json)",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("PDGS_PG_DSN"),
        help="PostgreSQL DSN (default: $PDGS_PG_DSN)",
    )
    args = parser.parse_args(argv)

    if not args.dsn:
        parser.error("no DSN: pass --dsn or set PDGS_PG_DSN")

    snapshot = export(args.dsn)

    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    cat_n = len(snapshot["catalogue"])
    anom_n = len(snapshot["anomalies"])
    print(f"Wrote {out_path} — {cat_n} catalogue rows, {anom_n} anomalies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
