# HANDOFF — SpaceGroundSegment

> Single source of project state. Living snapshot — rewritten/pruned at the end of
> every epic, never endlessly appended. Cap ~150 lines. Read this first when
> re-entering the project after a gap. Full methodology + conventions: `CLAUDE.md`.

_Last updated: 2026-06-13 — Epic 1 CLOSED (on `main`); Epic 2 (control) Phase 0 done on `epic/control`._

## Stack snapshot

- **Project:** "Mini Space Ground Segment" — portfolio ground segment (PDGS payload
  + FOS control + shared layers + 3D view). Built epic-by-epic.
- **Done:** Epic 1 = `payload/` (PDGS, Python). **Pending:** Epic 2 control
  (Java/Yamcs), Epic 3 shared layers, Epic 4 3D viz — `control/`/`shared/`/`viz/`
  are placeholders.
- **Stack:** Python 3.11 · (later) Java 17 + Yamcs · PostgreSQL · CesiumJS · Docker
  · CI: GitLab (`.gitlab-ci.yml`) + GitHub Actions mirror.
- **Payload gates (from `payload/`):** `ruff check .` · `ruff format --check .` ·
  `mypy src` · `pytest` · `lint-imports` · `docker compose build payload`.
  Baseline: `mypy --strict` = **0 errors**; 141 tests pass.

## Active feature flags

- None.

## In-flight work

- **Epic 2 (control / FOS) on branch `epic/control`. Phase 0 DONE** (riskiest
  assumption proven): the Yamcs **quickstart** is scaffolded at `control/yamcs/`
  and **builds + runs on this machine behind Avast** (Maven 3.9.9 via `mvnw` +
  Java 17). The CCSDS→Yamcs→XTCE **decommutation loop is verified end-to-end**:
  `python simulator.py` → CCSDS over UDP :10015 → `UdpTmDataLink` → MDB (XTCE) →
  parameter `ACQUIRED` (raw+eng) via the REST API and web UI (:8090). Spec:
  `docs/specs/control.md`; control REQs in SRD §1A; ICD §2 filled.
- Phase 0 uses the **stock quickstart** MDB/simulator to prove the toolchain. Our
  mission HK params, **labelled** simulator, calibration, limits, commands = Phases
  1–3. Pinned: simulator=Python, Yamcs via `mvnw`, UDP transport, XTCE MDB.
