# shared/ — cross-cutting layers (Epic 3)

Unifies the payload (PDGS) and control (FOS) segments behind three contracts:
`time_service` (OBT↔UTC), `catalogue` (shared **PostgreSQL** archive of payload
products + control telemetry references), `anomaly` (one model for payload
processing failures + control OOL alarms), plus a single **operator surface**
(`sgs-ops` CLI).

> **Dependency rule:** `shared/` depends on **neither** segment (`import-linter`
> forbids importing `pdgs`/`sgs_sim`). Segments depend on these contracts; the
> operator surface is a **read-only** consumer (shared catalogue + Yamcs REST).
> Control telemetry is **SIMULATED** and labelled everywhere.

## Setup

```bash
cd shared
python -m venv .venv && source .venv/Scripts/activate   # Windows; bin/ on POSIX
pip install -e ".[dev]"
```

## PostgreSQL (shared catalogue)

```bash
docker compose --profile epic3 up -d postgres   # from the repo root
export PDGS_PG_DSN="postgresql://sgs:change-me@localhost:5432/sgs_catalogue"
```

## Gates (from this directory)

```bash
ruff check . && ruff format --check . && mypy src && pytest && lint-imports
```

## Operator surface

```bash
SGS_SHARED=1 sgs-ops status   # cross-segment listing (payload products + control refs)
```
(dark flag `SGS_SHARED` while Epic 3 ships dark; flips on at the epic's last phase.)
