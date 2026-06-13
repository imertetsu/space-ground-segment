# PACKET FORMAT — FROZEN decode contract (FOS / Epic 2, Phase 1)

> **SIMULATED telemetry.** Every packet described here is synthetically generated
> by `sgs-sim` (`control/simulator/`). It is **CCSDS / PUS-compliant in structure**
> but is **not** operational spacecraft data, and is labelled *simulated*
> everywhere (CLI banner, logs, docs). Per SRD §5.

This is the **authoritative byte-level decode specification** that the Phase-1
simulator emits and that the Phase-2 **XTCE MDB** decodes against. It is **frozen**:
the MDB and any downstream consumer may rely on it exactly. All fields are
**big-endian / network byte order**.

Standards cited:
- **CCSDS 133.0-B-2** — Space Packet Protocol (primary header).
- **ECSS-E-ST-70-41C** — PUS (Telemetry & Telecommand Packet Utilization Standard;
  PUS-C secondary header, services 3 and 5).

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

## 6. Summary of constants for the MDB

| Constant | Value |
|---|---|
| UDP target (default) | 127.0.0.1:10015 (Yamcs `UdpTmDataLink`) |
| Datagram rule | 1 UDP datagram = 1 CCSDS packet |
| HK APID / packet length | 100 / 25 octets |
| EVENT APID / packet length | 101 / 17 octets |
| PUS version | C (0b0010); secondary-header octet0 = 0x20 |
| HK service / subtype | 3 / 25 |
| EVENT service / subtypes | 5 / {1 info, 2 low, 3 medium, 4 high} |
| Sequence count | per-APID, 14-bit, mod 16384 |
| Message type counter | per-service, 16-bit |
| Time field | **none** (Yamcs uses wallclock — see §2) |
