// app.js — boot CesiumJS (token-free) and drive the orbit from the REAL Sentinel-3A
// TLE via satellite.js (SGP4).
//
// READ-ONLY consumer. This module fetches only:
//   - data/sentinel3a.tle  (the REAL public NORAD 41335 TLE)
//   - data/snapshot.json   (canned shared-catalogue export, via data.js)
// It imports NO segment code (no pdgs / sgs_sim / control). The orbit track and the
// current sub-satellite position are computed from the real TLE with SGP4 — nothing
// is fabricated. Control telemetry in the panel is SIMULATED and labelled there.
//
// Globals provided by the CDN <script> tags in index.html:
//   - Cesium     (cesium@1.119)
//   - satellite  (satellite.js@5)

import { loadSnapshotAndRenderPanel } from "./data.js";

// ---- Constants ----
const TLE_URL = "data/sentinel3a.tle";
const ORBIT_PERIOD_MIN = 100.8; // Sentinel-3A ~ 100.8 min (sun-sync, ~814 km).
const ORBIT_SAMPLE_STEP_SEC = 30; // one orbit-track vertex every 30 s.

/**
 * Parse a 2- or 3-line TLE string into { name, line1, line2 }.
 * Accepts an optional name line (the Sentinel-3A file has one).
 * @param {string} text
 */
function parseTle(text) {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  let name = "SATELLITE";
  let line1;
  let line2;
  if (lines.length >= 3 && !lines[0].startsWith("1 ")) {
    name = lines[0];
    line1 = lines[1];
    line2 = lines[2];
  } else {
    line1 = lines[0];
    line2 = lines[1];
  }
  if (!line1 || !line2 || !line1.startsWith("1 ") || !line2.startsWith("2 ")) {
    throw new Error("malformed TLE: expected lines starting with '1 ' and '2 '");
  }
  return { name, line1, line2 };
}

/**
 * Propagate a satrec to a geodetic position at a given Date.
 * @returns {{lon: number, lat: number, altMeters: number} | null} null if SGP4 errored
 */
function geodeticAt(satrec, date) {
  const pv = satellite.propagate(satrec, date);
  if (!pv || !pv.position) return null; // SGP4 decay/error -> no position
  const gmst = satellite.gstime(date);
  const geo = satellite.eciToGeodetic(pv.position, gmst);
  return {
    lon: satellite.degreesLong(geo.longitude),
    lat: satellite.degreesLat(geo.latitude),
    altMeters: geo.height * 1000.0, // satellite.js height is in km
  };
}

/** Build a token-free Cesium Viewer (imagery is added afterwards, fully ready). */
function bootViewer() {
  // No base imagery here: `baseLayer: false` avoids Cesium reaching for an
  // ion-backed default (which needs a token). The offline Natural Earth II layer is
  // added in main() AFTER awaiting its provider — adding a fully-ready provider
  // guarantees the globe selects/loads tiles when the camera is first framed (an
  // async `fromProviderAsync` base layer can become ready *after* the initial
  // setView, leaving the globe un-refined / black until the next camera change).
  const viewer = new Cesium.Viewer("cesiumContainer", {
    baseLayer: false,
    baseLayerPicker: false, // would otherwise reach for ion imagery
    geocoder: false, // ion-backed; off so no token is needed
    homeButton: false,
    sceneModePicker: true,
    navigationHelpButton: false,
    animation: false,
    timeline: false,
    fullscreenButton: false,
    selectionIndicator: true,
    infoBox: true,
    // Continuous rendering (Cesium default): every frame re-evaluates the
    // CallbackProperty sub-satellite position (smooth motion) and progressively loads
    // globe imagery tiles. Preserve the WebGL drawing buffer so the rendered globe
    // survives screenshots/`toDataURL` (without it a captured WebGL canvas reads back
    // black).
    contextOptions: { webgl: { preserveDrawingBuffer: true } },
  });

  // Belt-and-braces: no terrain provider that needs ion; flat ellipsoid is fine.
  viewer.scene.globe.enableLighting = false;
  return viewer;
}

/**
 * Add the orbit track (sampled over ~one period) and the live sub-satellite point.
 * @param {Cesium.Viewer} viewer
 * @param {object} satrec
 * @param {string} label
 */
