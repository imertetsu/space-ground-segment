# HANDOFF — SpaceGroundSegment

> Single source of project state. Living snapshot — rewritten/pruned at the end of
> every epic, never endlessly appended. Cap ~150 lines. Read this first when
> re-entering after a gap. Full methodology + conventions: `CLAUDE.md`.

_Last updated: 2026-06-13 — Epics 1 & 2 CLOSED on `main`; Epic 3 (shared) Phases 0–1 done on `epic/shared` (catalogue schema FROZEN)._

## Stack snapshot

- **Project:** "Mini Space Ground Segment" — portfolio ground segment: PDGS
  (payload) + FOS (control) + shared layers + 3D view. Built epic-by-epic.
- **Done:** Epic 1 `payload/` (Python) · Epic 2 `control/` (Python sim + Yamcs).
  **Pending:** Epic 3 shared layers (`shared/`), Epic 4 3D viz (`viz/`).
- **Stack:** Python 3.11 (payload + simulator) · Java 17 + Yamcs (control) ·
  PostgreSQL (Epic 3) · CesiumJS (Epic 4) · Docker · CI: GitLab + GitHub Actions.
- **Gates — payload** (`payload/`): ruff · `mypy --strict` 0 · pytest (141) ·
  lint-imports · `docker compose build payload`. **simulator** (`control/simulator/`):
  ruff · `mypy --strict` 0 · pytest (~83). **yamcs** (`control/yamcs/`): `./mvnw
  package` (XTCE validated by Yamcs at startup). **shared** (`shared/`): ruff ·
  `mypy --strict` 0 · pytest (33, postgres-marked need `PDGS_PG_DSN`) · lint-imports.

## Active feature flags

- None.

## In-flight work

- **Epic 3 (shared layers) on branch `epic/shared`. Phases 0–1 DONE.** `shared/`
  package (`sgs_shared`, own gates; import-linter forbids importing `pdgs`/`sgs_sim`)
  + a shared **PostgreSQL** catalogue + the `sgs-ops` operator CLI (dark flag
  `SGS_SHARED`).
  - **Phase 1 (REQ-INT-02) — catalogue schema FROZEN** (the load-bearing freeze):
    full `PostgresCatalogue` (`register`/`get`/`list`/`update_status`/`set_provenance`),
    unified `CatalogueEntry` + `Provenance` envelope (origin+simulated+provenance on
    every row), single cross-segment query surface, primitive-field `mappers.py`
    (so segments map in without `shared/` importing them), and a **read-only
    Yamcs-REST control bridge** (`control_bridge.YamcsControlBridge`) recording
    telemetry/alarm **references** (never value copies). Frozen schema in **ICD §3.1**;
    bridge in **ICD §3.2**. **Verified live against real Yamcs:** `sgs-ops bridge`
    recorded 15 control refs (14 TM-archive + 1 OOL alarm) from Yamcs REST, then
    `sgs-ops status` listed them with a payload product (1 payload + 16 control),
    each labelled, no value stored. 33 shared tests pass. 3 ESCALATED defaults
    adopted (CLI MVP; Postgres for new writes + keep SQLite offline; read-only bridge).
- **Next: Phase 2 (shared anomaly model, REQ-INT-03)** — one anomaly record +
  state machine covering payload `FAILED`/dead-letter and Yamcs OOL alarms, shared
  operator actions (acknowledge both; reprocess payload-only); link via the frozen
  catalogue `reference`. Then Phase 3 (time service), Phase 4 (operator surface +
  flag flip + close → merge to `main`). Postgres: `docker compose --profile epic3 up
  -d postgres`; `PDGS_PG_DSN=postgresql://sgs:change-me@localhost:5432/sgs_catalogue`.

## Epic 1 (payload) — outcome

- PDGS chain: eumdac ingest → catalogue (sqlite) → cloud screen + simplified N2
  split-window SST (cited MCSST coeffs) → validate vs official L2 WST → report;
  operator CLI. **Validated on REAL EUMETSAT data:** 330,274 matchups, bias
  −0.85 K, RMSE 1.22 K, 91.6 % within ±2 K (honest for a documented simplified
  algorithm; NOT operational). Offline demo on labelled-synthetic fixtures.

