# Architecture Overview

> System-level architecture for the Mini Space Ground Segment. Persistent
> document. **Epics 1–3 are implemented** — `payload/` (PDGS), `control/` (FOS),
> and the cross-cutting `shared/` layer with the `sgs-ops` operator surface.
> `viz/` (Epic 4) is mapped here for orientation.

---

## 1. Bounded contexts & shared layer

Modular monorepo with two bounded contexts and a cross-cutting shared layer. The
3D view is a read-only consumer.

```
                         ┌───────────────────────────────────────────┐
                         │       shared/ (contracts) — Epic 3 ✓        │
                         │   time-service · catalogue · anomaly        │
                         │   + sgs-ops operator surface (live)         │
                         └───────────────────────────────────────────┘
                              ▲                              ▲
              depends on      │                              │   depends on
            (contracts only)  │                              │ (contracts only)
                              │                              │
        ┌─────────────────────┴───────┐      ┌──────────────┴──────────────────┐
        │      payload/  (PDGS)        │      │       control/  (FOS)           │
        │      Python                  │      │       Java / Yamcs              │
        │                              │      │                                 │
        │  cli                         │      │  (Epic 2 ✓):                    │
        │   └─ ingestion │ processing  │      │   TM/TC, CCSDS, PUS, XTCE MIB   │
        │      │ validation            │      │                                 │
        │      └─ catalogue            │      │                                 │
        │         └─ config            │      │                                 │
        └──────────────┬───────────────┘      └──────────────┬──────────────────┘
                       │   read-only (APIs or canned data)    │
                       └──────────────┬───────────────────────┘
                                      ▼
                         ┌───────────────────────────────┐
                         │     viz/  (3D, read-only)      │
                         │     CesiumJS + satellite.js    │
                         │     (Epic 4)                   │
                         └───────────────────────────────┘
```

## 2. Dependency-direction rule

- `payload/` and `control/` depend **only on `shared/` contracts** — **never on
  each other**.
- `viz/` is a **read-only consumer**: it reads from read-only APIs or canned data;
  nothing depends on `viz/`.
- Within `payload/` (Python), strict layering: `cli → (ingestion | processing |
  validation) → catalogue → config`. Lower layers never import upper layers.
- `shared/` depends on **neither** segment (its `lint-imports` contract forbids
  importing `pdgs`/`sgs_sim`). The `sgs-ops` operator surface and the bridges are
  **read-only consumers**: the Yamcs bridge reads the Yamcs REST API and the payload
  bridge reads the PDGS SQLite catalogue file read-only — **data** dependencies, not
  code imports, so the cross-segment isolation holds.
- Enforced by the project's arch-check gate (`import-linter`, wired in Phase 0;
  extended to `shared/` in Epic 3).

## 3. Conceptual calibration symmetry (payload ↔ control)

The two segments are deliberately structured as analogues, which is the
pedagogical spine of the portfolio:

| Concept | Payload side (PDGS) | Control side (FOS) |
|---|---|---|
| **Raw → engineering units** | raw radiances → calibrated L1 (radiometric calibration) | raw telemetry counts → engineering units via the **MIB** (calibration curves) |
| **Limit / range checking** | out-of-range flagging on derived products (REQ-PRO-05) | telemetry limit-checking / alarms against MIB-defined ranges |
| **Provenance / traceability** | processor + config versions stamped on every product | command verification + parameter source traceability |

> In short: *control-side raw-counts→engineering-units via the MIB is the analogue
> of payload-side raw-radiances→calibrated-L1, and telemetry limit-checking is the
> analogue of product out-of-range flagging.* The shared `anomaly` contract is
> where both sides' "something is out of range" signals converge conceptually.

## 4. 3D flow view (Epic 4 — implemented)

`viz/` is a static **CesiumJS** read-only flow view (no build step, no backend; CDN
libs). It ties the segments together on one screen — the Sentinel-3A platform, its
payload products, and the control state — fed by a canned JSON snapshot of the
shared catalogue (`viz/tools/export_snapshot.py` regenerates it read-only).

- **Stack:** **CesiumJS** (globe/scene, offline Natural Earth II imagery — no ion
  token) + **satellite.js** (SGP4) propagating the **real** Sentinel-3A TLE
  (Celestrak, NORAD 41335).
- **Read-only consumer:** fetches `data/*.tle` + `data/snapshot.json` only; imports
  no segment code (the exporter reads the shared catalogue/anomaly store read-only).
  Nothing depends on `viz/`.
- **Real / simulated / illustrative, always labelled (SRD §5):**
  - *REAL* — payload products (EUMETSAT SLSTR L1/L2) + the orbit (real TLE + SGP4).
  - *SIMULATED* — control telemetry references + OOL anomalies (Yamcs, Epic 2),
    shown as `control-simulated`.
  - *ILLUSTRATIVE* — scene footprint geometry (ellipses; the products are real, the
    footprint shapes are not reprojected scene polygons).
- A legend on screen states the three labels; a simplification is never presented as
  operational. Run: `cd viz/public && python -m http.server 8095`.
