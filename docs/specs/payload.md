# Epic 1 — PDGS / Payload Chain — Spec (EPHEMERAL)

> **EPHEMERAL.** This spec lives only while Epic 1 is in flight. Per the SSS
> methodology (`CLAUDE.md §1`), it is **DELETED in Epic 1's last commit**. Code,
> commits, and tests are the institutional memory — not this file.

_Status: draft — Phase 0 in progress (skeleton + CI, owned by the main session)._

---

## 1. Goal

Build the `payload/` bounded context (PDGS — Payload Data Ground Segment): a
Python pipeline that discovers and downloads **real** Sentinel-3 SLSTR Level-1
data, derives a simplified Level-2 Sea Surface Temperature (SST) product, and
validates it against the **official** EUMETSAT Level-2 SST product. All
processing is **Non-Time-Critical (NTC)**.

## 2. Verified facts (do not change — confirmed against EUMETSAT / data.europa.eu / NASA CMR)

- **Mission / instrument:** Sentinel-3 SLSTR. **Timeliness: NTC.**
- **L1 input collection:** `EO:EUM:DAT:0411` — "SLSTR Level 1B Radiances and
  Brightness Temperatures" — product type `SL_1_RBT`
  (`EO:EUM:DAT:SENTINEL-3:SL_1_RBT___NTC`). SAFE format = a folder of netCDF
  files. Bands **S1–S6** = TOA radiances (VIS/NIR/SWIR); **S7–S9** = TOA
  brightness temperature (TIR); **F1–F2** = fire channels (BT). Nadir + oblique
  views.
- **L2 reference (official) collection:** `EO:EUM:DAT:0412` — "SLSTR Level 2 Sea
  Surface Temperature (SST)" — product type `SL_2_WST`
  (`EO:EUM:DAT:SENTINEL-3:SL_2_WST___NTC`). GHRSST L2P; main field
  `sea_surface_temperature` (Kelvin) + `quality_level`. IPF v07.00.
- **Co-location simplification:** the derived L2 SST (from L1 nadir TIR split-
  window, S8 ≈ 10.8 µm and S9 ≈ 12 µm) and the official WST live on **different
  grids** → matchup needs gridding (nearest-neighbour). Documented as a
  simplification, never presented as operational.

## 3. Architecture constraints (from CLAUDE.md / project brief)

- Modular monorepo, two bounded contexts: `payload/` (PDGS, Python) and
  `control/` (FOS, Java/Yamcs), plus a cross-cutting `shared/` layer
  (time-service, catalogue, anomaly). `viz/` (3D) is a **read-only** consumer.
- **Dependency rule:** segments depend only on `shared/` contracts, never on each
  other; `viz/` consumes read-only APIs or canned data.
- Within `payload/` (Python), layered: `cli → (ingestion | processing |
  validation) → catalogue → config`.

## 4. Phased plan

Each phase lists deliverables, the **cross-phase CONTRACT it freezes** (so later
phases can parallelize against it — see §3 decision tree in `CLAUDE.md`),
acceptance criteria, and parallel-vs-serial guidance.

### Phase 0 — Skeleton + CI (owned by main session; this spec does NOT touch it)

- **Deliverables:** `payload/` Python package skeleton, layered module stubs,
  quality gates (lint/format/type-check/tests/arch-check), CI
  (`.gitlab-ci.yml` canonical + GitHub Actions mirror), Dockerfile.
- **Contract frozen:** the layering contract (`cli → ingestion|processing|
  validation → catalogue → config`) and the package import boundaries enforced by
  arch-check.
- **Acceptance:** all gates green on an empty-but-wired skeleton; CI passes on
  both runners.
- **Parallelism:** N/A — foundational, serial, prerequisite to everything.

### Phase 1 — Ingestion + Catalogue

- **Deliverables:** `eumdac`-based discovery + download for both L1 (`SL_1_RBT`)
  and official L2 (`SL_2_WST`); integrity check on downloaded products;
  registration into the catalogue.
- **Contract frozen (CRITICAL — unblocks Phase 2 parallelism):**
  - **Catalogue schema** — per-product record: product id, collection id,
    product type, timeliness (`NTC`), sensing start/stop, footprint/bbox,
    local path, checksum, ingest timestamp, status enum.
  - **L1-reader contract** — the in-memory representation the processing layer
    consumes (band arrays S1–S9 / F1–F2, view = nadir|oblique, geolocation,
    units per the ICD band table). Freezing this is what lets cloud-screening and
    SST retrieval be built in parallel in Phase 2.
- **Acceptance:** given valid credentials, a discover→download→register round
  trip persists a catalogue record whose checksum verifies; offline mode works
  against committed tiny fixtures.
- **Parallelism:** discovery/download and catalogue-registration touch different
  modules but share the catalogue schema → **DEFINE the schema first (1 unit),
  then PARALLEL**. **Note: live download is BLOCKED on credentials (see §6).**

### Phase 2 — Processing chain (cloud screening + SST)

- **Deliverables:**
  - Cloud-screening processor (threshold-based mask).
  - SST-retrieval processor (simplified split-window from nadir S8/S9).
  - Provenance stamping on every output product.
  - Each processor independently runnable.
  - Out-of-range value flagging.
