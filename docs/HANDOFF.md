# HANDOFF — SpaceGroundSegment

> Single source of project state. Living snapshot — rewritten/pruned at the end of
> every epic, never endlessly appended. Cap ~150 lines. Read this first when
> re-entering after a gap. Full methodology + conventions: `CLAUDE.md`.

_Last updated: 2026-06-14 — Epics 1, 2 & 3 CLOSED on `main`. Next: Epic 4 (3D viz)._

## Stack snapshot

- **Project:** "Mini Space Ground Segment" — portfolio ground segment: PDGS
  (payload) + FOS (control) + shared layers + 3D view. Built epic-by-epic.
- **Done:** Epic 1 `payload/` (Python) · Epic 2 `control/` (Python sim + Yamcs) ·
  Epic 3 `shared/` (unification — catalogue, anomaly, time, `sgs-ops` surface).
  **Pending:** Epic 4 3D viz (`viz/`).
- **Stack:** Python 3.11 (payload + simulator) · Java 17 + Yamcs (control) ·
  PostgreSQL (Epic 3) · CesiumJS (Epic 4) · Docker · CI: GitLab + GitHub Actions.
- **Gates — payload** (`payload/`): ruff · `mypy --strict` 0 · pytest (141) ·
  lint-imports · `docker compose build payload`. **simulator** (`control/simulator/`):
  ruff · `mypy --strict` 0 · pytest (~83). **yamcs** (`control/yamcs/`): `./mvnw
  package` (XTCE validated by Yamcs at startup). **shared** (`shared/`): ruff ·
  `mypy --strict` 0 · pytest (79, postgres-marked need `PDGS_PG_DSN`) · lint-imports.

## Active feature flags

- None. (The Epic-3 `SGS_SHARED` dark flag was **flipped on** at Epic-3 close — the
  `sgs-ops` operator surface is live by default.)

## In-flight work

- None. Epic 3 is CLOSED (merged to `main`); Epic 4 (3D viz) not yet started.

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

## Epic 3 (shared / unification) — outcome

- `shared/` (`sgs_shared`, own gates; `lint-imports` forbids `pdgs`/`sgs_sim`)
  unifies both halves behind one **PostgreSQL catalogue**, one **anomaly model**,
  one **UTC time base**, surfaced by the **`sgs-ops`** operator CLI. Control stays
  SIMULATED & labelled; payload stays REAL. Frozen contracts: ICD §3.1 (catalogue
  schema), §3.2 (Yamcs-REST bridge), §3.3 (anomaly model), §3.4 (time service).
- **Read-only consumers (no cross-segment code import):** the Yamcs bridge reads
  the Yamcs REST API; the payload bridge reads the PDGS SQLite catalogue file
  read-only (`sgs-ops sync-payload`). Data dependencies, not imports.
- **Verified live:** `sgs-ops overview` renders one cross-segment surface (state +
  anomalies + last results) — REAL payload products + control references + a control
  OOL anomaly, control labelled `control-simulated`, all on the shared catalogue/UTC
  base. The Yamcs bridge was verified against a running Yamcs (15 refs from real
  REST). 79 shared tests pass. ESCALATED business decisions: adopted the recommended
  defaults (CLI MVP surface; Postgres for new writes + SQLite stays offline;
  read-only Yamcs-REST bridge).

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
  request-id-correlated (custom verifier = future).
- (shared) OBT↔UTC correlation is a documented **seed** (no live PUS-9 report; ICD
  §3.4). `overview` live control state needs Yamcs running (degrades gracefully).

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
- Code → `payload/`, `control/simulator/` (`sgs_sim`), `control/yamcs/`,
  `shared/` (`sgs_shared` — catalogue/anomaly/time_service/bridges/`sgs-ops`) (+ READMEs)

## Next step

- **Epic 4 — 3D viz (`viz/`, CesiumJS):** read-only consumer rendering the flow view
  over the shared catalogue + Yamcs REST (orbit track via satellite.js/SGP4; scene
  footprints; data-driven overlays from REAL payload products). Write the ephemeral
  spec first; phase-by-phase with a real browser check; control/illustrative content
  labelled per SRD §5. Start: a planning agent writes `docs/specs/<epic4>.md`.
- **Follow-up (non-blocking, payload):** wire the live `pdgs` CLI to optionally write
  directly into the shared Postgres catalogue (today products reach the shared
  catalogue via the read-only `sgs-ops sync-payload` SQLite bridge; default stays
  SQLite for offline dev — the mapper + capability exist and are tested).
