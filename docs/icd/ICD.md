# Interface Control Document (ICD)

> ECSS-flavoured ICD. The **Payload** section is real (verified facts). The
> **Control** section (Epic 2) is a marked **TBD** placeholder — no packet
> structures or PUS specifics are invented here; they are to be confirmed against
> the official CCSDS / ECSS-PUS / Yamcs documentation.

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

## 2. Control interface (FOS — Epic 2) — **TBD / TO BE CONFIRMED**

> **PLACEHOLDER.** None of the following is defined yet. **Do not invent** packet
> structures, field layouts, APIDs, or PUS service specifics. Each item below is
> **to be confirmed against the official CCSDS, ECSS-E-ST-70-41 (PUS), and Yamcs
> documentation** during Epic 2.

### 2.1 CCSDS Space Packet structure — **TBD**

- Primary header, secondary header, and data field layout: **TBD** (confirm
  against CCSDS 133.0-B Space Packet Protocol).

### 2.2 PUS services (counts confirmed; specifics TBD)

The intended PUS services for the telemetry/telecommand simulation:

| PUS service | Purpose | Status |
|---|---|---|
| Service 3 | Housekeeping (HK) | **TBD** — parameters / structure to be confirmed against ECSS-E-ST-70-41 |
| Service 5 | Event reporting | **TBD** — event definitions to be confirmed |
| Service 1 | Command (request) verification | **TBD** — acceptance/execution stages to be confirmed |
| Service 9 | Time management | **TBD** — time format / correlation to be confirmed |

> Service numbers above are the conventional PUS service identifiers. All field
> definitions, subtypes, and parameter sets remain **TBD**.

### 2.3 XTCE MIB summary — **TBD**

- Mission Information Base (parameters, telecommands, calibrators, alarms)
  expressed in XTCE for Yamcs: **TBD** — to be defined and confirmed against the
  Yamcs / XTCE documentation in Epic 2.

### 2.4 Real vs simulated

Per SRD §5: control-side telemetry is **SIMULATED** but CCSDS/PUS-compliant and
**labelled simulated everywhere**. This ICD section will be filled with the
confirmed structures before Epic 2 implementation.
