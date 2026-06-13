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

> Status legend: **Planned** (test designed, not yet implemented) · *Implemented*
> · *Passing*. All entries are **Planned** until Phase work lands.

| REQ-ID | Planned test | Status |
|---|---|---|
| REQ-ING-01 | `test_discover_download_l1_rbt` (integration, fixture/offline) | Planned |
| REQ-ING-02 | `test_discover_download_l2_wst` (integration, fixture/offline) | Planned |
| REQ-ING-03 | `test_integrity_check_rejects_corrupt` (unit) | Planned |
| REQ-ING-04 | `test_catalogue_registration_record` (integration) | Planned |
| REQ-PRO-01 | `test_cloud_mask_thresholds` (unit) | Planned |
| REQ-PRO-02 | `test_split_window_sst_retrieval` (unit) | Planned |
| REQ-PRO-03 | `test_provenance_stamped_on_output` (integration) | Planned |
| REQ-PRO-04 | `test_processors_run_independently` (integration) | Planned |
| REQ-PRO-05 | `test_out_of_range_values_flagged` (unit) | Planned |
| REQ-VAL-01 | `test_colocated_comparison_nn` (integration) | Planned |
| REQ-VAL-02 | `test_statistics_persisted` (integration) | Planned |
| REQ-VAL-03 | `test_pipeline_fails_outside_thresholds` (integration) | Planned |
| REQ-VAL-04 | `test_report_human_readable` (integration) | Planned |
| REQ-CFG-01 | `test_config_is_versioned` (unit) | Planned |
| REQ-CFG-02 | `test_product_records_processor_and_config_versions` (integration) | Planned |
| REQ-CFG-03 | `test_rerun_is_reproducible` (integration) | Planned |
| REQ-OPS-01 | `test_failed_product_goes_dead_letter` (integration) | Planned |
| REQ-OPS-02 | `test_on_demand_reprocessing` (integration) | Planned |
| REQ-OPS-03 | `test_operator_status_cli` (integration) | Planned |

> The IV&V suite asserts this matrix is complete: every REQ-\* row must map to at
> least one test that runs in CI, or the build fails.

---

## 4. SVR — Software Verification Results (placeholder)

**No runs yet.** Verification results will be recorded here as phases land
(per-level pass/fail counts, validation statistics for the latest run, and any
deviations). The traceability statuses in §3 will move from **Planned** →
*Implemented* → *Passing* as tests are written and executed.
