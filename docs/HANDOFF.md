# HANDOFF — SpaceGroundSegment

> Single source of project state. Living snapshot — rewritten/pruned at the end of
> every epic, never endlessly appended. Cap ~150 lines. Read this first when
> re-entering the project after a gap. Full methodology lives in `CLAUDE.md`.

_Last updated: 2026-06-13 — methodology setup (commit zero)._

## Stack snapshot

- **PENDING the project prompt.** No stack, framework, datastore, or build tool
  chosen yet. This repo currently contains only the methodology scaffold:
  `CLAUDE.md`, this file, `docs/specs/`, the agent roster in `.claude/agents/`,
  and a base `.gitignore` / `README.md`.
- Quality gates: not yet wired (see the PENDING table in `CLAUDE.md §0`).
- Type-check baseline: not yet recorded.

## Active feature flags

- None yet.

## In-flight work

- None. Awaiting the project prompt to define the first epic, the stack, the
  architecture style, and the implementer domains.

## Recent decisions worth remembering

- 2026-06-13: Adopted the SSS (Spec → Sketch → Ship) methodology from commit
  zero. See `CLAUDE.md`.
- 2026-06-13: Did an intentionally stack-agnostic initial setup at the user's
  request; stack/purpose/architecture deferred to the forthcoming project prompt.

## Known gotchas

- Platform is Windows (PowerShell default shell; Bash also available). Prefer
  cross-platform commands; mind path separators and line endings (`.gitattributes`
  pins LF for text).

## Where to find things

- Methodology & conventions → `CLAUDE.md`
- Agent roster (roles, tool scopes, boundaries) → `.claude/agents/`
- In-flight epic specs → `docs/specs/<epic>.md` (none yet)
- Project state (this file) → `docs/HANDOFF.md`

## Next step

- Receive the project prompt → run `prompt-engineer` → `product-owner` to produce
  `docs/specs/<first-epic>.md`. Pin §0 parameters in `CLAUDE.md`, wire the quality
  gates, scaffold the architecture, and create the implementer agents. Then start
  Phase 0 (riskiest assumption first, behind a dark flag).
