# PACKET FORMAT — FROZEN decode contract (FOS / Epic 2, Phases 1 & 3)

> **SIMULATED telemetry & telecommanding.** Every packet described here is
> synthetically generated/consumed by `sgs-sim` (`control/simulator/`). It is
> **CCSDS / PUS-compliant in structure** but is **not** operational spacecraft
> data, and is labelled *simulated* everywhere (CLI banner, logs, docs). Per SRD §5.

This is the **authoritative byte-level decode specification** that the Phase-1
simulator emits and that the Phase-2 **XTCE MDB** decodes against, plus the
**Phase-3 telecommand (TC) + PUS service-1 verification ACK** contract (§§6–7). It
is **frozen**: the MDB and any downstream consumer may rely on it exactly. All
fields are **big-endian / network byte order**.

Standards cited:
- **CCSDS 133.0-B-2** — Space Packet Protocol (primary header, TM and TC).
- **ECSS-E-ST-70-41C** — PUS (Telemetry & Telecommand Packet Utilization Standard;
  PUS-C TM and TC secondary headers, services 3, 5, 1, and private service 132).

---

## 1. CCSDS Space Packet primary header — 6 octets (CCSDS 133.0-B-2 §4.1)

Every packet begins with this fixed 6-octet primary header.

| Word | Bits | Field | Value here |
|---|---|---|---|
| word0 (uint16) | 3 | Packet Version Number | `0b000` |
| | 1 | Packet Type | `0` (TM) |
| | 1 | Secondary Header Flag | `1` (PUS secondary header present) |
| | 11 | APID | `100` (HK) / `101` (EVENT) |
| word1 (uint16) | 2 | Sequence Flags | `0b11` (unsegmented, standalone) |
| | 14 | Packet Sequence Count | per-APID, increments mod 16384 |
| word2 (uint16) | 16 | Packet Data Length | **= (octets in the packet data field) − 1** |

The packet data field (PUS secondary header + user data) follows the primary
header. `Packet Data Length` counts only the data field, minus one.

### APIDs (frozen)

| APID | Hex | Stream |
|---|---|---|
| 100 | 0x064 | Housekeeping (PUS service 3) |
| 101 | 0x065 | Event reports (PUS service 5) |

---

## 2. PUS-C TM secondary header — 7 octets (ECSS-E-ST-70-41C)

Placed at the **start of the packet data field** (immediately after the 6-octet
primary header).

| Octet | Width | Field | Value here |
|---|---|---|---|
| 0 | 4 bits | PUS Version Number | `0b0010` (PUS-C, = 2) |
| 0 | 4 bits | Spacecraft Time Reference Status | `0` |
| 1 | uint8 | Service Type | `3` (HK) / `5` (EVENT) |
| 2 | uint8 | Message Subtype | see below |
| 3–4 | uint16 | Message Type Counter | per-service, increments |
| 5–6 | uint16 | Destination ID | `0` (ground) |

→ Octet 0 is therefore always **`0x20`**.

### DOCUMENTED SIMPLIFICATION — no time field

ECSS-E-ST-70-41C permits an **optional time field** in the TM secondary header.
**This contract omits it.** The Yamcs `UdpTmDataLink` preprocessor
(`MyPacketPreprocessor`) ingests packets using **wallclock** time — it parses only
the 6-byte CCSDS primary header (APID + sequence count) and does **not** read a
secondary-header time. Omitting the time field keeps the frozen contract minimal
and changes nothing in the ingest path. (Full PUS service-9 time correlation is a
later-phase / Epic-3 concern.)

---

## 3. HK packet — APID 100, PUS TM[3,25] "HK parameter report"

- **Service Type** = 3, **Message Subtype** = 25 (housekeeping parameter report).
- **Total packet length = 25 octets.** Packet Data Length = 19 − 1 = **18**.

Layout (offsets are from the **start of the packet**, i.e. including the primary
header):