- **Contract frozen:**
  - **Product/provenance model** — output product structure + provenance block
    (input product ids, processor name + version, config version, run timestamp,
    quality flags). Consumed by Phase 3 validation and `viz/`.
  - **Config schema** — versioned processor configuration (thresholds,
    coefficient set id, view selection).
- **Acceptance:** each processor runs standalone on a fixture and emits a product
  carrying a complete provenance block; out-of-range pixels are flagged, not
  silently clamped.
- **Parallelism:** once the **L1-reader contract** (Phase 1) is frozen,
  cloud-screening and SST-retrieval share **no files** and neither's output is
  the other's input → **PARALLEL** (per §3 decision tree). Provenance stamping is
  a shared concern → define the provenance model first, then both processors
  conform to it.

### Phase 3 — IV&V + validation vs official L2

- **Deliverables:** co-located comparison of derived SST vs official `SL_2_WST`
  (nearest-neighbour gridding); persisted comparison statistics; pipeline **fails
  CI when results fall outside thresholds**; human-readable validation report.
- **Contract frozen:**
  - **Validation-report schema** — match count, bias, RMSE, std, % agreement,
    threshold pass/fail, per-run metadata. Consumed by OPS status CLI and the
    report renderer.
- **Acceptance:** a validation run on fixtures produces a report conforming to the
  schema; a deliberately-degraded run trips the threshold gate.
- **Parallelism:** the IV&V harness (REQ coverage assertions) and the statistical
  validation comparison are independent once the product/provenance model and
  validation-report schema are frozen → **PARALLEL**.

### Phase 4 — Operations + docs

- **Deliverables:** failed-product → dead-letter state handling; on-demand
  reprocessing; operator status CLI; operations-guide sections filled in;
  finalize ECSS-flavoured docs.
- **Contract frozen:** the **operator CLI surface** (status, reprocess,
  dead-letter inspect) and the dead-letter state model.
- **Acceptance:** an operator can list status, reprocess a product on demand, and
  inspect dead-lettered items via the CLI; docs reflect the shipped behaviour.
- **Parallelism:** OPS features (dead-letter / reprocess / status) are largely
  independent of one another once the catalogue status enum is frozen →
  **PARALLEL**; doc finalization is serial-last (and this spec is deleted in the
  Epic's last commit).

## 5. Cross-phase contract summary (freeze points)

| Contract | Frozen at | Consumed by |
|---|---|---|
| Layering / import boundaries | Phase 0 | all |
| Catalogue schema | Phase 1 | Phase 2, 3, 4 (OPS) |
| L1-reader contract | Phase 1 | Phase 2 (enables parallel processors) |
| Product / provenance model | Phase 2 | Phase 3, `viz/` |
| Config schema (versioned) | Phase 2 | Phase 3, 4 |
| Validation-report schema | Phase 3 | Phase 4 (status CLI), report renderer |
| Operator CLI surface + dead-letter model | Phase 4 | operations |

## 6. ESCALATED — business decisions

1. **EUMETSAT Data Store credentials — RESOLVED.** Decision: **proceed without
   them for now.** Consequence: **Phase 1 live ingestion/download of real data is
   BLOCKED** until credentials arrive. The skeleton, offline code, and
   fixture-based tests proceed unblocked. The blocked unit is isolated so the rest
   of the epic is not gated.
2. **Remaining open business decisions (flag for the user):**
   - **Validation acceptance thresholds** — final pass/fail bounds for derived SST
     vs official L2 (see §7). Proposed by the agent; need owner sign-off before
     the Phase 3 gate is treated as authoritative.
   - **AOI / scene selection** for the demo matchup (which SLSTR scenes / region)
     — affects how representative the validation is. _TBD with the user._
   - **MVP scope of views** — nadir-only for MVP is proposed (oblique deferred).
     Confirm this is acceptable for the portfolio narrative.

## 7. Proposed validation acceptance thresholds (PROPOSED BY AGENT — tunable)

> These are **technical proposals** to make the Phase 3 gate concrete, not
> operational requirements. They are deliberately lenient because the derived SST
> uses a simplified split-window and nearest-neighbour co-location. **Subject to
> owner sign-off; tune against the first real matchup.**

| Metric | Proposed bound | Notes |
|---|---|---|
| Matchup count | ≥ 100 co-located pairs | per validation run; below this → inconclusive, not pass |
| `|bias|` (derived − official) | ≤ 1.0 K | proposed-by-agent |
| RMSE | ≤ 1.5 K | proposed-by-agent |
| Agreement within ±2 K | ≥ 90 % of matched pairs | proposed-by-agent |
| Quality filter | compare only where official `quality_level` ≥ 3 | exclude low-quality reference pixels |

If a run falls outside these bounds, Phase 3 fails CI (per REQ-VAL-03).

## 8. Out of scope (Epic 1)

- The `control/` (FOS / Yamcs / Java) segment — Epic 2.
- The 3D `viz/` consumer — Epic 4.
- Oblique-view processing (MVP is nadir-only — see §6.2).
- Operational-grade cloud screening / radiative-transfer SST (we ship documented
  simplifications, never presented as operational).
