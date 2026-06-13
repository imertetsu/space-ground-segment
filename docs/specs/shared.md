# Epic 3 — Shared layers (unification) — ephemeral spec

> **EPHEMERAL.** This spec lives only while Epic 3 is in flight. It is **deleted in
> the same commit as the epic's last phase** (the flag-flip / close phase). No
> archive. Code, commits, tests, and the persistent docs (SRD, ICD, architecture
> overview, operations guide) are the institutional memory. Branch: `epic/shared`.

_Owner: product-owner. Created 2026-06-13. Requirements: REQ-INT-01..03 (SRD
"Epic 3 — Shared layers (unification) requirements"). Persistent state snapshot:
`docs/HANDOFF.md` (main owns it)._

---

## 1. Goal & scope

Epic 3 **unifies** the two completed segments — Epic 1 payload (PDGS, Python) and
Epic 2 control (FOS, Python simulator + Yamcs) — behind a shared cross-cutting
layer `shared/` with three contracts: **time-service**, **catalogue**, **anomaly**.
The epic is done when there is **one operator surface** that lists, across both
halves, current state, anomalies, and last results — all on the shared time base
and the shared catalogue.

In scope (this epic):

- `shared/` Python package: `time-service`, `catalogue`, `anomaly` contracts +
  implementations.
- A shared **PostgreSQL** catalogue (the `postgres` service already declared in
  `docker-compose.yml` under the `epic3` profile) implementing the existing
  payload `Catalogue` contract, recording payload products **and** control
  telemetry/anomaly references with unified provenance and a single query surface.
- A shared **anomaly model** covering payload processing failures and control OOL
  alarms with shared states + operator actions.
- A shared **time service**: OBT↔UTC correlation, one UTC base both segments
  stamp against.
- A single **operator surface**: a Python CLI (and optionally a small read-only
  HTTP API) over the shared catalogue + a read-only Yamcs-REST bridge for live
  control state.

Out of scope: Epic 4 viz; rewriting Epic-1 catalogue history; replacing Yamcs's
own archive; any change to the frozen Epic-2 packet/MDB/TC contracts (ICD §2.5–2.7);
write access from the operator surface into the control segment.

## 2. Pinned architecture (do not relitigate — set by the main session)

- **`shared/` cross-cutting layer (Python)** with three contracts: `time-service`,
  `catalogue`, `anomaly`. **Dependency rule:** `payload/` and `control/` depend
  **only on `shared/` contracts**; `shared/` depends on **neither** segment. The
  operator surface is a **read-only consumer** — it may read the **Yamcs REST API**
  for live control state (the same read-only pattern `viz/` will use in Epic 4),
  with **no code dependency on `control/`**.
- **Shared catalogue = PostgreSQL.** The payload's Epic-1 catalogue was built
  behind an interface (`pdgs.catalogue.repository.Catalogue` ABC, with
  `SqliteCatalogue` as the only impl today) precisely so Epic 3 adds a **PostgreSQL
  implementation of that same contract**. Control telemetry/anomalies are
  **referenced** into the shared catalogue (Yamcs keeps its own archive; a bridge
  records references + anomaly records).
- **Shared anomaly model:** one record type covering payload processing failures
  (the payload `FAILED` / dead-letter state) **and** control OOL alarms (from
  Yamcs), with shared states + operator actions.
- **Shared time service:** OBT↔UTC correlation (the PUS service-9 seed from Epic 2,
  operations guide "Time correlation (PUS-9)") → one UTC base both segments stamp
  against.
- **Operator surface:** a Python CLI (and/or a small read-only HTTP API) over the
  shared catalogue + a Yamcs-REST bridge for live control state. Language English;
  control telemetry is **SIMULATED** and **must stay labelled** everywhere.

### Data-honesty + dependency invariants (carried from SRD §5 / overview §2)

- **Payload data is REAL** (real EUMETSAT SLSTR, documented simplifications).
  **Control telemetry is SIMULATED** and **labelled "simulated" everywhere** it
  surfaces (catalogue rows, anomaly records, CLI/API output, docs). The unified
  surface must carry an explicit per-row origin/simulated label — unification must
  never erase the real-vs-simulated distinction.
- **Dependency direction:** segments → `shared/` contracts only, never each other;
  `shared/` → neither segment; operator surface = read-only consumer (catalogue +
  Yamcs REST), depends on no segment. Enforced by `import-linter` contracts (extend
  the existing payload contract set to cover `shared/`).

