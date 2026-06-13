# viz — 3D flow view (Epic 4)

A read-only **CesiumJS** 3D flow view that ties the Mini Space Ground Segment
together on one screen: the **Sentinel-3A** platform orbiting Earth (real TLE,
SGP4), the **payload** products it produces (REAL EUMETSAT data), and the
**control** state of the spacecraft (SIMULATED telemetry/anomalies) — all read
from the shared catalogue via a canned JSON snapshot, with **every item labelled
real / simulated / illustrative**.

This is a static site: no build step, no bundler, no backend. The app loads
CesiumJS and satellite.js from a CDN and fetches two local files only —
`data/sentinel3a.tle` and `data/snapshot.json`.

## Run it

```sh
cd viz/public
python -m http.server 8095
```

Then open <http://localhost:8095/>.

You must serve it over HTTP (the app uses ES modules + `fetch`, which do not work
from a `file://` URL).

## What you should see

- A 3D globe rendered with **no Cesium-ion token** — imagery is the offline
  **Natural Earth II** tile set bundled in the Cesium build (no ion/Bing key, no
  external tile server). (Cesium may log an ion message in the console; that is
  harmless — the globe still renders.)
- The **Sentinel-3A** orbit track (green polyline, ~one ~100-min period), a dashed
  **ground track**, and a labelled current **sub-satellite position**, all computed
  from the REAL TLE (`data/sentinel3a.tle`, NORAD 41335) via SGP4.
- **Illustrative scene footprints** for each payload product (amber ellipses at the
  product's sub-satellite point) — **click a payload product** in the panel to fly
  the camera to its footprint (it is highlighted + its provenance shown).
- A **side panel** listing the shared catalogue (payload products + control
  references) and anomalies, each tagged with its origin and honesty label, plus
  a **legend** explaining the three labels.

> Note: opened in a foreground tab the globe loads on its own (the intro fly-to
> drives Cesium's tile refinement); if it ever shows un-textured, any camera
> drag/zoom forces it to refine.

## Data honesty (SRD §5)

Every element is labelled so a simplification is never shown as operational:

- **REAL** — payload products (EUMETSAT Sentinel-3A SLSTR L1/L2) and the orbit
  (real public TLE + SGP4).
- **SIMULATED** — control telemetry, parameter references, and OOL alarms (Yamcs,
  Epic 2). Control rows always show `control-simulated`.
- **ILLUSTRATIVE** — scene footprint geometry (amber ellipses). The *products* are
  real; the footprint *shapes* are illustrative (we do not reproject the real SLSTR
  scene polygons).

Live control state requires a running Yamcs instance and is out of scope for the
static snapshot — it arrives via the exporter (below) once the control segment is
populated (Phase 1+).

## Regenerate the snapshot

`data/snapshot.json` is a committed, canned export. To refresh it from the **live**
shared catalogue, run the read-only exporter from the shared virtualenv (which has
`sgs_shared` + `psycopg`) with the catalogue DSN set:

```powershell
# from the repo root (Windows PowerShell)
$env:PDGS_PG_DSN = "postgresql://sgs:change-me@localhost:5432/sgs_catalogue"
shared\.venv\Scripts\python.exe viz\tools\export_snapshot.py
```

Options: `--out <path>` (default `viz/public/data/snapshot.json`) and
`--dsn <dsn>` (default `$PDGS_PG_DSN`).

The exporter only calls `.list()` on the catalogue and anomaly store — it never
writes — and the served app never imports a segment; it reads only the JSON the
exporter produces. This keeps `viz/` a true read-only consumer that depends on no
segment.

## Architecture notes

- `viz/` depends on **nothing** in the segments (`payload/`, `control/`). The
  runtime fetches `data/*.tle` and `data/snapshot.json` only.
- Pinned CDN libraries: **CesiumJS 1.119**, **satellite.js 5.x**.
- `tools/export_snapshot.py` is a maintenance tool, not part of the served app; it
  imports `sgs_shared` but the static site does not.
