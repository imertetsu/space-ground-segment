# Operations Guide

Covers **PDGS / payload** (Epic 1) and **FOS / control** (Epic 2). Payload first;
the FOS / control section is near the end.

## PDGS / Payload (Epic 1)

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

## FOS / Control (Epic 2) — SIMULATED

The FOS = our **SIMULATED** Python spacecraft simulator (CCSDS/PUS) → **Yamcs**
(XTCE MDB). All telemetry/commands are simulated and labelled.

### Run natively (verified path)

```bash
cd control/yamcs && ./mvnw yamcs:run          # Yamcs web UI: http://localhost:8090
# in another shell — the simulator (HK stream + TC receiver):
cd control/simulator && python -m sgs_sim.cli.main   # TM → UDP :10015, TC ← :10025
```
Behind Avast, export `JDK_JAVA_OPTIONS=-Djavax.net.ssl.trustStoreType=Windows-ROOT`
and `CURL_HOME` (a `.curlrc` of `ssl-no-revoke`) for `mvnw` — see `control/README.md`.

### Run via docker-compose (CI-clean; local image build needs the Avast CA)

```bash
docker compose up yamcs simulator   # from the repo root
```

### Operate (Yamcs web UI :8090, or the REST API)

- **Telemetry:** Telemetry → Parameters → SpaceSystem `SGS` — decommutated HK in
  engineering units (battery_voltage V, obc_temp °C, reaction_wheel_speed RPM,
  spacecraft_mode enum, …). REST: `GET /api/processors/myproject/realtime/parameters/SGS/<param>`.
- **Alarms:** out-of-limit parameters raise OOL alarms (Alarms view). Trigger one
  by enabling an anomaly in `control/simulator/config/*.toml` (e.g. `obc_overtemp`,
  `battery_undervoltage`, `rw_overspeed`).
- **Telecommand:** Commanding → send `SGS/SET_MODE` (mode SAFE/NOMINAL/PAYLOAD) or
  `PING`; the simulator returns PUS-1 verification ACKs and the new mode appears in
  HK. Out-of-range args are rejected at validation. REST:
  `POST /api/processors/myproject/realtime/commands/SGS/SET_MODE` body `{"args":{"mode":"SAFE"}}`.

### MIB summary

The mission database (parameters, calibration, limits, commands, ACK containers)
is `control/yamcs/src/main/yamcs/mdb/xtce.xml`; its summary is recorded in the ICD:
§2.5 (HK packet field-map), §2.6 (TM params / calibration / limits), §2.7
(commands + verification). Packet byte-level spec: `control/simulator/PACKET_FORMAT.md`.

### Time correlation (PUS-9) — seed for Epic 3

OBT↔UTC correlation is **seeded**, not yet unified: the simulator omits a PUS time
field (documented simplification) and Yamcs stamps packet time from its own clock
(`MyPacketPreprocessor`). Epic 3's shared **time service** will add a PUS service-9
time report (CCSDS CUC) and a real OBT↔UTC correlation consumed by both segments,
so payload products and telemetry parameters share one UTC base — the control-side
analogue of payload product time-stamping.

## Unification — shared layers (Epic 3)

The `shared/` layer (`sgs_shared`) unifies both halves behind one PostgreSQL
catalogue, one anomaly model, and one UTC time base, surfaced by the **`sgs-ops`**
operator CLI. Control telemetry stays **SIMULATED** and labelled (`control-simulated`)
everywhere; payload data stays REAL. The surface is **read-only** w.r.t. the
segments (no `control/`/`pdgs` imports) — see the ICD §3 frozen contracts.

```bash
# Start the shared PostgreSQL catalogue (epic3 profile) and point sgs-ops at it:
docker compose --profile epic3 up -d postgres            # from the repo root
export PDGS_PG_DSN="postgresql://sgs:change-me@localhost:5432/sgs_catalogue"

# Mirror REAL payload products from the PDGS SQLite catalogue (read-only):
sgs-ops sync-payload --sqlite <path-to-pdgs catalogue.sqlite>
# Record control telemetry/alarm REFERENCES from a running Yamcs (read-only REST):
sgs-ops bridge                                           # needs Yamcs on :8090
# Record control OOL alarms as shared anomalies:
#   (the bridge's record_anomalies path; same read-only Yamcs REST)

# THE unified operator surface — state + anomalies + last results, both halves:
sgs-ops overview
# Other subcommands: status (catalogue listing), anomalies / ack <id> / resolve <id>.
```

- **Catalogue (REQ-INT-02):** `catalogue_entries` records payload products AND
  control references with a common origin/`simulated`/provenance envelope (ICD §3.1);
  the Yamcs bridge records `TM_ARCHIVE_REF` + `OOL_ALARM_REF` **references** only —
  never telemetry values (ICD §3.2).
- **Anomaly model (REQ-INT-03):** one record + state machine
  (`OPEN→ACKNOWLEDGED→REPROCESSING→RESOLVED`) for payload `FAILED` dead-letter AND
  control OOL alarms; `ack`/`resolve` on both, `reprocess` payload-only (ICD §3.3).
- **Time base (REQ-INT-01):** one UTC base; `time_service` adds OBT↔UTC correlation
  (seeded — the PUS-9 simplification, ICD §3.4).
- **Live control state** in `overview` requires Yamcs running; otherwise it degrades
  gracefully to a labelled "unavailable" note (the catalogue/anomaly view still works).

## 3D view

The 3D flow view is **Epic 4** — not yet built.