## 3. Riskiest-assumption-first phased plan

**The single riskiest assumption:** *a shared PostgreSQL catalogue + one operator
surface can present BOTH a payload product AND a control item together,
end-to-end, across the Python/Yamcs split.* Everything else (a clean anomaly state
machine, a precise time correlation) is comparatively low-risk refinement. So
Phase 0 proves the full cross-segment slice on day one, behind a dark flag.

> **Status legend:** each phase lists **Deliverables**, the **FROZEN CONTRACT** it
> introduces (frozen at phase end so later phases parallelize against it), the
> **acceptance criteria**, and **parallel-vs-serial** guidance (CLAUDE.md §3 tree).
> Ship dark per CLAUDE.md §8: Epic-3 work sits behind a feature flag (default off);
> the flag flips only in Phase 4 after the business decisions resolve.

---

### Phase 0 — Skeleton + cross-segment slice (RISKIEST)

Prove Postgres + the unified surface + the cross-segment integration immediately.

**Deliverables**

- The `shared/` Python package skeleton (own `pyproject`, `mypy --strict`, ruff,
  `lint-imports` contract, pytest) following the payload gate baseline.
- A shared **PostgreSQL** catalogue schema (initial, behind the existing
  `Catalogue` contract) — start the `postgres` service via the `epic3` compose
  profile; create the products table + a control-reference table.
- A `PostgresCatalogue(Catalogue)` thin implementation: enough of the contract
  (`register` / `get` / `list`) to round-trip one payload product.
- A control-reference recording path (manual/seed is acceptable in Phase 0): one
  control item (a telemetry-archive reference or one OOL alarm reference) recorded
  into the shared catalogue.
- A thin **operator CLI** (behind a dark flag, e.g. `SGS_SHARED=1`) that lists
  **ONE payload product AND ONE control reference together** from the shared
  catalogue, each row labelled with its origin (`payload` / `control-simulated`).

**FROZEN CONTRACT (end of Phase 0):** the `shared/` package boundary + the
`PostgresCatalogue` constructor/connection contract (DSN/env from the `epic3`
profile) + the dark-flag name. The catalogue *schema* is NOT frozen here — it is
frozen at the end of Phase 1.

**Acceptance criteria**

- AC0.1 `shared/` gates green (ruff, `mypy --strict` 0, pytest, `lint-imports`).
- AC0.2 `PostgresCatalogue` satisfies the `Catalogue` ABC (passes the same
  contract tests as `SqliteCatalogue` for the methods implemented in Phase 0).
- AC0.3 With the `epic3` profile up, the dark-flagged CLI prints **one payload
  product and one control reference in a single listing**, each labelled with its
  origin, the control one explicitly **simulated**.
- AC0.4 Dependency check: `shared/` imports neither `payload` nor `control`; the
  CLI imports no `control` code (it reads Yamcs via REST or reads recorded refs).

**Parallel-vs-serial:** SERIAL spine — schema → `PostgresCatalogue` → CLI slice
share the new contract and are each the next one's input. Single agent
(payload-developer, who owns the Python parts of `shared/`) or a tight serial pair.

---

### Phase 1 — Shared catalogue (REQ-INT-02)

Complete the unified catalogue: products + telemetry references, unified
provenance, single query surface.

**Deliverables**

- Full `PostgresCatalogue(Catalogue)` — every method of the `Catalogue` ABC
  (`register`, `get`, `list`, `update_status`, `set_provenance`).
- Payload **products** and control **telemetry references** both recorded with
  **unified provenance** (a single provenance shape: source segment, originating
  processor/MDB + version, input ids/source packet refs, run/ingest timestamp).
- A **single query surface** spanning both halves (one `list`/query returns
  payload products and control references with a common origin label).
- A control bridge that records telemetry-archive references / parameter snapshots
  into the catalogue (read-only against Yamcs — poll the REST API; see ESCALATED
  (c)). Yamcs keeps its own archive; the catalogue stores **references**, not a
  copy of telemetry.
- Tests: `PostgresCatalogue` passes the same contract suite as `SqliteCatalogue`;
  cross-segment listing test.