- **Epic 2 / Phase 1 DONE** on `epic/control`: our SIMULATED Python simulator
  (`control/simulator/`, `sgs_sim`) emits CCSDS+PUS-C packets over UDP — periodic
  PUS-3 HK (6-param set, raw counts), seeded dynamics, 4 configurable anomaly
  scenarios, PUS-5 events. 56 tests; ruff/mypy --strict 0. **Packet/APID decode
  contract FROZEN** (ICD §2.5 + `control/simulator/PACKET_FORMAT.md`): HK APID 100
  / 25 octets, EVENT APID 101. The 3 ESCALATED decisions adopted as proposed.
  **Verified:** live Yamcs ingested our HK stream (`udp-in` count advanced, no
  SHORT_PACKET); seq-jump warnings were only APID-100 collision with residual
  quickstart traffic (gone once our MDB replaces the quickstart's).
- **Epic 2 / Phase 2 DONE** on `epic/control`: our XTCE MDB
  (`control/yamcs/src/main/yamcs/mdb/xtce.xml`, SpaceSystem `SGS`, labelled
  SIMULATED) replaces the quickstart's — decodes HK APID 100 to engineering units
  (calibrators ×0.001/×0.01/×1, enum mode) with soft/hard limits (ICD §2.6).
  **Verified live:** nominal stream → correct eng values, 0 alarms; `obc_overtemp`
  anomaly → OOL alarm on `/SGS/obc_temp`. Container matches `SecHdrFlag=Present` +
  `APID=100`.
- **Next: Phase 3 (telecommanding)** — TC set in the MDB; build/validate/send a TC
  via Yamcs UDP TC link; simulator accepts TCs + returns PUS-1 verification ACKs;
  Yamcs tracks the verification chain; health + OOL alarms queryable (REQ-SIM-03,
  REQ-TMC-04/05).

## Epic 1 (payload) — outcome

- Full PDGS chain: eumdac ingest → catalogue (sqlite) → cloud screen + simplified
  **N2 split-window SST** (cited MCSST coeffs) → validate vs official L2 WST →
  report; operator CLI (`run`/`ingest`/`process`/`validate`/`status`/`reprocess`/
  `dead-letter`). Layering `cli>operations>validation>processing>ingestion>
  catalogue>config` (import-linter). All 19 REQ-* covered; IV&V coverage gate.
- **Validated on REAL data:** real S3A SLSTR L1 vs official SL_2_WST → 330,274
  matchups, **bias −0.85 K, RMSE 1.22 K, 91.6 % within ±2 K → PASS**. Numbers are
  honest for a documented, simplified, cross-sensor algorithm (NOT operational).
- Offline demo runs on tiny labelled-**synthetic** fixtures with `config/fixture.toml`.

## Recent decisions worth remembering

- Language = English; timeliness = NTC; CI = GitLab + GitHub mirror; remote =
  **GitHub** `origin` (https://github.com/imertetsu/space-ground-segment) — `main`
  pushed. Don't push other branches without the user's OK.
- Verified collection IDs: L1 `EO:EUM:DAT:0411` (`SL_1_RBT`), L2 `EO:EUM:DAT:0412`
  (`SL_2_WST`) — `docs/icd/ICD.md`.
- Real cloud screening uses the S8 BT threshold only (`default.toml`
  `use_l1_cloud_flag=false`; real `cloud_in` bit semantics TBD).
- Commits do **not** include a Claude co-author trailer (user disabled
  `includeCoAuthoredBy`).

## Follow-ups (non-blocking)

- Wire the Data Store-provided checksum as the integrity expected digest.
- Decode the real SLSTR `cloud_in`/`confidence_in`/`l2p_flags` bit semantics.
- A `pdgs fetch` command for scene/AOI selection (currently a manual script).
- (control) Anomalies clamp raw to the hard band → OOL lands at the
  warning/critical boundary (WARNING). Let anomalies overshoot for a clean
  CRITICAL alarm.

## Known gotchas

- **EUMETSAT creds** live in `.env` (gitignored) and work; network/Bash needs
  `dangerouslyDisableSandbox` + the Windows CA bundle (Avast TLS interception).
- **Avast TLS interception** breaks SSL for pip/git/curl/Maven/Java (host + Docker).
  Per-tool fixes: pip → `PIP_CERT`/`SSL_CERT_FILE` = Windows CA bundle; git →
  `http.sslBackend=schannel`; curl → `ssl-no-revoke` (via `CURL_HOME/.curlrc`);
  Maven/Java (`mvnw`) → `JDK_JAVA_OPTIONS=-Djavax.net.ssl.trustStoreType=Windows-ROOT`
  + the curl fix. CI runners unaffected (committed Dockerfiles/CI clean).
- numpy/netCDF4 ABI import RuntimeWarning is benign.
- Real EO data/reports under `data/` + `D:/sgs` (gitignored/scratch — deletable).
- `.venv/`, `data/`, `*.nc`, `*.pem` are gitignored — never commit creds/EO data.

## Where to find things

- Methodology, conventions, pinned params, gates → `CLAUDE.md`
- Agent roster → `.claude/agents/` (`payload-developer` exists; control/viz later)
- Requirements / interfaces / verification → `docs/srd`, `docs/icd`, `docs/svp-svr`
- Operations → `docs/operations/operations-guide.md`
- Payload code → `payload/` (`payload/README.md` quickstart)

## Next step

- **Epic 2 — Phase 3 (telecommanding):** add a TC set to the XTCE MDB; via Yamcs,
  build/validate/send a TC over the UDP TC link (:10025); the Python simulator
  accepts TCs and returns PUS service-1 command-verification ACKs; Yamcs tracks
  the verification chain; health state + OOL alarms remain queryable
  (REQ-SIM-03, REQ-TMC-04/05).