| Offset | Width | Type | Field | Raw → engineering |
|---|---|---|---|---|
| 0 | 6 | — | CCSDS primary header (§1) | — |
| 6 | 7 | — | PUS-C secondary header (§2) | — |
| 13 | 1 | uint8 | `structureId` = 1 | — |
| 14 | 2 | uint16 | `battery_voltage` | V = raw × 0.001 (nominal ~7000–8400) |
| 16 | 2 | uint16 | `battery_current` | A = raw × 0.001 (nominal ~500–2000) |
| 18 | 2 | int16 | `obc_temp` | °C = raw × 0.01 (nominal ~2000 = 20.0 °C) |
| 20 | 2 | int16 | `battery_temp` | °C = raw × 0.01 (nominal ~1500 = 15.0 °C) |
| 22 | 2 | int16 | `reaction_wheel_speed` | RPM = raw × 1 (nominal ~2000–4000) |
| 24 | 1 | uint8 | `spacecraft_mode` | enum (below) |

Data field after the primary header = 7 + 1 + (2+2+2+2+2+1) = **19 octets**.

### `spacecraft_mode` enum (uint8)

| Value | Mode |
|---|---|
| 0 | SAFE |
| 1 | NOMINAL |
| 2 | PAYLOAD |

### DOCUMENTED SIMPLIFICATION — fixed HK report

A real PUS TM[3,25] references a structure-id whose layout is defined out-of-band
(via service-3 subtype 18/19 definition reports). This contract ships a **single
fixed HK structure** identified by `structureId = 1`; the field-map above is
static and frozen rather than dynamically defined. The MDB decodes this one fixed
layout.

---

## 4. EVENT packet — APID 101, PUS TM[5,x] "event report"

- **Service Type** = 5. **Message Subtype** = severity (below).
- **Total packet length = 17 octets.** Packet Data Length = 11 − 1 = **10**.

| Offset | Width | Type | Field |
|---|---|---|---|
| 0 | 6 | — | CCSDS primary header (§1) |
| 6 | 7 | — | PUS-C secondary header (§2) |
| 13 | 2 | uint16 | `eventId` (catalogue below) |
| 15 | 2 | int16 | `context` (the offending raw value, or 0) |

### Message subtype = severity (ECSS-E-ST-70-41C service 5)

| Subtype | Severity |
|---|---|
| 1 | info |
| 2 | low |
| 3 | medium |
| 4 | high |

### eventId catalogue (frozen)

| eventId | Name | Trigger | Subtype (severity) | `context` |
|---|---|---|---|---|
| 1 | EVT_BATTERY_UNDERVOLTAGE | `battery_voltage` < its soft_min | 3 (medium) | offending raw voltage |
| 2 | EVT_OBC_OVERTEMP | `obc_temp` > its soft_max | 4 (high) | offending raw temp |
| 3 | EVT_RW_OVERSPEED | `reaction_wheel_speed` > its soft_max | 3 (medium) | offending raw speed |
| 4 | EVT_MODE_CHANGE | `spacecraft_mode` changed | 1 (info) | new mode value |
| 5 | EVT_MODE_SAFE | spacecraft entered SAFE mode | 2 (low) | 0 |

Events are **edge-triggered**: each soft-limit crossing emits its event once and
re-arms only when the value returns inside the soft band. A mode change emits
EVT_MODE_CHANGE (and EVT_MODE_SAFE additionally when the new mode is SAFE).

---

## 5. Example — decoded HK packet

Hexdump of one nominal HK packet (seed 42, tick 0, `config/default.toml`):

```
0864 c000 0012  20 03 19 0000 0000  01 1e75 03e3 07cf 05e2 0bb3 01
```

| Bytes | Field | Decode |
|---|---|---|
| `0864` | word0 | ver 0, type 0 (TM), sec-hdr 1, APID 100 |
| `c000` | word1 | seqFlags 0b11, seqCount 0 |
| `0012` | word2 | packetDataLength = 18 (→ data field 19 octets) |
| `20` | PUS octet0 | 0x20 = PUS-C, time-ref-status 0 |
| `03` | service | 3 (HK) |
| `19` | subtype | 25 (HK parameter report) |
| `0000` | msgTypeCounter | 0 |
| `0000` | destinationId | 0 (ground) |
| `01` | structureId | 1 |
| `1e75` | battery_voltage | 7797 → 7.797 V |
| `03e3` | battery_current | 995 → 0.995 A |
| `07cf` | obc_temp | 1999 → 19.99 °C |
| `05e2` | battery_temp | 1506 → 15.06 °C |
| `0bb3` | reaction_wheel_speed | 2995 → 2995 RPM |
| `01` | spacecraft_mode | 1 (NOMINAL) |