**FROZEN CONTRACT (end of Phase 1): the shared catalogue schema.** This is the
load-bearing freeze of the epic. It must cover:
- the payload product record (the existing `Product` / `Provenance` /
  `ProductStatus` shape — see `pdgs.catalogue.models`, which already declares
  itself a frozen contract);
- the control-reference record (telemetry-archive reference and/or OOL-alarm
  reference) with the Yamcs locator (instance / parameter / archive time range or
  alarm id) — a **reference**, never a telemetry copy;
- a common **origin / provenance** envelope on every row (`origin ∈ {payload,
  control}`, `simulated: bool`, source version, ingest/run UTC timestamp).
Record the frozen schema summary in the ICD (new "Shared catalogue" subsection)
when this phase lands.

**Acceptance criteria**

- AC1.1 `PostgresCatalogue` passes the **full** `Catalogue` contract test suite
  (parity with `SqliteCatalogue`).
- AC1.2 One query returns payload products **and** control references together,
  each carrying origin + simulated label + unified provenance.
- AC1.3 Control rows are **references** (Yamcs locators), verifiably not copies of
  telemetry; the bridge is read-only against Yamcs.
- AC1.4 NEW payload writes can target Postgres without rewriting Epic-1 SQLite
  history (see ESCALATED (b)); SQLite remains usable for offline payload dev.

**Parallel-vs-serial:** the **schema must be defined first** (DEFINE-FIRST node of
the §3 tree). Once frozen mid-phase, the `PostgresCatalogue` completion and the
control-bridge recorder touch different files behind the same schema → **PARALLEL**
(payload-developer on the impl; the control bridge — read-only REST consumer, no
`control/` code change — can run alongside).

---

### Phase 2 — Shared anomaly model (REQ-INT-03)

One anomaly record + state machine covering both halves, with shared operator
actions.

**Deliverables**

- A single **anomaly record** type + **state machine** in `shared/anomaly`,
  covering:
  - payload **processing failures** (the payload `FAILED` / dead-letter state —
    `ProductStatus.FAILED`, surfaced today via `pdgs dead-letter`);
  - control **OOL alarms** (from Yamcs — e.g. `/SGS/obc_temp` out-of-limits).
- Bridges that map each source into the shared model: payload dead-letter →
  anomaly record; Yamcs OOL alarm (read via REST) → anomaly record. The payload
  side adopts the shared anomaly contract for its dead-letter representation
  (payload-developer); the control side is bridged read-only.
- Shared **operator actions** on the unified model: **acknowledge** (both halves)
  and **reprocess** where applicable (payload only — control has no reprocess;
  acknowledge is the shared action there). Map "reprocess" to the existing
  `pdgs reprocess <id>` capability; acknowledge updates the shared anomaly record.

**FROZEN CONTRACT (end of Phase 2): the anomaly record + state machine.**
- States (proposed, tunable by the implementer within the contract): `OPEN` →
  `ACKNOWLEDGED` → `RESOLVED` (+ `REPROCESSING` for the payload reprocess path).
  One state set for both halves.
- Fields: `anomaly_id`, `origin ∈ {payload, control}`, `simulated: bool`,
  `source_ref` (catalogue product id **or** Yamcs alarm/parameter ref), `kind`
  (`processing_failure` | `ool_alarm`), `severity`, `state`, `opened_at`,
  `updated_at`, `detail`.
- Actions: `acknowledge` (both), `reprocess` (payload only; control raises
  unsupported). Record the frozen contract in the ICD/SRD as appropriate.

**Acceptance criteria**

- AC2.1 A payload dead-letter and a Yamcs OOL alarm both materialise as anomaly
  records in the **same** model/states, each labelled origin + simulated.
- AC2.2 `acknowledge` works on both; `reprocess` works on a payload anomaly and is
  cleanly rejected (unsupported) on a control anomaly.
- AC2.3 The operator surface (extended from Phase 0/1) lists anomalies across both
  halves with state + actions.
- AC2.4 Gates green across `shared/` and the touched payload code.

**Parallel-vs-serial:** the anomaly contract is a DEFINE-FIRST node. Define it
(1 agent/main), then the payload adoption and the control bridge touch different
dirs → **PARALLEL**. Depends on Phase 1 only for the catalogue `source_ref`
linkage, so it can start once the Phase 1 schema is frozen.

---

### Phase 3 — Shared time service (REQ-INT-01)

OBT↔UTC correlation both segments use; consistent UTC timestamps on products and
telemetry references.

