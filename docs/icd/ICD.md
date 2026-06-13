# Interface Control Document (ICD)

> ECSS-flavoured ICD. The **Payload** section (§1) is real (verified facts). The
> **Control** section (§2, Epic 2) gives the confirmed transport / framing
> interface from the standards and Yamcs. **No packet byte-layouts, PUS subtypes,
> or APIDs are invented here** — exact field widths and subtypes are marked
> *to be finalized in the MDB phase against the standard* (CCSDS 133.0-B-2,
> ECSS-E-ST-70-41) and recorded here as each Epic 2 phase freezes its contract.

---

## 1. Payload interface (PDGS — Epic 1)

### 1.1 Data source

- **Provider:** EUMETSAT Data Store, accessed via `eumdac`.
- **Mission / instrument:** Sentinel-3 SLSTR.
- **Timeliness:** **NTC** (Non-Time-Critical) for all collections below.

### 1.2 Collections / product types (verified — do not change)

| Role | Collection ID | String form | Product type | Description |
|---|---|---|---|---|
| L1 input | `EO:EUM:DAT:0411` | `EO:EUM:DAT:SENTINEL-3:SL_1_RBT___NTC` | `SL_1_RBT` | SLSTR Level 1B Radiances and Brightness Temperatures |
| L2 reference | `EO:EUM:DAT:0412` | `EO:EUM:DAT:SENTINEL-3:SL_2_WST___NTC` | `SL_2_WST` | SLSTR Level 2 Sea Surface Temperature (SST), GHRSST L2P, IPF v07.00 |

### 1.3 Product format & internal netCDF structure

Each product is a **SAFE folder** = `xfdumanifest.xml` + a set of netCDF files.
The reader resolves bands/geolocation from the netCDF set within the folder.

**Grid-suffix convention (L1):** `in`/`io` = 1 km TIR grid, nadir/oblique;
`an`/`ao` = 500 m grid stripe A, nadir/oblique; `bn`/`bo` = stripe B.

**L1 `SL_1_RBT` files/variables consumed by the payload reader (nadir, MVP):**

| File | Variable | Quantity | Unit |
|---|---|---|---|
| `S7_BT_in.nc` | `S7_BT_in` | TIR brightness temperature (~3.7 µm) | K |
| `S8_BT_in.nc` | `S8_BT_in` | TIR brightness temperature (~10.8 µm) | K |
| `S9_BT_in.nc` | `S9_BT_in` | TIR brightness temperature (~12 µm) | K |
| `geodetic_in.nc` | `latitude_in`, `longitude_in` | geolocation (1 km grid) | deg |
| `flags_in.nc` | `cloud_in`, `confidence_in` | cloud/quality flags | bitmask |

> `S{1..6}_radiance_a{n,o}.nc` (500 m radiances) exist but are **not** used by the
> nadir split-window SST MVP. BT variables are stored scaled (`scale_factor` /
> `add_offset`); the reader relies on xarray `mask_and_scale` to decode to K.

**L2 `SL_2_WST` variables (GHRSST L2P, single measurement netCDF):**

| Variable | Quantity | Unit |
|---|---|---|
| `sea_surface_temperature` | sea surface temperature | K |
| `quality_level` | per-pixel quality (0–5) | enum |
| `sst_algorithm_type`, `l2p_flags` | algorithm / L2P flags | bitmask |
| `lat`, `lon` | geolocation | deg |

> **Confirmed against a real product (2026-06-13):** a real `SL_2_WST` SAFE
> (`.SEN3`) contains **one GHRSST netCDF** named by convention (e.g.
> `<date>-MAR-L2P_GHRSST-SSTskin-SLSTRA-…-v02.0-fv01.0.nc`), NOT `L2P.nc` — so
> `read_l2_wst` locates it by globbing for the file containing
> `sea_surface_temperature`. Its `sea_surface_temperature`/`quality_level` carry a
> leading singleton `time` dim (squeezed on read); `lat`/`lon` are 2D `(nj, ni)`;
> `quality_level` is 0–5 (5 = best). A real L1 `SL_1_RBT` `.SEN3` carries ~97
> netCDFs (the reader uses S7/S8/S9 `_BT_in`, `geodetic_in`, `flags_in`). Products
> download as a zip → extracted to the `.SEN3` folder. **Still TBD:** the real
> `cloud_in`/`confidence_in`/`l2p_flags` bit semantics. Synthetic test fixtures
> mirror this structure/naming and are **labelled synthetic** (see SRD §4 / §5).

