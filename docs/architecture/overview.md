# Architecture Overview

> System-level architecture for the Mini Space Ground Segment. Persistent
> document. Epic 1 implements only the `payload/` context; the rest is mapped
> here for orientation.

---

## 1. Bounded contexts & shared layer

Modular monorepo with two bounded contexts and a cross-cutting shared layer. The
3D view is a read-only consumer.

```
                         ┌───────────────────────────────────────────┐
                         │              shared/ (contracts)            │
                         │   time-service  ·  catalogue  ·  anomaly    │
                         └───────────────────────────────────────────┘
                              ▲                              ▲
              depends on      │                              │   depends on
            (contracts only)  │                              │ (contracts only)
                              │                              │
        ┌─────────────────────┴───────┐      ┌──────────────┴──────────────────┐
        │      payload/  (PDGS)        │      │       control/  (FOS)           │
        │      Python                  │      │       Java / Yamcs              │
        │                              │      │                                 │
        │  cli                         │      │  (Epic 2 — WIP):                │
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
- Enforced by the project's arch-check gate (wired in Phase 0).

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

## 4. 3D view design (Epic 4 — placeholder)

> Brief placeholder; full design lands with Epic 4.

- **Stack:** **CesiumJS** for the globe/scene; **satellite.js** for orbit
  propagation (TLE/SGP4) of the Sentinel-3 platform.
- **Read-only:** consumes read-only APIs or canned data; never writes to or
  depends on the segments.
- **Tiers — illustrative vs data-driven (must be labelled):**
  - *Illustrative* — orbit track, ground-track geometry, scene footprints drawn
    for context. Labelled **illustrative**.
  - *Data-driven* — overlays derived from **real** payload products (e.g. SST
    fields / matchup locations). Labelled as derived from real data.
- Per SRD §5, simulated (control) and illustrative (viz) content is always
  labelled as such; a simplification is never presented as operational.
