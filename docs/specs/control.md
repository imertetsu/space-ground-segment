# Epic 2 — Control (FOS) spec

> **EPHEMERAL.** This is the in-flight spec for Epic 2 (FOS / control). It lives
> only while the epic is in flight and is **deleted in the epic's last commit**
> (Phase 4). Institutional memory is the code, commits, tests, the SRD, the ICD,
> and `docs/HANDOFF.md` — not this file. Full methodology: `CLAUDE.md`.

_Branch: `epic/control`. Scope: the `control/` bounded context only._

---

## 0. Goal & frame

Build a **FOS** (Flight Operations Segment): a spacecraft **simulator** emitting
CCSDS / PUS telemetry over UDP into **Yamcs**, which decommutates it against an
**XTCE** mission database (MDB), limit-checks spacecraft health, and supports
telecommanding. The decommutated, calibrated parameters and out-of-limit (OOL)
alarms are surfaced to the operator via the Yamcs web UI.

**Telemetry is SIMULATED.** It is structurally **CCSDS / PUS-compliant** but
synthetically generated, and must be **labelled "simulated" everywhere** it
appears (data, web UI, logs, reports, docs) — per SRD §5. This is not operational
software; every simplification is documented.

### Pinned decisions (record — do not relitigate)

| Decision | Value |
|---|---|
| Control core (MCS) | **Yamcs** (Java 17), based on the **Yamcs quickstart** |
| Build / run | **Maven Wrapper (`mvnw`)** — no global Maven. Lives in `control/yamcs/` |
| Simulator | **Python** (`control/simulator/`), emits CCSDS Space Packets + PUS secondary header over UDP |
| Transport | **UDP** — TM in, TC out |
| MDB | **XTCE** XML |
| Phase 0 runtime | Yamcs **natively** via `mvnw` (prove the loop); docker-compose comes in Phase 4 |
| Known hurdle | Maven downloads hit Avast TLS interception → a Java truststore must be wired from the Windows CA bundle (main session handles the mechanics) |

> Simulator-in-Python justification (recorded): reuse the project's Python
> toolchain + fast iteration; it mirrors the quickstart's Python packet sender;
> Yamcs is the Java MCS. The dependency rule still holds — `control/` depends only
> on `shared/` contracts, never on `payload/`.

### Verified facts the implementers must trust (do not re-derive, do not extend)

- **CCSDS Space Packet** (CCSDS 133.0-B-2): 6-octet primary header =
  version(3b) + type(1b) + secondary-header-flag(1b) + APID(11b) |
  sequence-flags(2b) + sequence-count(14b) | packet-data-length(16b, = octets in
  the data field − 1). An optional secondary header follows. (Field table: ICD §2.1.)
- **PUS** (ECSS-E-ST-70-41): TM/TC packets carry a PUS secondary header with a
  service type + message subtype. Services used: **3** (housekeeping), **5**
  (event reporting), **1** (request verification), **9** (time management).
  **Exact field widths / subtypes are NOT invented here** — they are finalized in
  the MDB phase against the standard. (ICD §2.2.)
- **Yamcs** (open-source Java MCS, from the official quickstart): receives CCSDS
  packets over UDP via `org.yamcs.tctm.UdpTmDataLink` (**1 datagram = 1 packet**);
  MDB is XTCE XML; a packet preprocessor sets packet time + sequence count;
  commands go out via a UDP TC link; web UI on the configured HTTP port
  (quickstart default **8090**). (ICD §2.4.)

> **Do NOT invent** packet byte-layouts, PUS subtypes, APIDs, or XTCE specifics in
> this spec. They are defined and frozen *in their phase* (Phase 1 freezes the
> packet/APID layout; Phase 2 freezes the XTCE parameter/calibration/limit set;
> Phase 3 freezes the command set + verification stages) — and recorded in the
> ICD when frozen.

### Requirements covered (full text: SRD "Epic 2 — Control (FOS) requirements")

`REQ-SIM-01..04` (simulator) and `REQ-TMC-01..05` (MDB / decommutation / limits /
telecommanding / operator surfacing).

---

## 1. Phasing — riskiest assumption first

The plan is ordered so the **single riskiest assumption** — "a Python-emitted
CCSDS+PUS packet over UDP is correctly ingested and decommutated by Yamcs against
an XTCE MDB, end-to-end, on this machine" — is proven in **Phase 0** before any
breadth is built. Everything after Phase 0 is incremental fill-in against frozen
contracts.