Total = 25 octets.

---

## 6. Telecommand (TC) packet — APID 200 (FROZEN Phase 3)

> **SIMULATED telecommanding.** TCs flow **ground → spacecraft**: Yamcs' `udp-out`
> (`UdpTcDataLink`, `localhost:10025`) sends them; the simulator's TC receiver
> binds that port and consumes one TC per UDP datagram. Yamcs'
> `MyCommandPostprocessor` finalizes the CCSDS **sequence count** and **packet data
> length** after the command is built from the XTCE `CommandContainer`.

### 6.1 TC CCSDS primary header — 6 octets

| Word | Bits | Field | Value here |
|---|---|---|---|
| word0 (uint16) | 3 | Packet Version Number | `0b000` |
| | 1 | Packet Type | `1` (**TC**) |
| | 1 | Secondary Header Flag | `1` (PUS secondary header present) |
| | 11 | APID | **200** (`0x0C8`) |
| word1 (uint16) | 2 | Sequence Flags | `0b11` (unsegmented, standalone) |
| | 14 | Packet Sequence Count | filled by the Yamcs postprocessor |
| word2 (uint16) | 16 | Packet Data Length | = (data-field octets) − 1; filled by the postprocessor |

### 6.2 PUS-C TC secondary header — 5 octets (ECSS-E-ST-70-41C)

Placed at the start of the packet data field (after the 6-octet primary header).

| Octet | Width | Field | Value here |
|---|---|---|---|
| 0 | 4 bits | PUS Version Number | `0b0010` (PUS-C, = 2) |
| 0 | 4 bits | Acknowledgement Flags | `0b1001` (acceptance + completion) |
| 1 | uint8 | Service Type | **132** (private command service) |
| 2 | uint8 | Message Subtype | command id (below) |
| 3–4 | uint16 | Source ID | `0` (ground) |

→ Octet 0 is therefore **`0x29`** = `(2 << 4) | 0b1001`.

**Acknowledgement flags** (bit field, ECSS-E-ST-70-41C): bit0 acceptance, bit1
start, bit2 progress, bit3 completion. This FOS requests **acceptance +
completion** (`0b1001`), so each TC yields a TM[1,1] then a TM[1,7] on success.

### 6.3 Command set — private PUS service 132

> **DOCUMENTED CHOICE — private/custom service.** ECSS-E-ST-70-41C reserves
> service types **≥ 128 for mission-private services**. This FOS uses service
> **132** for its (SIMULATED) command set; it is therefore non-standard by design
> and documented as private/custom.

| Command | Service / subtype | Args (after the 5-octet TC secondary header) | Validation |
|---|---|---|---|
| `SET_MODE` | 132 / 1 | `mode` : uint8 enum (0=SAFE, 1=NOMINAL, 2=PAYLOAD) | mode ∈ {0,1,2}; out-of-range rejected at acceptance |
| `PING` | 132 / 2 | none | always valid |

`SET_MODE` total packet length = 6 + 5 + 1 = **12 octets**; `PING` = **11 octets**.

### 6.4 Request id (for verification correlation)

The TC **request id** (per ECSS-E-ST-70-41C service 1) is the TC's **first 4
octets** = CCSDS *packet id* (word0: version/type/secHdrFlag/APID) + *packet
sequence control* (word1: seqFlags/seqCount). The simulator echoes it verbatim in
every verification ACK so the ground (Yamcs) can correlate the verification chain
to the command (by its CCSDS sequence count).

---

## 7. PUS service-1 verification ACK packet — APID 102 (FROZEN Phase 3)

