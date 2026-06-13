# Agent roster — SpaceGroundSegment

Project agents for the SSS methodology (see `CLAUDE.md §2`). Each agent has a tool
set, a directory scope, and a "never touches" boundary. The main session
orchestrates and owns verification — agents never commit.

## Defined now

| Agent | Writes? | Scope | Never touches |
|---|---|---|---|
| `prompt-engineer` | No (text out) | — reads only | Any file (Write/Edit not granted) |
| `product-owner` | Yes | `docs/` only (not `HANDOFF.md`) | Source, tests, build, CI |
| `architect` | No (text out) | — reads only | Any file (read-only planner) |
| `payload-developer` | Yes | `payload/` (Python parts of `shared/` later) | `control/`, `viz/`, `docs/`, CLAUDE.md, CI |

## Pending their epic

Created when their epic starts and their territory exists:
- `control-developer` — Java/Yamcs + simulator, scoped to `control/` (Epic 2).
- `viz-developer` — web app, scoped to `viz/` (Epic 4).

When creating an implementer agent, give it:
- **Tools:** Read, Write, Edit, Glob, Grep, Bash (to run its own gates).
- **Scope:** the exact directories it owns.
- **Never touches:** other implementers' directories, `docs/specs/` ownership
  (that's the product-owner's), and CI/release config unless explicitly in scope.
- A reminder: **do not commit** — leave changes in the working tree for the main
  session to verify against the gates and the diff.