function drawOrbit(viewer, satrec, label) {
  const now = new Date();

  // ---- Orbit track + ground track: sample SGP4 over one full period ----
  const positions = []; // at orbit altitude
  const groundPositions = []; // sub-satellite path clamped to the surface
  const totalSec = ORBIT_PERIOD_MIN * 60;
  for (let t = 0; t <= totalSec; t += ORBIT_SAMPLE_STEP_SEC) {
    const when = new Date(now.getTime() + t * 1000);
    const g = geodeticAt(satrec, when);
    if (g) {
      positions.push(Cesium.Cartesian3.fromDegrees(g.lon, g.lat, g.altMeters));
      groundPositions.push(Cesium.Cartesian3.fromDegrees(g.lon, g.lat, 0));
    }
  }

  viewer.entities.add({
    name: "Sentinel-3A orbit track (real TLE / SGP4)",
    polyline: {
      positions,
      width: 2,
      material: new Cesium.PolylineGlowMaterialProperty({
        glowPower: 0.18,
        color: Cesium.Color.fromCssColorString("#3ddc84"), // green = REAL
      }),
      arcType: Cesium.ArcType.NONE, // already 3D Cartesian points; don't re-clamp
    },
  });

  viewer.entities.add({
    name: "Sentinel-3A ground track (real TLE / SGP4)",
    polyline: {
      positions: groundPositions,
      width: 1.5,
      material: new Cesium.PolylineDashMaterialProperty({
        color: Cesium.Color.fromCssColorString("#3ddc84").withAlpha(0.55),
      }),
      clampToGround: true,
    },
  });

  // ---- Live sub-satellite position: a CallbackProperty re-propagates each frame ----
  const positionCallback = new Cesium.CallbackProperty(() => {
    const g = geodeticAt(satrec, new Date());
    if (!g) return undefined;
    return Cesium.Cartesian3.fromDegrees(g.lon, g.lat, g.altMeters);
  }, false);

  const satEntity = viewer.entities.add({
    name: `${label} — real TLE / SGP4`,
    position: positionCallback,
    point: {
      pixelSize: 12,
      color: Cesium.Color.fromCssColorString("#3ddc84"),
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 2,
    },
    label: {
      text: `${label}\nreal TLE / SGP4`,
      font: "12px monospace",
      fillColor: Cesium.Color.WHITE,
      showBackground: true,
      backgroundColor: Cesium.Color.fromCssColorString("#0a0e14cc"),
      pixelOffset: new Cesium.Cartesian2(0, -22),
      verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
      style: Cesium.LabelStyle.FILL,
    },
  });

  // A subsatellite ground point (lat/lon at altitude 0) for visual grounding.
  const groundCallback = new Cesium.CallbackProperty(() => {
    const g = geodeticAt(satrec, new Date());
    if (!g) return undefined;
    return Cesium.Cartesian3.fromDegrees(g.lon, g.lat, 0);
  }, false);

  viewer.entities.add({
    name: "Sub-satellite ground point (real TLE / SGP4)",
    position: groundCallback,
    point: {
      pixelSize: 6,
      color: Cesium.Color.fromCssColorString("#3ddc8488"),
      outlineColor: Cesium.Color.fromCssColorString("#3ddc84"),
      outlineWidth: 1,
    },
  });

  // CallbackProperty(false) means non-constant -> with continuous rendering Cesium
  // re-evaluates it every frame, so the sub-satellite point advances smoothly with
  // wall-clock time (no extra timer needed).

  // Frame the globe on first load, centred near the current sub-satellite longitude
  // so the full Earth + the polar orbit ring + the satellite are all visible. We use
  // flyTo to an EXPLICIT destination (not flyTo(entities), whose CallbackProperty
  // bounding sphere is unreliable): the camera genuinely moves each frame, which
  // forces the globe quadtree to refine and load imagery tiles (a static initial
  // setView can otherwise leave the globe un-refined / black until the first camera
  // change).
  const g0 = geodeticAt(satrec, now);
  const centerLon = g0 ? g0.lon : 0;
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(centerLon, 10, 24_000_000),
    duration: 2.5,
  });

  return satEntity;
}

// SLSTR nadir swath is ~1420 km wide; we draw an ILLUSTRATIVE footprint ellipse at
// the product's sub-satellite point (geometry is illustrative — we do not reproject
// real scene polygons — but it is anchored to the REAL product's sensing time/orbit).
const FOOTPRINT_SEMI_MAJOR_M = 710_000;
const FOOTPRINT_SEMI_MINOR_M = 360_000;

/**
 * Draw an illustrative scene footprint for each payload product that has a sensing
 * time, anchored at the SGP4 sub-satellite point for that time.
 * @returns {Map<string, Cesium.Entity>} entry_id -> footprint entity
 */