### Phase 0 — Skeleton + CCSDS → Yamcs → decommutation spike (RISKIEST ASSUMPTION)

**Why first.** This proves the whole toolchain in one thin slice: the Yamcs
quickstart builds/runs via `mvnw` behind the Avast/Maven CA hurdle; a Python
process can frame a valid CCSDS Space Packet with a PUS-3 secondary header and put
it on UDP; Yamcs ingests it (`UdpTmDataLink`), decommutates it against a minimal
XTCE MDB, applies a raw→engineering calibrator, and shows the **calibrated**
value in the web UI. If this slice works, the epic is de-risked; if it doesn't,
we learn it on day one, not at Phase 2.

**Deliverables**
- `control/` directory structure: `control/yamcs/` (quickstart) and
  `control/simulator/` (Python).
- Yamcs quickstart wired and **building + running via `mvnw`** (the main session
  wires the Java truststore from the Windows CA bundle so Maven downloads work
  behind Avast).
- A **minimal XTCE MDB**: 1–2 HK parameters with a raw→engineering **calibrator**
  (e.g. one linear/polynomial calibrated parameter).
- A **minimal Python simulator** emitting **one** CCSDS + PUS service-3 HK packet
  over UDP into the Yamcs `UdpTmDataLink`.
- The decommutated **engineering value visible in the Yamcs web UI**, labelled
  **simulated**.

**CONTRACT frozen at end of phase:** the *toolchain contract* — `control/`
layout; Yamcs runs via `mvnw`; UDP TM ingest path (`UdpTmDataLink`, 1 datagram =
1 packet); XTCE is the MDB format. (Packet field-map is NOT yet frozen — it is
deliberately minimal here and is frozen in Phase 1.)

**Acceptance**
- `mvnw` builds and starts Yamcs (truststore in place).
- The simulator sends one packet; Yamcs ingests it without parse errors.
- The decommutated parameter shows the **correct calibrated engineering value**
  in the web UI (verify the calibration: known raw count → expected eng value).
- The value is labelled simulated.

---

### Phase 1 — Simulator (REQ-SIM-01, REQ-SIM-02, REQ-SIM-04)

**Deliverables**
- Periodic **HK (service 3)** telemetry stream over UDP with a realistic
  raw-count parameter set (the proposed default set is in §4 ESCALATED — battery
  voltage/current, OBC temp, battery temp, reaction-wheel speed, spacecraft mode).
  Parameters are emitted as **raw counts** (calibration lives in the MDB, Phase 2).
- **Realistic dynamics**: drift / noise on continuous params; mode-dependent
  behaviour; **configurable anomaly injection** (scenarios + on/off + magnitude in
  simulator config).
- **PUS event reports (service 5)** on state changes / threshold crossings
  (e.g. a param crossing a configured threshold, a mode transition).
- All emitted telemetry labelled **simulated** (e.g. a fixed simulated-source
  APID / naming convention, recorded in the ICD).

**CONTRACT frozen at end of phase (the decode contract):**
- The **packet / APID layout**: CCSDS primary header usage + the PUS secondary
  header (service/subtype placement per ECSS-E-ST-70-41) + the **HK data-field
  field-map** (parameter order, widths, raw-count encodings) for the chosen APID(s).
- This is the exact bit/byte contract the MDB decodes against. It is recorded in
  the ICD §2 (filling the "to-be-finalized in the MDB phase" markers) **once
  chosen against the standard** — still not invented in *this* spec.

**Acceptance**
- Yamcs ingests the periodic stream with no parse errors; sequence counts advance.
- Toggling an anomaly scenario in config visibly changes the raw values and emits
  the corresponding service-5 event.
- Field-map documented and stable (downstream MDB work can rely on it).

---

### Phase 2 — MDB + decommutation + limits (REQ-TMC-01, REQ-TMC-02, REQ-TMC-03)

**Deliverables**
- **Full XTCE MDB**: all HK parameters defined with **position + type**,
  **raw→engineering calibration curves** (linear / polynomial / enum as
  appropriate), and **soft + hard limits**.
- Yamcs **decommutates** the Phase 1 stream to engineering units per the MDB
  (REQ-TMC-02).
