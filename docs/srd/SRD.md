# Software Requirements Document (SRD) — Epic 1 (PDGS / Payload)

> ECSS-flavoured SRD for the `payload/` bounded context. Persistent document.
> Requirement identifiers are stable; the ephemeral Epic 1 spec
> (`docs/specs/payload.md`) holds the in-flight plan and is deleted on epic close.

_Scope: Epic 1 only (PDGS payload chain). Control (FOS) requirements are Epic 2._

---

## 1. Requirements

Each requirement is a single testable statement. Traceability to tests lives in
`docs/svp-svr/SVP.md`.

### Ingestion — REQ-ING

| ID | Requirement |
|---|---|
| REQ-ING-01 | The system shall discover and download Sentinel-3 SLSTR L1 products (`SL_1_RBT`, collection `EO:EUM:DAT:0411`, NTC) via `eumdac`. |
| REQ-ING-02 | The system shall discover and download the official L2 SST reference products (`SL_2_WST`, collection `EO:EUM:DAT:0412`, NTC) via `eumdac`. |
| REQ-ING-03 | The system shall verify the integrity of each downloaded product (checksum / completeness) before registration. |
| REQ-ING-04 | The system shall register every successfully ingested product in the catalogue with its metadata. |

### Processing — REQ-PRO

| ID | Requirement |
|---|---|
| REQ-PRO-01 | The system shall produce a cloud mask for an L1 scene using a documented threshold-based screening. |
| REQ-PRO-02 | The system shall derive an L2 SST product from L1 nadir TIR bands (S8 ≈ 10.8 µm, S9 ≈ 12 µm) using a simplified split-window retrieval. |
| REQ-PRO-03 | The system shall stamp provenance (input product ids, processor name + version, config version, run timestamp) on every output product. |
| REQ-PRO-04 | Each processor (cloud mask, SST retrieval) shall be independently runnable. |
| REQ-PRO-05 | The system shall flag out-of-range output values rather than silently clamping or discarding them. |

### Validation — REQ-VAL

| ID | Requirement |
|---|---|
| REQ-VAL-01 | The system shall produce a co-located comparison of the derived SST against the official `SL_2_WST` product (nearest-neighbour gridding). |
| REQ-VAL-02 | The system shall persist the comparison statistics (match count, bias, RMSE, std, % agreement). |
| REQ-VAL-03 | The pipeline shall fail (gate CI) when validation results fall outside the configured acceptance thresholds. |
| REQ-VAL-04 | The system shall render a human-readable validation report from the persisted statistics. |

### Configuration — REQ-CFG

| ID | Requirement |
|---|---|
| REQ-CFG-01 | All processor configuration shall be versioned. |
| REQ-CFG-02 | Every output product shall record the processor version and the config version used to produce it. |
| REQ-CFG-03 | The system shall support reproducible reruns (same inputs + same processor/config versions → equivalent output). |

### Operations — REQ-OPS

| ID | Requirement |
|---|---|
| REQ-OPS-01 | A product whose processing fails shall transition to a dead-letter state. |
| REQ-OPS-02 | The system shall support on-demand reprocessing of a selected product. |
| REQ-OPS-03 | An operator shall be able to query product/pipeline status via a CLI. |

## 2. Rationale

- **Real data, real provenance.** The portfolio value is a credible, reproducible
  ground-segment chain on **real** SLSTR data, validated against the **official**
  EUMETSAT product. Provenance and versioned config (REQ-PRO-03, REQ-CFG-*) make
  every product auditable and reruns deterministic.
- **Independent processors** (REQ-PRO-04) enable parallel development (per the
  §3 decision tree once the L1-reader contract is frozen) and isolated testing.
- **Threshold-gated validation** (REQ-VAL-03) turns "looks plausible" into an
  objective CI gate, the ECSS-flavoured verification stance of this project.
- **Operational hooks** (REQ-OPS-*) demonstrate ground-segment operability
  (dead-letter, reprocessing, status) without claiming operational maturity.

## 3. Assumptions

- `eumdac` and an EUMETSAT Data Store account are the access path for L1 and L2.
  **Credentials are not yet available** → live ingestion is blocked; offline /
  fixture-based development proceeds (see `docs/specs/payload.md §6`).
- The official `SL_2_WST` product (IPF v07.00, GHRSST L2P) is the authoritative
  reference for validation.
- Tiny representative fixtures are committed for offline unit/integration tests;
  full scenes are downloaded, never committed.
- NTC timeliness is sufficient for all Epic 1 use cases (no near-real-time path).

## 4. Simplifications (explicit — none of these is operational)

> Listed so they are never mistaken for operational capability. The pipeline and
> reports must label these as simplifications.

- **Cloud screening is threshold-based**, not a trained/operational cloud mask.
- **SST is a simplified split-window** from nadir S8/S9 — the **N2 nadir-only
  dual-channel (11/12 µm)** SST type of the SLSTR SST ATBD (EUMETSAT), in the
  constant-coefficient **MCSST** form `SST_°C = a0 + a1·T11 + a2·(T11−T12)`
  (output → K via +273.15). Coefficients = published **NOAA-19 day-split MCSST**
  set (MCSST family: McClain/Pichel/Walton 1985; values via ENVI "Compute AVHRR
  Sea Surface Temperature"). **Cross-sensor simplification:** AVHRR coefficients
  applied to SLSTR S8/S9 — NOT the operational SLSTR SST (which uses
  water-vapour-binned LUT coefficients per the ATBD). The MCSST `sec(θ)−1`
  view-angle term is dropped for nadir. Coefficients live in versioned config
  (`payload/config/default.toml`); the offline demo uses synthetic fixture
  coefficients (`config/fixture.toml`, labelled).
- **Co-location is nearest-neighbour gridding** between the derived grid and the
  official L2P grid — no rigorous resampling / footprint matching.
- **Nadir view only** for the MVP; oblique view deferred.
- **NTC only** — no near-real-time handling.
- Quality handling consumes the official `quality_level` for reference filtering
  but does not replicate the official quality scheme on the derived product.

## 5. Real vs Simulated Data Statement (MANDATORY)

- **Payload data is REAL.** All SLSTR L1 and official L2 products are real
  EUMETSAT data retrieved via `eumdac`. Derived products are computed from this
  real data using the documented simplifications in §4.
- **Spacecraft telemetry (Epic 2 — control / FOS) is SIMULATED.** It is
  **CCSDS / PUS-compliant** in structure but synthetically generated, and is
  **labelled "simulated" everywhere** it appears (data, UIs, logs, reports).
- **The 3D view (Epic 4) labels illustrative-vs-live** content: orbit
  propagation and any illustrative geometry are marked illustrative; data-driven
  overlays are marked as derived from real payload data.
- **A simplification is never presented as operational.** Reports, CLI output,
  and the viz must surface the simplification and simulated/illustrative labels.