### 1.4 Band → quantity → unit (L1 `SL_1_RBT`)

| Band(s) | Spectral region | Quantity | Unit | View(s) |
|---|---|---|---|---|
| S1–S6 | VIS / NIR / SWIR | TOA radiance | radiance (W·m⁻²·sr⁻¹·µm⁻¹) | nadir + oblique |
| S7–S9 | TIR | TOA brightness temperature | K | nadir + oblique |
| F1–F2 | fire channels | brightness temperature | K | nadir + oblique |

> For the simplified split-window SST (Epic 1), the relevant TIR bands are
> **S8 ≈ 10.8 µm** and **S9 ≈ 12 µm**, **nadir view** (MVP).

### 1.5 Reference product fields (L2 `SL_2_WST`)

| Field | Quantity | Unit | Notes |
|---|---|---|---|
| `sea_surface_temperature` | Sea surface temperature | K | GHRSST L2P main field |
| `quality_level` | Per-pixel quality indicator | (enumerated level) | used to filter reference pixels in validation |

### 1.6 Co-location note (simplification)

The **derived** L2 SST (computed from L1 nadir TIR S8/S9) and the **official**
`SL_2_WST` product are on **different grids**. Matchup therefore requires
gridding via **nearest-neighbour** co-location. This is a documented
**simplification**, not an operational resampling scheme (see SRD §4).

---

## 2. Control interface (FOS — Epic 2)

> The transport / framing interface below is confirmed from the standards and the
> Yamcs quickstart. **Exact bit/byte field-maps, PUS subtypes, and APIDs are NOT
> invented here.** They are finalized against the standards as each Epic 2 phase
> freezes its contract (per `docs/specs/control.md`): Phase 1 freezes the packet /
> APID layout + HK data-field field-map; Phase 2 freezes the XTCE parameter /
> calibration / limit set; Phase 3 freezes the command set + verification stages.
> This section is filled in as those contracts land.

The FOS is a spacecraft **simulator** (Python, `control/simulator/`) emitting
CCSDS Space Packets with a PUS secondary header over **UDP** into **Yamcs**
(Java, `control/yamcs/`), which decommutates them against an **XTCE** MDB.

### 2.1 CCSDS Space Packet — primary header (CCSDS 133.0-B-2)

The **6-octet (48-bit) primary header** is fixed by the standard. An optional
secondary header (here, the PUS secondary header — §2.2) follows, then the packet
data field.

| Field | Width | Notes |
|---|---|---|
| Packet Version Number | 3 bits | CCSDS Space Packet = `000`. |
| Packet Type | 1 bit | `0` = TM (telemetry), `1` = TC (telecommand). |
| Secondary Header Flag | 1 bit | `1` when a secondary header is present (PUS packets set this). |
| Application Process Identifier (APID) | 11 bits | Logical stream id. **Exact APID values to be finalized in the MDB phase — not invented here.** |
| Sequence Flags | 2 bits | Grouping (`11` = unsegmented standalone packet). |
| Packet Sequence Count | 14 bits | Per-APID counter (wraps); Yamcs preprocessor uses it. |
| Packet Data Length | 16 bits | **= (number of octets in the packet data field) − 1.** |

> The first 4 octets are the *packet identification* + *packet sequence control*;
> the last 2 octets are the *packet data length*. The packet data field (secondary
> header + user data) follows the 6-octet primary header.

### 2.2 PUS secondary header & services (ECSS-E-ST-70-41)

PUS TM/TC packets carry a **PUS secondary header** in the packet data field,
containing (among standard fields) a **service type** and a **message subtype**
that identify the service and the specific message. Services used by this FOS:

| PUS service | Use in this FOS | Direction | Subtypes / field widths |
|---|---|---|---|
| Service 3 — Housekeeping | Periodic HK parameter reports (REQ-SIM-01) | TM | **to be finalized in the MDB phase against ECSS-E-ST-70-41 — not invented here** |
| Service 5 — Event reporting | Event reports on state changes / threshold crossings (REQ-SIM-02) | TM | **to be finalized in the MDB phase — not invented here** |
| Service 1 — Request verification | Command-verification ACKs / verification chain (REQ-SIM-03, REQ-TMC-04) | TM | acceptance / execution stages **to be finalized in the MDB phase — not invented here** |
| Service 9 — Time management | Time-correlation concept seed (Epic 2 Phase 4; full unification = Epic 3) | TM | time format / correlation **to be finalized — not invented here** |