**Deliverables**

- A `shared/time_service` utility implementing **OBT↔UTC correlation** building on
  the Epic-2 **PUS service-9** seed (the simulator omits a PUS time field today and
  Yamcs stamps wallclock — operations guide "Time correlation (PUS-9)"). Provide a
  correlation function `obt → utc` (and inverse) from a correlation pair/rate, and
  one UTC base both segments stamp against.
- Payload products already carry UTC (the catalogue stores ISO-8601 UTC); telemetry
  **references** in the shared catalogue gain a **consistent UTC timestamp** derived
  through the time service, so product and telemetry-ref timestamps are comparable.
- Tests: round-trip OBT↔UTC; a payload product and a control reference share one
  UTC base; the operator surface can sort/correlate both on UTC.

**FROZEN CONTRACT (end of Phase 3): the time-service interface** — the correlation
API (`obt_to_utc`, `utc_to_obt`, correlation source) and the rule that **every
catalogue row carries a UTC timestamp on the shared base**. Document the
correlation model + simplifications in the ICD (extend §2.2 service-9 / the time
section) and the operations guide.

**Acceptance criteria**

- AC3.1 OBT↔UTC correlation round-trips within a documented tolerance.
- AC3.2 A payload product and a control telemetry reference report timestamps on
  the **same UTC base**; the unified listing orders both correctly by UTC.
- AC3.3 Any simplification in the correlation (e.g. seeded/fixed correlation pair
  vs a live service-9 report) is documented, not presented as operational.

**Parallel-vs-serial:** the time service is largely standalone (a utility +
stamping at write time). It shares the catalogue **schema** (already frozen in
Phase 1) for where the UTC field lives, so it is **PARALLEL** with Phase 2 once the
Phase 1 schema is frozen — different files, contract defined. Keep serial only if
the same write paths are being edited concurrently.

---

### Phase 4 — Single operator surface + docs + close

The cross-segment operator surface on the shared base, the docs unification, and
the spec deletion.

**Deliverables**

- The single **operator surface** (CLI for MVP; small read-only HTTP API optional
  — see ESCALATED (a)) that, across **both halves**, lists: **current state**
  (payload product status + live control state via the Yamcs REST bridge),
  **anomalies** (the shared anomaly model), and **last results** (latest payload
  validation result + latest telemetry reference) — all on the shared time base and
  the shared catalogue. Every control row stays **labelled simulated**.
- **Flag flip:** turn the dark flag on (default the unified surface) once the
  ESCALATED business decisions resolve.
- **Docs unification:**
  - SRD: REQ-INT-01..03 section (added by product-owner; this task).
  - ICD: a "Shared layers (Epic 3)" section recording the frozen contracts —
    catalogue schema (Phase 1), anomaly model (Phase 2), time-service interface
    (Phase 3).
  - Architecture overview: mark `shared/` as implemented (it is currently mapped
    as forward-looking).
  - Operations guide: a **unification section** — how to run the shared catalogue
    (`epic3` profile), the operator CLI/API, and how the time base + anomaly model
    + catalogue tie the two halves together.
  - SVP/SVR: add REQ-INT-01..03 to the traceability matrix.
- **Delete `docs/specs/shared.md` in this phase's final commit.** Main session
  also updates `docs/HANDOFF.md` (main owns it — not this spec, not this agent).

**Acceptance criteria**

- AC4.1 One command/endpoint lists, across both halves, **state + anomalies + last
  results**, all on the shared UTC base + shared catalogue, control rows labelled
  simulated.
- AC4.2 The operator surface is **read-only** w.r.t. control (Yamcs REST + recorded
  refs); no import of `control/`; `lint-imports` contracts kept across `shared/`,
  `payload/`, and the surface.
- AC4.3 All gates green; REQ-INT-01..03 each have a passing mapped test in the SVP
  matrix.
- AC4.4 The spec is deleted in the closing commit; `docs/HANDOFF.md` reflects the
  new state (main).

**Parallel-vs-serial:** the surface consumes contracts frozen in Phases 1–3, so the
CLI/API build is **PARALLEL** with the doc updates (different files). The flag flip
is the **last** serial step, gated on the ESCALATED decisions (CLAUDE.md §4: a
resolved business decision blocks only the final flag-flip phase — implementation
of Phases 0–3 proceeds while decisions are pending).

---

## 4. Dependency / parallelism summary