- **Limit checking**: parameters outside soft/hard limits raise **OOL alarms**
  (REQ-TMC-03); injected anomalies (Phase 1) trip them.

**CONTRACT frozen at end of phase:** the **parameter set + calibration curves +
limit definitions** (soft/hard) — the MDB's TM half. Recorded in the ICD §2.3
(XTCE MDB summary) and the Phase 4 MIB summary doc.

**Acceptance**
- Every HK parameter shows a correct **engineering value** in the web UI
  (raw→eng calibration verified for at least one continuous + one enum param).
- Driving a parameter past its soft and hard limits raises the corresponding OOL
  alarms in Yamcs; a nominal stream raises none.

---

### Phase 3 — Telecommanding (REQ-SIM-03, REQ-TMC-04, REQ-TMC-05)

**Deliverables**
- A **telecommand set** defined in the XTCE MDB (REQ-TMC-01's TC half).
- **Build / validate / send** a TC against the MDB via Yamcs, out over the UDP TC
  link (REQ-TMC-04).
- The simulator **accepts** telecommands and returns **PUS service-1 command
  verification** ACKs (REQ-SIM-03); Yamcs tracks the **verification chain**
  (acceptance / execution stages — exact stages chosen against ECSS-E-ST-70-41,
  not invented here).
- **Spacecraft health state + OOL alarms are queryable and surfaced** to the
  operator (Yamcs web UI is acceptable) (REQ-TMC-05).

**CONTRACT frozen at end of phase:** the **command set + verification stages**
(which service-1 subtypes / stages are used) — the MDB's TC half. Recorded in the
ICD §2 and the MIB summary doc.

**Acceptance**
- Sending a defined TC from Yamcs produces simulator service-1 ACK(s) and Yamcs
  shows the verification chain progressing.
- A TC that violates the MDB (out-of-range argument / unknown command) is rejected
  at validation, not silently sent.
- Health state + active OOL alarms are visible/queryable in the web UI.

---

### Phase 4 — Time concept seed + containerisation + docs + close

> Full time **unification** across segments is **Epic 3** (shared layers). Phase 4
> only seeds the FOS-local time concept.

**Deliverables**
- A **PUS service-9 time-correlation concept seed**: document how packet time is
  carried/correlated (CCSDS time format + the Yamcs preprocessor that sets packet
  time), as a seed for the Epic 3 shared time-service. No full cross-segment
  unification here.
- **docker-compose** the FOS stack: `yamcs` + `simulator` + a `postgres`
  placeholder (Phase 0–3 ran Yamcs natively; this is the containerised path).
- A **MIB summary doc** (parameters / calibrators / limits / commands) and the
  **control section of the operations guide** (how to run the FOS, send a TC, read
  alarms — all labelled simulated).
- **Delete this spec (`docs/specs/control.md`) in the last commit.**
- Update `docs/HANDOFF.md` to the new state (main session owns HANDOFF).

**CONTRACT frozen at end of phase:** the time-correlation seed (handed to Epic 3);
the containerised run contract (compose service names / ports).

**Acceptance**
- `docker compose up` brings up yamcs + simulator (+ postgres placeholder) and the
  end-to-end loop works in containers, equivalent to the native loop.
- MIB summary + operations-guide control section exist and are accurate.
- This spec is deleted in the closing commit; HANDOFF reflects Epic 2 closed.

---

## 2. Requirement → phase traceability

| Requirement | Phase(s) |
|---|---|
| REQ-SIM-01 (periodic HK service-3 stream) | 0 (one packet) → 1 (full stream) |
| REQ-SIM-02 (service-5 event reports) | 1 |
| REQ-SIM-03 (accept TC, service-1 ACKs) | 3 |
| REQ-SIM-04 (realistic dynamics + configurable anomalies) | 1 |
| REQ-TMC-01 (XTCE MDB: params, calibration, limits, TC set) | 2 (TM) + 3 (TC) |
| REQ-TMC-02 (Yamcs UDP ingest + decommutation to eng units) | 0 (spike) → 2 (full) |
| REQ-TMC-03 (limit checking → OOL alarms) | 2 |
| REQ-TMC-04 (build/validate/send TC + track verification) | 3 |
| REQ-TMC-05 (health state + OOL alarms queryable / surfaced) | 3 |
| REQ-INT time-correlation seed (full unification = Epic 3) | 4 |

---

## 3. Parallel-vs-serial guidance (per `CLAUDE.md` §3 tree)

The governing dependency is the **decode contract** (Phase 1's packet/APID
field-map): the simulator *produces* it and the MDB *consumes* it, so until it is
frozen, simulator and MDB work must not run in parallel.

- **Phase 0 — SERIAL, single-owner.** It is the riskiest spike and threads
  through both `control/yamcs/` and `control/simulator/` plus the shared
  toolchain/CA hurdle. One owner (or the main session) drives it end to end. Do
  not split it.
- **Phase 1 → Phase 2 — SERIAL on a real dependency.** Phase 2's MDB decodes
  against Phase 1's frozen field-map (one's output is the other's input → SERIAL
  per the tree). Phase 1 must freeze the contract before Phase 2 starts.