> The service numbers above are the conventional PUS service identifiers. **The
> exact PUS secondary-header field widths, the per-service message subtypes, and
> the HK data-field parameter field-map are deliberately NOT specified here** — they
> are chosen against ECSS-E-ST-70-41 and frozen in the relevant Epic 2 phase, then
> recorded in this section (see §2 intro and `docs/specs/control.md`).

### 2.3 Yamcs ingest path & XTCE MDB

| Aspect | Confirmed value |
|---|---|
| MCS | **Yamcs** (open-source, Java 17), from the official Yamcs quickstart. |
| TM ingest link | `org.yamcs.tctm.UdpTmDataLink` over **UDP** — **1 datagram = 1 CCSDS packet**. |
| Packet preprocessor | Sets packet time + sequence count (from the primary header §2.1). |
| Mission database (MDB) | **XTCE** XML — defines parameters (position, type, raw→engineering calibrators), limits, and the telecommand set (REQ-TMC-01). |
| Decommutation | Yamcs decodes each packet against the XTCE MDB to **engineering-unit** parameters (REQ-TMC-02); limit checks raise OOL alarms (REQ-TMC-03). |
| TC link | Commands go out over a **UDP TC link** (REQ-TMC-04). |
| Operator surface | Yamcs **web UI** on the configured HTTP port (quickstart default **8090**); health state + OOL alarms queryable there (REQ-TMC-05). |

> The full XTCE MDB summary (parameter set, calibration curves, limits, command
> set) is produced in Epic 2 Phase 4 (MIB summary doc) and reflected here as the
> Phase 2 / Phase 3 contracts freeze.

### 2.4 Real vs simulated

Per SRD §5: control-side telemetry is **SIMULATED** but **CCSDS / PUS-compliant**
in structure and **labelled "simulated" everywhere** (data, web UI, logs,
reports, docs). The Python simulator (`control/simulator/`) frames the CCSDS +
PUS packets described above and emits them over UDP; nothing here is real
spacecraft data.

### 2.5 FROZEN Phase 1 packet contract (TM)

Frozen 2026-06-13 (Epic 2 Phase 1). The **authoritative byte-level spec** is
`control/simulator/PACKET_FORMAT.md`; the MDB (Phase 2) decodes against it. All
fields big-endian.

| Item | Value |
|---|---|
| APIDs | HK = **100** (`0x064`); EVENT = **101** (`0x065`) |
| Primary header | 6 octets (§2.1); `secondaryHeaderFlag=1`; `seqFlags=0b11`; per-APID seq count |
| PUS-C secondary header | 7 octets; octet0 = `0x20` (pusVersion `2` \| timeRefStatus `0`), then serviceType, messageSubtype, messageTypeCounter (u16), destinationId (u16) |
| HK packet | service **3** / subtype **25**; total **25 octets** (`packetDataLength=18`); data = `structureId(u8=1)` + `battery_voltage(u16)` + `battery_current(u16)` + `obc_temp(i16)` + `battery_temp(i16)` + `reaction_wheel_speed(i16)` + `spacecraft_mode(u8 enum 0=SAFE/1=NOMINAL/2=PAYLOAD)` |
| HK raw→eng | voltage = raw×0.001 V · current = raw×0.001 A · obc_temp/battery_temp = raw×0.01 °C · reaction_wheel_speed = raw×1 RPM |
| EVENT packet | service **5**; subtype 1/2/3/4 = info/low/medium/high; data = `eventId(u16)` + `context(i16)` (eventId catalogue in `PACKET_FORMAT.md`) |

**Documented simplifications:** (1) no PUS **time** field in the secondary header —
Yamcs `MyPacketPreprocessor` uses wallclock; (2) a single fixed HK structure
(`structureId=1`) rather than dynamically-defined service-3 structure reports.

**Phase 1 verified (2026-06-13):** the simulator's HK stream (APID 100, 25-octet
packets) is ingested by the live Yamcs `UdpTmDataLink` (`udp-in dataInCount`
advanced, no `SHORT_PACKET` errors). Decommutation to named engineering
parameters lands in Phase 2 (our XTCE MDB replaces the quickstart's; APID 100 =
our HK).

