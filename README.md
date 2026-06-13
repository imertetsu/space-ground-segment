# SpaceGroundSegment — Mini Space Ground Segment

A portfolio project demonstrating both halves of a satellite ground segment, the
kind EUMETSAT / ESA operate — engineered to read as **operationally credible**,
with every scientific/operational simplification explicitly documented.

- **PDGS (payload)** — ingest real Earth-Observation data (Sentinel-3 SLSTR) and
  run a chained processor **L1 → L2** (cloud screening → simplified split-window
  SST), then validate the output against the **official L2 SST** product.
- **FOS (control)** — ingest a simulated, CCSDS/PUS-compliant telemetry stream
  into **Yamcs**, decommutate against a mission database, limit-check spacecraft
  health, and command the spacecraft.
- **Shared layers** — common time service, catalogue/archive, anomaly model.
- **3D flow view** — satellite in orbit → downlink → ground segment → products
  and spacecraft state.

> **Data honesty:** payload data is **real** (EUMETSAT Data Store). Spacecraft
> telemetry is **simulated** but CCSDS/PUS-compliant, and labelled as simulated
> everywhere it appears. The 3D view labels whether it shows canned animation or
> live data.

## Status

**Epic 1 (payload), Phase 0 — skeleton + CI.** No processing logic yet; the
quality gates run green on the skeleton. Ingestion (Phase 1) is blocked until
EUMETSAT Data Store credentials are provided (see `docs/HANDOFF.md`).

## How we work

SSS (Spec → Sketch → Ship) methodology — full contract in [`CLAUDE.md`](CLAUDE.md);
current state in [`docs/HANDOFF.md`](docs/HANDOFF.md); ECSS-flavoured docs in
[`docs/`](docs/) (SRD, ICD, SVP/SVR, architecture, operations).

## Repository layout

```
payload/   Epic 1 — PDGS payload chain (Python)            ◄── built first
control/   Epic 2 — FOS control (Java + Yamcs, simulator)  (placeholder)
shared/    Epic 3 — time service · catalogue · anomaly     (placeholder)
viz/       Epic 4 — 3D flow web app (CesiumJS)             (placeholder)
docs/      SRD · ICD · SVP/SVR · architecture · ops · specs
ops/       docker, scripts, observability                  (as needed)
```

## Quickstart — Epic 1 (payload)

```bash
cd payload
python -m venv .venv && source .venv/Scripts/activate   # Windows; bin/ on POSIX
pip install -e ".[dev]"
pytest                 # run the test suite
pdgs status            # operator status CLI

# or via Docker, from the repo root:
docker compose build payload && docker compose run --rm payload status
```
