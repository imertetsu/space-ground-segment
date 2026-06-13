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