- **Within Phase 1 — mostly serial, single file-owner.** Dynamics, anomaly
  injection, service-5 events, and the HK field-map all live in
  `control/simulator/` and share files → SERIAL (one implementer owns the
  simulator).
- **Phase 2 ↔ Phase 3 — partially parallelisable once contracts are frozen.**
  Phase 2 (TM: params/calibration/limits) and Phase 3's TC-set definition both
  edit the XTCE MDB → those edits are **SERIAL** (shared file). But Phase 3's
  **simulator-side TC handling + service-1 ACKs** live in `control/simulator/`
  and don't share files with the MDB's TM section → can proceed in **PARALLEL**
  with Phase 2 *once the command set is defined* (define-first, then parallel).
  Recommended for simplicity at this scale: keep 2 → 3 serial unless throughput
  demands otherwise.
- **Phase 4 — docs + compose are largely independent of each other.** The MIB
  summary, operations-guide section, and docker-compose touch different files →
  **PARALLEL**. The spec-deletion + HANDOFF update is the closing serial step.

> Implementer domains for this epic: a `control-developer` (Java/Yamcs +
> simulator, `control/`) is created when the stack is pinned (it now is). At this
> scale a single `control-developer` owning all of `control/` avoids the
> shared-file contention above; split only if a phase is large enough to warrant
> two non-overlapping owners.

---

## 4. ESCALATED — business decisions for the user

These are business / scope calls (per `CLAUDE.md` §4). Each has an agent-proposed
default so technical work can start while they resolve; they block only the
contract-freeze of their phase, not the start of work.

1. **HK parameter set (Phase 1/2 contract).** Proposed default set
   (**proposed-by-agent, tunable**) — raw counts in TM, calibrated in the MDB:
   - `battery_voltage` (continuous)
   - `battery_current` (continuous)
   - `obc_temp` (on-board computer temperature, continuous)
   - `battery_temp` (continuous)
   - `reaction_wheel_speed` (continuous)
   - `spacecraft_mode` (enum: e.g. SAFE / NOMINAL / PAYLOAD — exact enum tunable)

   *Recommendation:* adopt this set for the MVP; it is small, realistic, and
   exercises continuous calibration, an enum, and limit-checking. Confirm or trim.

2. **Anomaly scenarios (Phase 1, REQ-SIM-04).** Proposed default scenarios
   (**proposed-by-agent, tunable**): battery under-voltage drift; OBC
   over-temperature; reaction-wheel over-speed; a mode transition to SAFE. Each
   toggleable in simulator config with a magnitude/rate.

   *Recommendation:* adopt these four; they map 1:1 to limit checks and service-5
   events. Confirm or extend.

3. **Operator surface for the MVP.** Proposed: **keep the Yamcs web UI as the
   operator surface** for the MVP (REQ-TMC-05 explicitly allows it). A custom UI
   would be later scope (and overlaps Epic 4 viz).

   *Recommendation:* Yamcs web UI for MVP. Confirm.

> Note for all of the above: telemetry is **SIMULATED** and is **labelled
> simulated everywhere** (web UI, logs, the MIB summary, the operations guide).
> The exact CCSDS/PUS field widths, subtypes, and APIDs are **finalized against
> CCSDS 133.0-B-2 / ECSS-E-ST-70-41 in their phase** (Phase 1 packet layout,
> Phase 2 calibration/limits, Phase 3 commands) — **not invented** in this spec.
