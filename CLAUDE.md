# CLAUDE.md — SpaceGroundSegment

Permanent contract for every agent (human or AI) working in this repo. Read this
first. Keep it lean; let the spec, commits, and tests carry the detail.

---

## 0. Project parameters

| Parameter | Value |
|---|---|
| `PROJECT_NAME` | SpaceGroundSegment ("Mini Space Ground Segment") |
| `ONE_LINE_PURPOSE` | A portfolio ground segment demonstrating both halves of satellite ops — PDGS (payload: real Sentinel-3 SLSTR L1→L2 + cal/val) and FOS (control: simulated CCSDS/PUS TM/TC via Yamcs) — unified by shared layers and a 3D flow view; engineered to read as operationally credible (EUMETSAT/ESA-style), with every simplification explicitly documented. |
| `STACK` | Python 3.11+ (payload: eumdac, xarray, netCDF4, numpy) · Java + Yamcs, XTCE MIB (control) · PostgreSQL (shared catalogue) · CesiumJS + satellite.js / Three.js (3D viz) · Docker + docker-compose · CI: GitLab CI (canonical) + GitHub Actions (mirror). |
| `ARCHITECTURE_STYLE` | Modular monorepo. Two bounded contexts — `payload/` (PDGS) and `control/` (FOS) — plus a shared cross-cutting layer `shared/` (time-service, catalogue, anomaly). `viz/` is a read-only consumer. **Dependency rule:** segments depend only on `shared/` contracts, **never on each other**; `viz/` consumes read-only APIs (or labelled canned data) only. Within `payload/` (Python), layered: `cli → (ingestion \| processing \| validation) → catalogue → config`. |
| `ARCH_ENFORCEMENT` | `import-linter` (`lint-imports`) enforces the Python layering and fails the build on a violation. ArchUnit will guard the Java/control side (Epic 2). Cross-segment isolation is enforced by directory ownership + import-linter contracts. |
| `PRIMARY_LANGUAGE` (user-facing copy) | **English** — all deliverables (docs, UI, code, commit messages). (Maintainer conversation may be Spanish; artifacts are English.) |
| `MONETIZATION / TIERS` | n/a (portfolio project). |
| `IMPLEMENTER DOMAINS` | `payload-developer` (Python, `payload/` + Python parts of `shared/`) · `control-developer` (Java/Yamcs + simulator, `control/`) · `viz-developer` (web, `viz/`). Created per-epic; only `payload-developer` exists today. |

### Quality gates

Gates are per-segment. For **Epic 1 (payload, Python)** run from `payload/`:

| Gate | Command (run from `payload/`) | Baseline |
|---|---|---|
| lint | `ruff check .` | 0 errors (Phase 0) |
| format | `ruff format --check .` | clean (Phase 0) |
| type-check | `mypy src` | **0 errors** (recorded Phase 0, 2026-06-13) |
| tests | `pytest` | 0 failures (Phase 0) |
| arch-check | `lint-imports` | contracts kept (Phase 0) |
| build | `docker compose build payload` (from repo root) | builds (Phase 0) |

> Type-check baseline = **0 errors** under `mypy --strict` on the skeleton. Any new
> mypy error vs this baseline blocks the phase. Update this table if the baseline
> legitimately changes. Control (Java) and viz (web) gates are added with their epics.

---

## 1. Methodology — SSS (Spec → Sketch → Ship)

Tailored for AI-agent development: fast, parallel, memory-less agents. Not Scrum,
not Kanban. Five pillars:

1. **Ephemeral specs.** When an epic starts, the planning agent writes a spec at
   `docs/specs/<epic>.md`. The spec lives only while the epic is in flight. When
   the epic's last commit lands, the spec is **deleted in that same commit**. No
   `archive/`. Code, commits, and tests are the institutional memory.
2. **Single-pass shipping by phase.** The unit of work is a *phase* from the
   spec, not a time window. One phase = one (or a few) commits. Never accumulate
   half-done work between phases.
3. **Hard constraints in every brief.** Every prompt to an agent ends with a
   "Hard constraints" section: what must NOT be touched, and which shared files
   must be `Edit`ed (not rewritten). Agents drift without pins.
4. **Parallel by default.** If two work units don't share a file AND their
   contract is already defined, launch them as parallel agents in one message.
   Serial only on a real dependency — and justify it in the brief.
5. **Trust but verify.** Agents report what they *intended*. The main session
   checks `git status`, reads the diff, and runs the gates before marking
   anything done.

## 2. Agents & pipeline

Roster (configs live in `.claude/agents/`):

- **prompt-engineer** (text in/out only) — turns a rough idea into a structured
  brief. Use before kicking off a new epic.
- **product-owner** (writes only under `docs/`) — turns a brief into a phased,
  testable spec with acceptance criteria; marks business decisions `ESCALATED`.
- **architect** (read-only, no write tools) — for non-trivial features: weighs
  trade-offs, picks an approach, sketches module layout and phase plan. Produces
  plans, never edits code.