### 2.6 FROZEN Phase 2 MDB (TM decommutation + limits)

Frozen 2026-06-13. SpaceSystem **`SGS`** (labelled SIMULATED) decodes HK APID 100
(§2.5) to engineering units and limit-checks. Authoritative:
`control/yamcs/src/main/yamcs/mdb/xtce.xml`.

| Parameter | Eng unit | Calibrator (raw→eng) | Warning (soft) | Critical (hard) |
|---|---|---|---|---|
| battery_voltage | V | × 0.001 | 7.2 – 8.4 | 6.8 – 8.6 |
| battery_current | A | × 0.001 | 0.4 – 2.2 | 0.0 – 3.0 |
| obc_temp | °C | × 0.01 | 0 – 50 | −20 – 80 |
| battery_temp | °C | × 0.01 | 0 – 40 | −20 – 60 |
| reaction_wheel_speed | RPM | × 1 | 1000 – 6000 | −8000 – 8000 |
| spacecraft_mode | enum | 0=SAFE / 1=NOMINAL / 2=PAYLOAD | — | — |

Calibrators are XTCE `PolynomialCalibrator`s (Yamcs has no `LinearCalibrator`);
the HK container restricts on `SecHdrFlag=Present` + `APID=100`.

**Verified live (2026-06-13):** a nominal stream decommutates to correct
engineering values (e.g. battery_voltage 7.886 V, obc_temp 20.08 °C, RW 3062 RPM,
mode NOMINAL), all `IN_LIMITS`, 0 alarms; the `obc_overtemp` anomaly drives
obc_temp out of limits → an OOL alarm on `/SGS/obc_temp`. (Follow-up: the
simulator clamps raw to the hard band, so over-temp lands at the warning/critical
boundary as WARNING — let anomalies overshoot for a clean CRITICAL.)

### 2.7 FROZEN Phase 3 telecommand + verification contract

Frozen 2026-06-13. Authoritative: `control/simulator/PACKET_FORMAT.md`. All
big-endian; telecommands are SIMULATED.

- **TC packet:** CCSDS primary — type **1 (TC)**, secHdrFlag 1, APID **200**
  (`0x0C8`); PUS-C TC secondary (5 octets): octet0 `0x29` (pusVersion 2 \|
  ackFlags `1001` = acceptance+completion), serviceType, subtype, sourceId(u16)=0;
  then args. Yamcs `MyCommandPostprocessor` fills the CCSDS seq count + length.
- **Command set** (private PUS service **132**): `SET_MODE` (subtype 1; arg `mode`
  enum 0=SAFE/1=NOMINAL/2=PAYLOAD, range-checked) · `PING` (subtype 2, no args).
- **PUS service-1 verification ACK (TM, APID 102):** service 1, subtype **1**
  accept-success / **7** complete-success / **2** accept-fail / **8** complete-fail;
  data = the verified TC's request id (its first 4 octets = packet id + sequence
  control). Defined as TM containers (`Pus1AcceptanceSuccess`, …) in the MDB.
- **Yamcs verifiers:** each command has Accepted + Complete verifiers (container
  match on the ACK containers, `CheckWindow` ~5 s). **Simplification (documented):**
  these are container-match, **not request-id-correlated** (the TC seq count is
  injected post-build by the postprocessor, so XTCE can't compare it to the ACK's
  request id) — correct for one command in flight; true correlation needs a custom
  verifier (`Verification_RequestId` is exposed for that). 

**Verified live (2026-06-13):** `SET_MODE(SAFE)` via Yamcs → simulator executes →
`spacecraft_mode` becomes SAFE in HK; PUS-1 ACKs (APID 102) received; an
out-of-range `mode` is rejected at validation (HTTP 400, not transmitted).

---

## 3. Shared layers interface (Epic 3)

> Unification layer `shared/` (Python, `sgs_shared`) — `time_service`, `catalogue`,
> `anomaly` + the `sgs-ops` operator surface. Depends on **neither** segment
> (import-linter forbidden contract on `pdgs`/`sgs_sim`). Contracts frozen per phase.

### 3.1 Shared catalogue (PostgreSQL) — FROZEN schema (Phase 1)

