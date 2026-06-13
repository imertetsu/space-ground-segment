# HANDOFF — SpaceGroundSegment

> Single source of project state. Living snapshot — rewritten/pruned at the end of
> every epic, never endlessly appended. Cap ~150 lines. Read this first when
> re-entering the project after a gap. Full methodology lives in `CLAUDE.md`.

_Last updated: 2026-06-13 — Epic 1 (payload), Phase 2 (processing chain) complete (offline/mock)._

## Stack snapshot

- **Project:** "Mini Space Ground Segment" — portfolio ground segment. Two halves
  (PDGS payload / FOS control) + shared layers + 3D view. Build epic-by-epic.
- **Now building:** Epic 1 = `payload/` (PDGS), Python. Other segments are
  placeholders until their epics (control = Epic 2, shared = Epic 3, viz = Epic 4).
- **Stack:** Python 3.11 (payload) · Java 17 + Yamcs (control, later) ·
  PostgreSQL (shared, later) · CesiumJS/Three.js (viz, later) · Docker · CI:
  GitLab (`.gitlab-ci.yml`) canonical + GitHub Actions mirror.
- **Quality gates (payload, run from `payload/`):** `ruff check .` ·
  `ruff format --check .` · `mypy src` · `pytest` · `lint-imports` ·
  `docker compose build payload`. All green at Phase 0.
- **Type-check baseline:** `mypy --strict` = **0 errors** (file count grows per
  phase). Any new error blocks a phase.

## Active feature flags

- None yet. (Unfinished epic work ships dark; flags flip on the epic's last phase.)

## In-flight work

- **Epic 1 / Phase 0 DONE** (commit on `epic/payload`): skeleton, gates, CI,
  Dockerfile/compose, ECSS docs + spec.
- **Epic 1 / Phase 1 DONE (offline/mock)** on `epic/payload`: catalogue (sqlite,
  FROZEN `Product`/`ProductStatus`/`Provenance` + `Catalogue` ABC), ingestion
  (`DataStoreClient` ABC, `OfflineDataStoreClient` default + `EumdacClient`,
  `make_client` OFFLINE-by-default, integrity sha256, `ingest` with dead-letter
  routing), FROZEN L1-reader contract (`L1Scene`/`read_l1_rbt`) + `L2Reference`,
  tiny **labelled-synthetic** SLSTR fixtures + deterministic generator, CLI
  `ingest`/`status`. 48 tests; gates green; mypy --strict 0 (19 files).
- **Epic 1 / Phase 2 DONE (offline/mock)** on `epic/payload`: versioned config
  (`ProcessingConfig`, tomllib; `config/default.toml` = cited MCSST coeffs,
  `config/fixture.toml` = synthetic demo coeffs), `screen_clouds` (threshold +
  L1 flag), `retrieve_sst` (N2 split-window, NaN over cloud, out-of-range
  flagged), FROZEN `DerivedSstProduct` + netCDF writer + `process_scene`
  orchestration (stamps provenance, registers `SST_L2_DERIVED` PROCESSED), CLI
  `process`. 67 tests; gates green; mypy --strict 0.
- **Decision (user):** build payload with **mock data now**, switch to real data
  when the API key arrives. Real-data run is the only remaining gate to true
  "Epic 1 done".
- **Next: Phase 3 (IV&V + validation)** — co-locate derived SST vs official L2,
  stats (bias/RMSE/std/match%/count), threshold gate, report + difference plot.
  Unblocked (consumes the frozen DerivedSstProduct + L2Reference).

## Recent decisions worth remembering

- Stack/architecture pinned in `CLAUDE.md §0` (modular monorepo, two bounded
  contexts + shared layer; payload layered cli→…→config, enforced by import-linter).
- Deliverables language = **English**; payload timeliness = **NTC**; CI = GitLab
  canonical + GitHub mirror; remote will be **GitHub** (not yet created/pushed —
  do not publish without the user's OK).
- Verified SLSTR collection IDs: L1 `EO:EUM:DAT:0411` (`SL_1_RBT`), L2
  `EO:EUM:DAT:0412` (`SL_2_WST`). In `docs/icd/ICD.md`.
- **Open (for the user):** (a) EUMETSAT credentials; (b) sign-off on validation
  acceptance thresholds proposed in `docs/specs/payload.md §7`; (c) AOI/scene for
  the demo matchup; (d) confirm nadir-only MVP. None block Phase 0.
- SST split-window **coefficient source is a real TBD** for Phase 2 — must cite a
  public reference; do not invent coefficients.

## Real-data path TODOs (when EUMETSAT credentials arrive)

- `EumdacClient.download` currently writes the product stream to a single path;
  real `SL_1_RBT`/`SL_2_WST` arrive as **zipped SAFE** → add unzip-to-folder.
- Integrity check in `ingest` is a self-consistency sha256 (no external expected
  digest offline); wire the Data Store-provided checksum as the expected value.
- Confirm the real `SL_2_WST` internal netCDF filename (synthetic uses `L2P.nc`;
  `read_l2_wst` keys on it) and the real scale/offset + flag bit semantics.

## Known gotchas

- **numpy/netCDF4 ABI RuntimeWarning** ("ndarray size changed") on import is
  benign (wheel build mismatch), not a failure.
- **Avast TLS interception** on this machine breaks `pip` cert verification (host
  AND inside Docker). Host venv install works by pointing pip at a Windows CA
  bundle (`PIP_CERT`/`SSL_CERT_FILE` → exported `Cert:\*\Root`). Local
  `docker compose build` needs the CA supplied to the build or Avast HTTPS
  scanning disabled. **CI runners are unaffected** (no interception) — the
  committed `Dockerfile` is intentionally clean.
- Windows host: PowerShell default; Bash available. `.gitattributes` pins LF.
- `.venv/`, `data/`, `*.nc`, `*.pem` are gitignored — never commit creds or EO data.

## Where to find things

- Methodology & conventions, pinned params, gate commands → `CLAUDE.md`
- Agent roster → `.claude/agents/` (`payload-developer` exists; control/viz later)
- Requirements / interfaces / verification → `docs/srd`, `docs/icd`, `docs/svp-svr`
- In-flight Epic 1 spec (ephemeral) → `docs/specs/payload.md`
- Payload code + gates → `payload/` (`payload/README.md` for the quickstart)

## Next step

- Provide EUMETSAT Data Store credentials to unblock Phase 1 live ingestion, OR
  start Phase 1 design now: freeze the **catalogue schema** + **L1-reader
  contract** (the freeze points that let Phase 2's two processors run in
  parallel), delegating implementation to `payload-developer`. Main verifies
  gates + diff, commits per phase.
