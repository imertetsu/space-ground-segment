# Operations Guide — Epic 1 (PDGS / Payload)

How to run the payload chain. All commands run from the `payload/` directory using
its virtualenv. Authoritative gate commands/baselines live in `CLAUDE.md §0`.

> **Data mode:** the chain currently runs **offline** against tiny **synthetic,
> labelled** SLSTR fixtures (no EUMETSAT credentials yet). Use `config/fixture.toml`
> (synthetic coefficients) for the offline demo; `config/default.toml` ships the
> cited MCSST coefficients for real data. Real-data runs are activated by providing
> EUMETSAT Data Store credentials (see "Real data" below).

## Setup

```bash
cd payload
python -m venv .venv && source .venv/Scripts/activate    # Windows; bin/ on POSIX
pip install -e ".[dev]"
```

> Behind Avast / a TLS-intercepting AV, point pip at the Windows CA bundle
> (`PIP_CERT`/`SSL_CERT_FILE`) or disable HTTPS scanning — see `docs/HANDOFF.md`.

## One-command end-to-end (offline demo)

```bash
python -m pdgs.cli.main run --config config/fixture.toml
```
Runs ingest → process → validate on the synthetic fixtures and writes a validation
report under `data/reports/<derived_id>/` (`validation.md`, `validation.json`,
`difference.png`). Exits non-zero if validation fails the thresholds.

## Per-stage commands

| Stage | Command | What it does |
|---|---|---|
| Ingest | `pdgs ingest` | Discover/download/verify/register the L1 + official L2 fixtures (REQ-ING). |
| Process | `pdgs process --config config/fixture.toml` | Cloud-screen + split-window SST → derived `SST_L2_DERIVED` product with provenance (REQ-PRO). |
| Validate | `pdgs validate --config config/fixture.toml` | Co-locate vs official L2, compute stats, gate on thresholds, write report (REQ-VAL). |
| Status | `pdgs status [--status STATUS] [--type TYPE]` | List catalogue products with status, level, and provenance `config_version` (REQ-OPS-03). |
| Reprocess | `pdgs reprocess <product_id> [--validate]` | On-demand re-run for a product (resolves the source L1; refreshes in place) (REQ-OPS-02). |
| Dead-letter | `pdgs dead-letter` | List products in the `FAILED` dead-letter state (REQ-OPS-01). |

(`pdgs` is the installed console script; `python -m pdgs.cli.main` is equivalent.)

## Interpreting results

- **Validation report** (`validation.md`): stats table (match count, bias, RMSE,
  std, % within tolerance), per-threshold PASS/FAIL, overall verdict, and the run
  metadata (processor/config versions, thresholds, timestamp). `difference.png`
  shows the derived−official difference map + histogram.
- **Thresholds** live in the `[validation]` section of the config (spec defaults:
  ±2 K tolerance, |bias| ≤ 1.0 K, RMSE ≤ 1.5 K, ≥ 90 % within tolerance, ≥ 100
  matchups, reference `quality_level` ≥ 3).
- **Anomalies / dead-letter:** a product that fails ingestion or processing is
  routed to `FAILED`; inspect with `pdgs dead-letter` and re-attempt with
  `pdgs reprocess <id>`.
- **Reproducibility:** every derived product records its processor + config
  versions (provenance); re-running with the same versions yields an equivalent
  product (REQ-CFG-03).

## Real data (when EUMETSAT credentials are available)

1. Create a free EUMETSAT Data Store account; copy the Consumer Key/Secret into a
   local `.env` (see `.env.example`) — never commit it.
2. Run with the real config: `pdgs run --config config/default.toml` (the client
   factory auto-selects the real `eumdac` path when credentials are present).
3. Known real-path TODOs are tracked in `docs/HANDOFF.md` (zip-SAFE extraction,
   Data Store checksum as the expected digest, confirm the WST internal filename).

## 3D view

The 3D flow view is **Epic 4** — not part of the payload epic.
