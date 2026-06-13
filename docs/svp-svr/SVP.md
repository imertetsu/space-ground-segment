# Software Verification Plan (SVP) — Epic 1 (PDGS / Payload)

> ECSS-flavoured SVP. Defines the verification levels and the requirement→test
> traceability for Epic 1. A short **SVR** (results) placeholder is at the bottom.

---

## 1. Verification levels

| Level | What it covers | How it runs |
|---|---|---|
| **Unit** | Individual algorithms (cloud-screening thresholds, split-window SST, out-of-range flagging) and — for Epic 2 — telemetry decommutation & calibration. | Pure functions over small in-memory inputs; fast, no I/O. |
| **Integration** | End-to-end flow across layers (read fixture → process → produce product with provenance → validate) on **tiny committed fixtures**. | Runs in CI on committed SAFE/netCDF fixtures (no live download). |
| **IV&V suite** | Independent verification asserting **every REQ-\* is exercised** by at least one test; **gates CI**. | Dedicated suite mapping each requirement to its test; fails the build if a requirement has no passing test. |
| **Validation** | Statistical comparison of derived SST vs the official `SL_2_WST` reference; pass/fail against acceptance thresholds. | Validation run producing the persisted statistics + report; trips the threshold gate (REQ-VAL-03). |

## 2. Verification methods (per requirement class)

- **REQ-ING-\*** — integration tests against fixtures (offline); live-download
  paths verified once credentials arrive (currently **blocked**).
- **REQ-PRO-\*** — unit tests for each algorithm + integration test for
  provenance stamping and out-of-range flagging.
- **REQ-VAL-\*** — validation run on fixtures; a deliberately-degraded run to
  prove the threshold gate trips.
- **REQ-CFG-\*** — unit/integration tests asserting versions are recorded and
  reruns are reproducible.
- **REQ-OPS-\*** — integration tests for dead-letter transition, on-demand
  reprocessing, and the status CLI.

## 3. Traceability matrix

> Status legend: **Planned** · **Passing** (mapped test implemented and green).
> The **authoritative, machine-checked** REQ→test map lives in
> `payload/tests/ivv/test_ivv_coverage.py`: the IV&V suite runs `pytest
> --collect-only` and fails CI if any requirement lacks a collectable test, so
> this table cannot silently drift. All Epic-1 tests pass against the synthetic
> fixtures (offline); real-data validation is pending EUMETSAT credentials.

| REQ-ID | Mapped test | Status |
|---|---|---|
| REQ-ING-01 | `test_ingest_roundtrip.py::test_ingest_l1_roundtrip_registers_and_verifies` | Passing |
| REQ-ING-02 | `test_ingest_roundtrip.py::test_ingest_l2_roundtrip_registers` | Passing |
| REQ-ING-03 | `test_integrity.py::test_verify_rejects_corrupted_file` | Passing |
| REQ-ING-04 | `test_ingest_roundtrip.py::test_ingest_both_collections_persist` | Passing |
| REQ-PRO-01 | `test_cloud_screening.py::test_screen_flags_known_cloudy_pixels_via_l1_flag` | Passing |
| REQ-PRO-02 | `test_sst_retrieval.py::test_retrieve_recovers_synthetic_field_clear_sky` | Passing |
| REQ-PRO-03 | `test_process_scene.py::test_process_scene_writes_product_and_registers` | Passing |
| REQ-PRO-04 | `test_cloud_screening.py` + `test_sst_retrieval.py` (each processor standalone) | Passing |
| REQ-PRO-05 | `test_sst_retrieval.py::test_retrieve_flags_out_of_range_without_clamping` | Passing |
| REQ-VAL-01 | `test_colocation.py::test_same_grid_returns_aligned_pairs` | Passing |
| REQ-VAL-02 | `test_stats.py::test_known_bias_and_rmse` + `test_result.py::test_write_result_json_roundtrips` | Passing |
| REQ-VAL-03 | `test_validate_product.py::test_degraded_derived_trips_the_gate` | Passing |
| REQ-VAL-04 | `test_report.py::test_markdown_report_written_and_labels_synthetic` | Passing |
| REQ-CFG-01 | `test_config_processing.py::test_load_default_toml_exposes_config_version` | Passing |
| REQ-CFG-02 | `test_process_scene.py::test_process_scene_writes_product_and_registers` | Passing |
| REQ-CFG-03 | `test_reproducibility.py::test_rerun_is_reproducible` | Passing |
| REQ-OPS-01 | `test_ingest_roundtrip.py::test_ingest_corrupt_download_routes_to_failed` | Passing (capability; operator dead-letter CLI = Phase 4) |
| REQ-OPS-02 | `test_reproducibility.py::test_on_demand_reprocessing_refreshes_in_place` | Passing (capability; `reprocess` CLI = Phase 4) |
| REQ-OPS-03 | `test_cli.py::test_status_command_returns_zero` | Passing |

---

## 4. SVR — Software Verification Results

**Verification status (2026-06-13, Epic 1 Phases 0–3, offline/synthetic).**

- **Quality gates:** ruff (lint+format), `mypy --strict` = 0 errors, `import-linter`
  1 contract kept, **107 tests passing** (unit + integration + IV&V). IV&V coverage
  suite green → all 19 REQ-* have a collectable, passing test.
- **Validation run (first), synthetic fixtures, `config/fixture.toml`:**
  matchups = 1186 (`quality_level ≥ 3`); **bias = −0.0497 K** (≤ 1.0); **RMSE =
  0.0508 K** (≤ 1.5); **100.0 % within ±2 K** (≥ 90); verdict **PASS**. Report:
  `validation.md` + `difference.png` + `validation.json`.
  (These synthetic numbers exercise the pipeline **mechanics** on self-consistent
  inputs — they are not a scientific validation.)

**Real-data validation run (2026-06-13) — REAL Sentinel-3 SLSTR, `config/default.toml`.**

- **Inputs (real, via `eumdac`, NTC):** L1 `S3A_SL_1_RBT____20260515T230350…` (one
  nadir granule, 1200×1500) vs official L2 `S3A_SL_2_WST____20260515T223233…`
  (GHRSST L2P). Coefficients = cited MCSST NOAA-19 day-split (cross-sensor
  simplification); cloud screening = S8 BT threshold only (real `cloud_in` bit
  semantics TBD).
- **Result:** matchups = **330,274** (`quality_level ≥ 3`); **bias = −0.854 K**
  (≤ 1.0); **RMSE = 1.217 K** (≤ 1.5); **std = 0.867 K**; **91.6 % within ±2 K**
  (≥ 90); verdict **PASS**.
- **Interpretation:** a sub-1 K bias / ~1.2 K RMSE against the operational product
  is a credible, honest outcome for a deliberately simplified cross-sensor
  split-window — and it clears the (lenient) acceptance thresholds. It is **not**
  operational-grade SST; the simplifications (SRD §4) stand. Report artifacts
  (`validation.md`, `difference.png`, `validation.json`) are generated under
  `data/reports/<id>/` (gitignored, regenerate with `pdgs validate`).
