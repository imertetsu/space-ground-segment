# HANDOFF — SpaceGroundSegment

> Single source of project state. Living snapshot — rewritten/pruned at the end of
> every epic, never endlessly appended. Cap ~150 lines. Read this first when
> re-entering the project after a gap. Full methodology + conventions: `CLAUDE.md`.

_Last updated: 2026-06-13 — Epic 1 (payload) CLOSED and merged to `main`._

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

- None. Epic 1 is complete and on `main`.

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

- Language = English; timeliness = NTC; CI = GitLab + GitHub mirror; remote will be
  **GitHub** (not yet created/pushed — do not publish without the user's OK).
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

## Known gotchas

- **EUMETSAT creds** live in `.env` (gitignored) and work; network/Bash needs
  `dangerouslyDisableSandbox` + the Windows CA bundle (Avast TLS interception).
- **Avast TLS interception** breaks `pip` cert verification (host + Docker): point
  pip at a Windows CA bundle (`PIP_CERT`/`SSL_CERT_FILE`); CI runners are
  unaffected (committed `Dockerfile` is clean).
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

- **Epic 2 — FOS control:** spacecraft simulator emitting CCSDS/PUS → Yamcs + XTCE
  MIB → decommutation → limit checking → telecommanding. Branch `epic/control`;
  run prompt-engineer → product-owner for `docs/specs/control.md`, then Phase 0.