- DB: **PostgreSQL** (`postgres` compose service, `epic3` profile; db `sgs_catalogue`).
- `PostgresCatalogue(dsn=None)` (DSN arg or `PDGS_PG_DSN` env) implements the shared
  `Catalogue` ABC. **Full surface (frozen):** `register` / `get` /
  `list(*, origin=None)` / `update_status(entry_id, status)` /
  `set_provenance(entry_id, provenance)`. Schema init is idempotent **and
  forward-compatible** (`CREATE TABLE IF NOT EXISTS` + `ALTER … ADD COLUMN IF NOT
  EXISTS` for the `prov_*` columns). A new connection per call; all backend errors
  wrap in `CatalogueError`.
- **Unified record `CatalogueEntry` (frozen):** `entry_id`, **`origin`**
  (`payload`|`control`), **`simulated`** (bool), `product_type`, `status`,
  `sensing_time` (UTC|None), `ingest_time` (UTC), `reference` (locator),
  `provenance` (envelope), `detail`. `origin` + `simulated` are mandatory on every
  row — unification never erases the real-vs-simulated distinction (SRD §5).
- **Provenance envelope (frozen, one shape both segments):** `source_version`
  (processor version for payload / MDB id for control), `source_refs`
  (tuple — payload input product ids / control source parameter ref(s)),
  `run_time` (UTC|None — payload run / control alarm-trigger time).

**Frozen `catalogue_entries` table:**

| column | type | null | meaning |
|---|---|---|---|
| `entry_id` | TEXT PK | no | row id (payload product id / control locator) |
| `origin` | TEXT (CHECK in `payload`,`control`) | no | source segment |
| `simulated` | BOOLEAN | no | `false`=payload (REAL), `true`=control (SIMULATED) |
| `product_type` | TEXT | no | e.g. `SST_L2_DERIVED`, `TM_ARCHIVE_REF`, `OOL_ALARM_REF` |
| `status` | TEXT | no | lifecycle/state (e.g. `VALIDATED`, `ARCHIVED`, `TRIGGERED`) |
| `sensing_time` | TIMESTAMPTZ | yes | observation/trigger time (UTC) |
| `ingest_time` | TIMESTAMPTZ | no | when written to the shared catalogue (UTC) |
| `reference` | TEXT | no | locator (payload path/id or `yamcs://…`) — never a value copy |
| `prov_source_version` | TEXT | yes | provenance: processor/MDB version |
| `prov_source_refs` | TEXT[] | no (`'{}'`) | provenance: upstream ids/param refs |
| `prov_run_time` | TIMESTAMPTZ | yes | provenance: run/trigger time (UTC) |
| `detail` | TEXT | yes | free-text note |

- **Catalogue migration policy:** NEW payload writes can target Postgres via the
  shared mappers (`catalogue.mappers.entry_from_payload_product`) without rewriting
  the Epic-1 SQLite history; SQLite stays the offline payload-dev catalogue.

### 3.2 Control reference bridge (read-only Yamcs REST)

- **`control_bridge.YamcsControlBridge`** records control telemetry/anomaly
  **references** (never value copies — AC1.3) into the shared catalogue, read-only
  over the Yamcs REST API (stdlib `urllib`; **no `control/` code dependency** —
  same read-only consumer pattern `viz/` will use in Epic 4). Endpoints (instance
  `myproject`):
  - `GET /api/mdb/myproject/parameters?system=/SGS` → one `TM_ARCHIVE_REF` per
    parameter; `reference = yamcs://myproject/parameters/<qualifiedName>`.
  - `GET /api/archive/myproject/alarms` → one `OOL_ALARM_REF` per alarm;
    `reference = yamcs://myproject/alarms/<param>/<seqNum>`, `status ∈
    {TRIGGERED, ACKNOWLEDGED}`, `sensing_time`/`prov_run_time` = alarm `triggerTime`.
  - Yamcs alarm `id` may be split (`namespace`+`name`) or a single fully-qualified
    `name` (real archive alarms) — both normalise to the qualified parameter ref.
- Operator surface: `sgs-ops` CLI behind the dark flag **`SGS_SHARED`** (ships
  dark): `status` (cross-segment listing), `bridge` (poll Yamcs → record refs),
  `seed-demo` (hidden).