- **implementer agents**, one per IMPLEMENTER DOMAIN (e.g. `backend-developer`,
  `frontend-developer`) — each scoped to its own directories, never crossing
  into another's. They write code and tests. _Created once the stack and
  architecture are pinned._

Pipeline:

```
user → main → prompt-engineer (refine) → main → product-owner → spec
                                                      ↓
                                architect (optional, hard tech calls)
                                                      ↓
user ← main ← (only business decisions) ← main ← implementers in parallel per phase
                                                      ↓
                                main verifies (gates + diff) → commit
                                (drops the spec on the epic's last commit)
```

## 3. Parallelism decision tree

```
Do the tasks touch shared files?
├── Yes → SERIAL.
└── No → Is one's output the other's input?
         ├── Yes → SERIAL.
         └── No → Is there a shared contract (API, schema, type)?
                  ├── Defined already → PARALLEL.
                  ├── Not defined → DEFINE FIRST (1 agent or main), then PARALLEL.
                  └── No contract → PARALLEL, no question.
```

Freeze the cross-phase contract (response schema / interface / types) at the end
of the phase that introduces it, so later phases can parallelize against it.

## 4. Decision boundaries

**Escalate to the user (business):**
- Scope; what's in / out; the MVP boundary.
- Monetization & tier gating.
- Domain-policy / UX calls that change user outcomes (safety, content policy,
  pricing-adjacent behavior).
- Persona prioritization, deadlines, cross-initiative sequencing.

Present escalations as a short numbered list, each with a recommended option. A
resolved business decision usually blocks only the final flag-flip phase — so
implementation can start while decisions are pending.

**Agents own (technical):**
- Naming, file/layer organization within the architecture rules.
- Performance budgets, cache TTLs, retries, timeouts.
- Test fixtures, telemetry thresholds, copy variants within the design system.
- MVP-vs-v2 splits when the trade-off is purely technical.

## 5. Definition of Done (per phase)

ALL must hold before a phase is complete:
- arch-check green (ARCH_ENFORCEMENT).
- type-check: no new errors vs the recorded baseline.
- tests green (except documented, pre-existing baseline failures — list them).
- lint + format clean on touched files.
- UI phases: build green + a real browser/device check of the visible change.
- `git diff` reviewed by the main session — not just the agent's report.
- If it's the epic's last phase: the spec is deleted in that commit.
- `docs/HANDOFF.md` updated to the new state.

## 6. Persistent vs ephemeral docs

- `CLAUDE.md` (permanent) — this file: methodology + conventions, commands,
  architecture, gotchas. The contract every agent reads.
- `docs/HANDOFF.md` (permanent, living snapshot) — the single source of project
  state. Rewritten/pruned at the end of every epic, never endlessly appended.
  Cap ~150 lines. Read it first when re-entering the project after a gap.
- `docs/specs/<epic>.md` (ephemeral) — one per in-flight epic, deleted on close.
- **No `docs/archive/`.** It does not exist. Delete, don't hoard.

## 7. Anti-patterns (do not do)

- Keeping old specs "just in case" — delete them on epic close.
- A `docs/archive/` folder.
- Sprints / standups / story points / velocity.
- Giant specs for small features.
- Skipping the verify step (trusting the agent's report over the diff + gates).
- Letting an agent define scope — they polite-bloat. Scope is the user's call.
- Rewriting a shared file when a surgical `Edit` would do.

## 8. Conventions

- **Branching:** branch-per-epic — `epic/<short-name>`. The methodology setup and
  other foundational changes land directly on `main`.
- **Commits:** commit-per-phase. One phase = one (or a few) commits.
- **Commit message style:** `<type>(<scope>): <subject>` where
  `type ∈ {feat, fix, chore, docs, refactor, test, build, perf}` and `scope` is
  the phase or module (e.g. `feat(telemetry): decode CCSDS frames — phase 1`).
  End commit bodies with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Feature flags:** ship dark. Unfinished epic work goes in behind a flag
  (default off); the flag flips on the epic's last phase, after the business
  decisions resolve.
- **Verification is the main session's job**, not the implementer's. Always read
  the diff and run the gates.

## 9. Brief template (use for every agent task)

```
GOAL: <one sentence — the outcome, not the steps>
CONTEXT: <verified facts about the current code the agent must trust; file paths>
SCOPE (this phase only): <the exact deliverables>
OUT OF SCOPE: <what belongs to a later phase — name it so the agent doesn't drift>
CONTRACT: <the API/schema/types this work must conform to, if any>
TASKS:
- (<layer/dir>) <task> ...
DEFINITION OF DONE: run and REPORT ACTUAL OUTPUT of <the gate commands>;
  <known baseline failures to ignore>.
HARD CONSTRAINTS:
- Do NOT touch: <dirs/files outside this agent's scope; other agents' territory>.
- Use Edit (not rewrite) on shared files: <list>.
- Respect <ARCHITECTURE_STYLE> layering; <other invariants>.
- Do not commit; leave changes in the working tree for main to verify.
```
