# Agent roster — SpaceGroundSegment

Project agents for the SSS methodology (see `CLAUDE.md §2`). Each agent has a tool
set, a directory scope, and a "never touches" boundary. The main session
orchestrates and owns verification — agents never commit.

## Defined now (stack-agnostic)

| Agent | Writes? | Scope | Never touches |
|---|---|---|---|
| `prompt-engineer` | No (text out) | — reads only | Any file (Write/Edit not granted) |
| `product-owner` | Yes | `docs/` only | Source, tests, build, CI |
| `architect` | No (text out) | — reads only | Any file (read-only planner) |

## Pending the stack/architecture decision

Implementer agents — one per IMPLEMENTER DOMAIN — are created once the stack and
architecture are pinned (from the project prompt). Each will be scoped to its own
directories and forbidden from crossing into another's territory. Expected shape
(to be confirmed): e.g. `backend-developer`, `frontend-developer`, `infra`.

When creating an implementer agent, give it:
- **Tools:** Read, Write, Edit, Glob, Grep, Bash (to run its own gates).
- **Scope:** the exact directories it owns.
- **Never touches:** other implementers' directories, `docs/specs/` ownership
  (that's the product-owner's), and CI/release config unless explicitly in scope.
- A reminder: **do not commit** — leave changes in the working tree for the main
  session to verify against the gates and the diff.