> **SIMULATED.** ACKs flow **spacecraft → ground** over the **same TM link** as HK
> (`127.0.0.1:10015`, Yamcs `UdpTmDataLink`). One ACK per UDP datagram.

- CCSDS TM primary header (§1) with **APID = 102** (`0x066`), `type=0` (TM),
  `secHdrFlag=1`.
- PUS-C **TM** secondary header (§2, 7 octets): **Service Type = 1**, Message
  Subtype = the verification stage (below), messageTypeCounter (per-service),
  destinationId = 0.
- User data = the verified TC's **4-octet request id** (§6.4).

| Offset | Width | Type | Field |
|---|---|---|---|
| 0 | 6 | — | CCSDS TM primary header (APID 102) |
| 6 | 7 | — | PUS-C TM secondary header (service 1) |
| 13 | 4 | bytes | `requestId` (= the verified TC's first 4 octets, §6.4) |

**Total ACK packet length = 17 octets.** Packet Data Length = 11 − 1 = **10**.

### Verification subtypes (ECSS-E-ST-70-41C service 1)

| Subtype | Report | Emitted when |
|---|---|---|
| 1 | acceptance — success (TM[1,1]) | a received TC passes validation |
| 2 | acceptance — failure (TM[1,2]) | a received TC fails validation (unknown service/subtype, out-of-range arg) |
| 7 | completion — success (TM[1,7]) | an accepted TC has been applied |
| 8 | completion — failure (TM[1,8]) | reserved (defined; not currently emitted — both commands always complete) |

**Per-TC sequence (simulator behaviour):**

```
valid TC   ->  TM[1,1] acceptance-success
               apply (SET_MODE changes spacecraft_mode; PING = no-op)
           ->  TM[1,7] completion-success
invalid TC ->  TM[1,2] acceptance-failure         (rejected; nothing applied)
```

`SET_MODE` drives the simulator's `spacecraft_mode`, so subsequent HK packets
(§3) report the commanded mode, and a mode change emits the usual PUS-5
`EVT_MODE_CHANGE` (and `EVT_MODE_SAFE` for SAFE).

> **DOCUMENTED SIMPLIFICATION — request-id payload.** A full ECSS service-1 report
> carries the request id as the structured *packet id + packet sequence control*
> plus (for failures) a failure-code/parameters. This contract ships the **request
> id only** (the 4 raw octets) and signals failure via the **subtype** (2/8); no
> separate failure code is encoded. This is sufficient for Yamcs to correlate the
> chain by the command's CCSDS sequence count.

---

## 8. Summary of constants for the MDB

| Constant | Value |
|---|---|
| UDP TM target (default) | 127.0.0.1:10015 (Yamcs `UdpTmDataLink`; HK, EVENT, ACK) |
| UDP TC target (default) | 127.0.0.1:10025 (Yamcs `UdpTcDataLink`; sim binds to receive) |
| Datagram rule | 1 UDP datagram = 1 CCSDS packet |
| HK APID / packet length | 100 / 25 octets |
| EVENT APID / packet length | 101 / 17 octets |
| TC APID | **200** (`0x0C8`) — ground → spacecraft |
| ACK (verification) APID / packet length | **102** (`0x066`) / 17 octets |
| PUS version | C (0b0010); TM secondary octet0 = 0x20; TC secondary octet0 = 0x29 |
| HK service / subtype | 3 / 25 |
| EVENT service / subtypes | 5 / {1 info, 2 low, 3 medium, 4 high} |
| Command service / subtypes | **132** (private) / {1 SET_MODE, 2 PING} |
| Verification service / subtypes | **1** / {1 accept-ok, 2 accept-fail, 7 complete-ok, 8 complete-fail} |
| TC secondary header | 5 octets; pusVersion 2 \| ackFlags 0b1001; service, subtype, sourceId(u16=0) |
| Request id | TC's first 4 octets (packet id + packet sequence control); echoed in ACKs |
| Sequence count | per-APID, 14-bit, mod 16384 |
| Message type counter | per-service, 16-bit |
| Time field | **none** (Yamcs uses wallclock — see §2) |