**Verified live (2026-06-13):** with Yamcs running, `sgs-ops bridge` recorded 15
control references (14 TM-archive + 1 OOL alarm) from real Yamcs REST, then
`sgs-ops status` listed them together with a payload product (1 payload + 16
control), each labelled (`payload` / `control-simulated`); no telemetry value
stored. 33 shared tests pass (DB + bridge), `lint-imports` keeps `shared ↛ pdgs/sgs_sim`.

### 3.3 Shared anomaly model — FROZEN (Phase 2, REQ-INT-03)

One `Anomaly` record + one state machine cover BOTH payload processing failures
(the `ProductStatus.FAILED` dead-letter) and control OOL alarms (from Yamcs).

- **`Anomaly` (frozen):** `anomaly_id`, **`origin`** (`payload`|`control`),
  **`simulated`**, `source_ref` (catalogue linkage — control = the `yamcs://…` alarm
  locator; payload = the catalogue product id), `kind` (`processing_failure` |
  `ool_alarm`), `severity`, `state`, `opened_at`/`updated_at` (UTC), `detail`.
- **State machine (`AnomalyState`):** `OPEN → ACKNOWLEDGED → REPROCESSING →
  RESOLVED` (RESOLVED terminal); `OPEN`/`ACKNOWLEDGED` may go straight to
  `RESOLVED`; `REPROCESSING` may fall back to `OPEN`. Transitions validated before
  the write.
- **Shared operator actions:** `acknowledge` + `resolve` (both halves);
  `start_reprocess` is **payload-only** — a control anomaly raises
  `UnsupportedActionError` (control has no reprocess; payload `REPROCESSING` maps to
  the existing `pdgs reprocess <id>` capability).
- **`AnomalyStore` ABC / `PostgresAnomalyStore`:** table `anomalies` (idempotent +
  forward-compatible schema, UTC `timestamptz`), `record` / `get` / `list(*,
  origin, state)` / `acknowledge` / `resolve` / `start_reprocess`. Errors wrap in
  `AnomalyError`.
- **Bridges (no segment imports):** `anomaly.mappers.anomaly_from_payload_failure`
  (FAILED product → anomaly) and `anomaly_from_yamcs_alarm` +
  `control_bridge.collect_anomalies` / `record_anomalies` (Yamcs OOL alarm →
  anomaly, read-only). CLI: `sgs-ops anomalies` / `ack <id>` / `resolve <id>`
  (dark-flagged).

**Verified live (2026-06-13):** a payload-failure anomaly and a Yamcs OOL-alarm
anomaly recorded into the shared store and listed together by `sgs-ops anomalies`
(each labelled); `ack` advanced the payload one OPEN→ACKNOWLEDGED; `start_reprocess`
succeeded on the payload anomaly (→REPROCESSING) and was rejected on the control
anomaly. 62 shared tests pass, `lint-imports` KEPT.

### 3.4 Shared time service — FROZEN (Phase 3, REQ-INT-01)

One UTC base both halves stamp/compare against, plus OBT↔UTC correlation.

- **Shared base = UTC** (tz-aware ISO-8601). Payload products already carry UTC;
  control telemetry **references** carry UTC (bridge ingest/trigger times). Every
  catalogue/anomaly row stores `timestamptz` (UTC) — so rows from both halves sort
  and compare on one base.
- **`TimeCorrelation` (frozen):** linear model `utc = utc_at_epoch + rate·(obt −
  obt_epoch)` — `obt_epoch` (s), `utc_at_epoch` (UTC), `rate` (UTC s per OBT s;
  `1.0` ideal, off-1.0 = drift; non-zero).
- **API:** `obt_to_utc(obt, corr=None)`, `utc_to_obt(utc, corr=None)` (default =
  `default_correlation()`); `MISSION_EPOCH_UTC` = `2026-01-01T00:00:00Z`.
- **DOCUMENTED SIMPLIFICATION (PUS-9 seed):** the simulator emits no PUS time field
  and Yamcs stamps wall-clock, so there is no live service-9 report;
  `default_correlation()` returns a **seeded** pair (OBT 0 s ↔ `MISSION_EPOCH_UTC`,
  `rate=1.0`) — a labelled seed, NOT an operational correlation. Callers with a real
  pair pass their own `TimeCorrelation`.

**Verified (2026-06-13):** OBT↔UTC round-trips exactly under the default and custom
(incl. drift `rate≠1.0`) correlations; 70 shared tests pass.
