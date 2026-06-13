# Synthetic SLSTR fixtures — SYNTHETIC, NOT real data

> **These are SYNTHETIC test fixtures, NOT real EO data.** Every netCDF file carries
> a global attribute `synthetic = "true"` and a `title` that says "SYNTHETIC ... NOT
> real data". Each `xfdumanifest.xml` is marked synthetic too. They exist only to
> exercise the offline ingestion + reader code paths without network or credentials,
> per SRD §5 (a simplification/synthetic input is never presented as operational).

Generated deterministically by [`generate.py`](./generate.py) (fixed RNG seed
`20240613`, no wall-clock, no unseeded randomness). Re-running the generator
reproduces identical content. They mirror the **structure and variable naming** of
the real products described in `docs/icd/ICD.md`, at a tiny 30×40 px grid.

## Contents

### `l1_rbt_synthetic/` — `SL_1_RBT` (L1, collection `EO:EUM:DAT:0411`, NTC)

A nadir 1 km TIR scene (the `*_in` grid suffix):

| File | Variable(s) | Notes |
|---|---|---|
| `S7_BT_in.nc` | `S7_BT_in` | ~3.7 µm brightness temperature (K), stored scaled int16 |
| `S8_BT_in.nc` | `S8_BT_in` | ~10.8 µm brightness temperature (K), stored scaled int16 |
| `S9_BT_in.nc` | `S9_BT_in` | ~12 µm brightness temperature (K), stored scaled int16 |
| `geodetic_in.nc` | `latitude_in`, `longitude_in` | geolocation (deg) |
| `flags_in.nc` | `cloud_in`, `confidence_in` | bitmasks (`cloud_in` bit 0 = cloud) |
| `xfdumanifest.xml` | — | minimal synthetic SAFE manifest |

Brightness temperature is stored **scaled** (`scale_factor = 0.01`,
`add_offset = 280.0`, int16) so the reader exercises xarray `mask_and_scale` to
decode back to Kelvin.

### `l2_wst_synthetic/` — `SL_2_WST` (L2, collection `EO:EUM:DAT:0412`, NTC)

A GHRSST L2P single-measurement netCDF:

| File | Variable(s) | Notes |
|---|---|---|
| `L2P.nc` | `sea_surface_temperature` (K), `quality_level` (0–5), `sst_algorithm_type`, `l2p_flags`, `lat`, `lon` | the official SST reference field |
| `xfdumanifest.xml` | — | minimal synthetic SAFE manifest |

## Synthetic relation (consistency for later phases)

Both products are built from a single **hidden "true SST" field** (`sea`,
~287–300 K over a small open-ocean patch, clipped to 270–305 K). This makes the L1
and L2 fixtures mutually consistent so Phase 2/3 can recover SST and validate it.

1. **True SST → L1 brightness temperatures.** A smooth atmospheric/water-vapour
   term `d = S8 − S9 ≥ 0` is chosen per pixel (12 µm is more strongly absorbed than
   10.8 µm). The split-window is then **inverted** to set the BTs so that a simple
   split-window recovers the true SST:

   ```
   S8 = (SST − A0 − A2·d) / A1
   S9 = S8 − d
   ```

   with the **synthetic, fixture-only** coefficients `A0 = 1.0`, `A1 = 1.0`,
   `A2 = 2.0`. (S7 ≈ S8 − 6 K, a plausible nearby band, **not** used by the SST
   retrieval.)

   > These coefficients exist **only to make the fixture self-consistent**. They are
   > **not** the real operational split-window coefficients — that coefficient set is
   > a documented TBD for Phase 2 and must be cited from a public reference
   > (SRD §4 / `docs/specs/payload.md`). Do not treat the fixture coefficients as
   > operational.

2. **Recovery check (what Phase 2 will do).** Applying
   `SST = A0 + A1·S8 + A2·(S8 − S9)` to the L1 fixture recovers the WST SST field
   with **bias ≈ −0.05 K, RMSE ≈ 0.05 K** (the small bias is the deliberate WST
   offset below). This is asserted in the integration tests.

3. **True SST → L2 WST.** `sea_surface_temperature = true_SST + 0.05 K` (a tiny
   constant sensor/algorithm offset). `quality_level = 5` over clear ocean, `2`
   over the few cloudy pixels.

4. **Clouds.** A small fixed cloudy blob (rows 5–7, cols 10–13) plus two scattered
   cloudy pixels — 14 pixels total — are flagged in L1 `flags_in.cloud_in` (bit 0)
   and `l2p_flags` (bit 1), and have degraded L2 `quality_level = 2`.

## Regenerating

From `payload/`:

```
./.venv/Scripts/python.exe fixtures/generate.py
```

The tiny `.nc` files are committed (the repo `.gitignore` ignores `*.nc` everywhere
**except** under `payload/fixtures/**`). Full real scenes are never committed.