```
Phase 0 (riskiest cross-segment slice)        SERIAL spine
   └─ freezes: shared/ boundary, PostgresCatalogue ctor, dark-flag name
Phase 1 (shared catalogue, REQ-INT-02)        schema = DEFINE-FIRST, then PARALLEL
   └─ freezes: SHARED CATALOGUE SCHEMA  ◄── load-bearing freeze
        ├─ Phase 2 (anomaly, REQ-INT-03)  ─┐ PARALLEL once schema frozen
        └─ Phase 3 (time service, REQ-INT-01)┘ (different files, contracts defined)
Phase 4 (operator surface + docs + close)     surface ∥ docs; flag flip LAST
```

Freeze each cross-phase contract at the end of the phase that introduces it
(CLAUDE.md §3) and record it in the persistent docs (ICD/SRD), so the spec can be
safely deleted at close without losing the contract.

---

## 5. ESCALATED — business decisions for the user (agent-proposed defaults)

Each item has a recommended default so implementation (Phases 0–3) can proceed
while the decision is pending; only the Phase-4 flag flip is blocked.

1. **Operator surface = CLI for the MVP** *(proposed; the API is optional/tunable).*
   - **Recommended:** ship a Python **CLI** as the MVP operator surface; defer a
     small read-only HTTP API to an optional later increment (it can reuse the same
     shared-catalogue + Yamcs-REST read paths). Lower surface area, fastest path to
     the cross-segment listing. **Tunable:** add the read-only API in Phase 4 if a
     web/automation consumer is wanted now (it is also what Epic-4 viz will read).

2. **Catalogue migration = add a Postgres impl, NEW writes go to Postgres** *(proposed).*
   - **Recommended:** add `PostgresCatalogue` behind the existing `Catalogue`
     contract and route **new** writes to Postgres; **do not** rewrite/migrate
     Epic-1 SQLite history. Keep **SQLite** as the offline payload-dev catalogue
     (no Postgres needed for local payload work). **Tunable:** a one-off
     backfill/import of existing SQLite rows into Postgres if a single historical
     view is required — out of scope for the MVP unless requested.

3. **Control bridge = poll the Yamcs REST API for alarms/parameters (read-only)** *(proposed).*
   - **Recommended:** the control bridge **polls the Yamcs REST API** (the
     endpoints already documented in the operations guide: realtime parameters,
     alarms) to record telemetry references + OOL alarms into the shared catalogue
     / anomaly model. **Read-only**, no code dependency on `control/`, mirrors the
     read-only consumer pattern `viz/` will use. **Tunable:** swap polling for a
     push/stream subscription later if latency matters; not needed for the MVP.

> All three preserve the **data-honesty** rule (control stays simulated-and-labelled)
> and the **dependency-direction** rule (read-only consumer, no cross-segment code
> dependency). None changes a frozen Epic-1/Epic-2 contract.

---

## 6. Known seeds, constraints & open questions

- **Postgres service already exists** in `docker-compose.yml` under the `epic3`
  profile (`postgres:16`, db `sgs_catalogue`, user `sgs`) — wire it, don't add a
  new service.
- **Catalogue interface already exists:** `pdgs.catalogue.repository.Catalogue`
  (ABC) + `SqliteCatalogue`; the per-product record (`Product` / `Provenance` /
  `ProductStatus`) is already a frozen contract in `pdgs.catalogue.models`. Reuse
  it; do not fork the product shape.
- **Time-correlation seed:** PUS service-9 is *seeded only* (simulator omits a PUS
  time field; Yamcs stamps wallclock — operations guide). The shared time service
  must document whatever correlation it actually uses and label any simplification.
- **Frozen Epic-2 contracts are off-limits:** ICD §2.5 (packet), §2.6 (MDB), §2.7
  (TC/verification) do not change in Epic 3.
- **Open question (for main/implementers):** does the control bridge record a
  *telemetry-archive reference* (time range / archive locator), a *parameter
  snapshot*, or both? The Phase-1 schema must pick one as the canonical control
  reference; the recommendation is an **archive reference + alarm reference** (no
  parameter-value copies), but confirm against what the Yamcs REST archive API
  exposes when Phase 1 starts.
- **Open question:** anomaly "last results" semantics for control — likely the
  latest OOL alarm and current spacecraft mode/state via REST; confirm during
  Phase 4 surface design.
