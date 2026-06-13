# HANDOFF — SpaceGroundSegment

> Single source of project state. Living snapshot — rewritten/pruned at the end of
> every epic, never endlessly appended. Cap ~150 lines. Read this first when
> re-entering the project after a gap. Full methodology lives in `CLAUDE.md`.

_Last updated: 2026-06-13 — Epic 1 (payload), Phase 0 (skeleton + CI) complete._

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
- **Type-check baseline:** `mypy --strict` = **0 errors** (11 files). Recorded
  2026-06-13. Any new error blocks a phase.

## Active feature flags

- None yet. (Unfinished epic work ships dark; flags flip on the epic's last phase.)

## In-flight work

- **Epic 1 / Phase 0 DONE** on branch `epic/payload`: package skeleton, layered
  module stubs, gates wired + green, CI (GitLab + GitHub mirror), Dockerfile +
  compose, ECSS docs (SRD/ICD/SVP/architecture/operations), ephemeral spec
  `docs/specs/payload.md`.
- **Next: Phase 1 (ingestion + catalogue)** — but **BLOCKED on EUMETSAT Data Store
  credentials** (decision: proceed without for now). Offline/fixture work and the
  catalogue-schema + L1-reader contract design can start; live download cannot.

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

## Known gotchas

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