function addFootprints(viewer, satrec, catalogue) {
  const byEntryId = new Map();
  for (const entry of catalogue) {
    if (entry.origin !== "payload" || !entry.sensing_time) continue;
    const when = new Date(entry.sensing_time);
    if (Number.isNaN(when.getTime())) continue;
    const g = geodeticAt(satrec, when);
    if (!g) continue;
    const ent = viewer.entities.add({
      id: `footprint:${entry.entry_id}`,
      name: `${entry.product_type} scene footprint (ILLUSTRATIVE)`,
      position: Cesium.Cartesian3.fromDegrees(g.lon, g.lat, 0),
      ellipse: {
        semiMajorAxis: FOOTPRINT_SEMI_MAJOR_M,
        semiMinorAxis: FOOTPRINT_SEMI_MINOR_M,
        material: Cesium.Color.fromCssColorString("#e0a73a").withAlpha(0.25),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString("#e0a73a"),
        height: 0,
      },
      description:
        `<b>${entry.product_type}</b> &mdash; ${entry.entry_id}<br/>` +
        `Illustrative footprint (geometry not from the real scene polygon).<br/>` +
        `Product is REAL; sensing ${entry.sensing_time}.`,
    });
    byEntryId.set(entry.entry_id, ent);
  }
  return byEntryId;
}

/** Wire panel payload-row clicks to fly to / select the matching footprint. */
function wirePanelSelection(viewer, footprints) {
  const catList = document.getElementById("catalogueList");
  if (!catList) return;
  catList.addEventListener("click", (event) => {
    const row = event.target.closest(".row[data-entry-id]");
    if (!row) return;
    const id = row.getAttribute("data-entry-id");
    const ent = id ? footprints.get(id) : null;
    catList.querySelectorAll(".row.selected").forEach((r) => r.classList.remove("selected"));
    if (!ent) return;
    row.classList.add("selected");
    viewer.selectedEntity = ent;
    viewer.flyTo(ent, { duration: 1.5 }).catch(() => {});
  });
}

/** Entry point. */
async function main() {
  let viewer;
  try {
    viewer = bootViewer();
    window.viewer = viewer; // exposed for debugging / inspection
  } catch (err) {
    console.error("Failed to boot Cesium viewer:", err);
    return;
  }

  // Add the offline Natural Earth II imagery (bundled in the Cesium build) AFTER
  // awaiting its provider, so it is fully ready before the camera is framed. No
  // Cesium-ion / Bing token and no external tile server — renders even with no
  // network / behind a TLS-intercepting proxy.
  try {
    const provider = await Cesium.TileMapServiceImageryProvider.fromUrl(
      Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII")
    );
    viewer.imageryLayers.addImageryProvider(provider);
  } catch (err) {
    console.error("Failed to load offline base imagery:", err);
  }

  // Render the cross-segment panel from the canned snapshot; keep the parsed
  // snapshot so its payload products can be drawn as footprints below.
  const snapshot = await loadSnapshotAndRenderPanel().catch((err) => {
    console.error("Panel render failed:", err);
    return null;
  });

  // Load + propagate the REAL TLE, draw the orbit, then the illustrative footprints
  // for the snapshot's payload products and wire panel selection to them.
  try {
    const resp = await fetch(TLE_URL, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching ${TLE_URL}`);
    const text = await resp.text();
    const { name, line1, line2 } = parseTle(text);
    const satrec = satellite.twoline2satrec(line1, line2);
    drawOrbit(viewer, satrec, name);
    if (snapshot && Array.isArray(snapshot.catalogue)) {
      const footprints = addFootprints(viewer, satrec, snapshot.catalogue);
      wirePanelSelection(viewer, footprints);
    }
    console.info(`Propagating REAL TLE for ${name} (SGP4 via satellite.js).`);
  } catch (err) {
    console.error("Failed to load/propagate the Sentinel-3A TLE:", err);
  }

  // Kick the globe's tile refinement after layout + imagery settle. Empirically the
  // quadtree can stay un-refined (black globe) after first paint until a viewport
  // recompute; resize() forces it. Run a few times to cover slow imagery/layout, and
  // again whenever the tab becomes visible (browsers throttle rAF/timers in a
  // background tab, so a page opened in the background refines once it is focused).
  const kick = () => {
    viewer.resize();
    viewer.scene.requestRender();
  };
  for (const ms of [400, 1200, 2500]) setTimeout(kick, ms);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) kick();
  });
}

main();