## Epic 2 (control) — outcome

- FOS: **SIMULATED** Python simulator (`control/simulator/`, `sgs_sim`) emits
  CCSDS + PUS-C telemetry over UDP → **Yamcs** (`control/yamcs/`, from the
  quickstart) decommutates via an **XTCE** MDB (SpaceSystem `SGS`).
- **Verified live:** HK decommutates to engineering units (calibrated), OOL alarms
  fire on injected anomalies, and `SET_MODE(SAFE)` telecommand → simulator executes
  (mode changes in HK) + returns PUS-1 verification ACKs; invalid TC rejected at
  validation. Contracts frozen in ICD §2.5 (packets), §2.6 (MDB), §2.7 (TC).
- Telemetry is simulated & labelled everywhere. docker-compose FOS stack provided
  (CI-clean; local image build needs the Avast CA).

## Recent decisions worth remembering

- Language = English; CI = GitLab + GitHub mirror; remote = **GitHub** `origin`
  (https://github.com/imertetsu/space-ground-segment) — `main` pushed.
- Commits carry **no** Claude co-author trailer (`includeCoAuthoredBy=false`).
- Verified SLSTR collection IDs: L1 `EO:EUM:DAT:0411`, L2 `EO:EUM:DAT:0412`.
- Control APIDs: HK 100, EVENT 101, ACK 102, TC 200; private PUS service 132 for
  commands; PUS-1 for verification.

## Follow-ups (non-blocking)

- (payload) Data Store checksum as integrity digest; decode real
  `cloud_in`/`l2p_flags` bits; a `pdgs fetch` command.
- (control) anomalies clamp at the hard band → OOL lands at WARNING boundary; let
  them overshoot for a clean CRITICAL. Command verifiers are container-match, not
  request-id-correlated (custom verifier = future). PUS-9 time correlation is a
  seed (full unification = Epic 3).

## Known gotchas

- **EUMETSAT creds** in `.env` (gitignored), work. **Avast TLS interception**
  breaks SSL for pip/git/curl/Maven/Java (host + Docker): pip →
  `PIP_CERT`/`SSL_CERT_FILE`=Windows CA bundle; git → `http.sslBackend=schannel`;
  curl → `ssl-no-revoke` (`CURL_HOME/.curlrc`); Maven/Java (`mvnw`) →
  `JDK_JAVA_OPTIONS=-Djavax.net.ssl.trustStoreType=Windows-ROOT`. CI unaffected.
- Network commands need `dangerouslyDisableSandbox`. Real EO data + Yamcs scratch
  live under `data/` + `D:/sgs` (gitignored/scratch — deletable).
- gitignored: `.venv/`, `data/`, `*.nc` (except fixtures), `*.ccsds`, `*.pem`.

## Where to find things

- Methodology, conventions, gates → `CLAUDE.md`
- Agent roster → `.claude/agents/` (payload-developer, control-developer; viz later)
- Requirements / interfaces / verification → `docs/srd`, `docs/icd`, `docs/svp-svr`
- Operations → `docs/operations/operations-guide.md`
- Code → `payload/`, `control/simulator/` (`sgs_sim`), `control/yamcs/` (+ READMEs)

## Next step

- **Epic 3 — Phase 2 (shared anomaly model, REQ-INT-03):** one anomaly record +
  state machine for payload `FAILED`/dead-letter **and** Yamcs OOL alarms; shared
  operator actions (acknowledge both halves; reprocess payload-only); link via the
  frozen catalogue `reference`. Then Phase 3 (time service, REQ-INT-01), Phase 4
  (single operator surface + flag flip + close → merge `epic/shared` to `main`).
- **Follow-up (non-blocking):** wire the live `pdgs` CLI to optionally write into
  the shared Postgres catalogue (the mapper + capability exist and are tested;
  default stays SQLite for offline dev).
