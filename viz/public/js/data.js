// data.js — load the canned shared-catalogue snapshot and render the side panel.
//
// READ-ONLY consumer: this fetches data/snapshot.json (a committed export of the
// Epic 3 shared catalogue) and renders two lists — payload products (REAL) and
// control references (SIMULATED) — plus the anomalies list. It imports NO segment
// code; the only input is the JSON file. Honesty labels (SRD §5) are mandatory and
// visible: payload rows are tagged REAL, control rows control-simulated / SIMULATED.

/**
 * Map a catalogue/anomaly row to its operator-facing origin label.
 * Mirrors sgs_shared.*.origin_label(): control+simulated -> "control-simulated".
 * @param {{origin: string, simulated: boolean}} row
 * @returns {string}
 */
export function originLabel(row) {
  if (row.origin === "control" && row.simulated) return "control-simulated";
  if (row.simulated) return `${row.origin}-simulated`;
  return row.origin;
}

/** Honesty tag class for a row: payload -> REAL, simulated -> SIMULATED. */
function honestyTag(row) {
  if (row.simulated) return { cls: "tag-sim", text: "SIMULATED" };
  return { cls: "tag-real", text: "REAL" };
}

/** Escape text for safe insertion as element textContent-equivalent in HTML. */
function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Build one catalogue row's HTML. */
function catalogueRowHtml(entry) {
  const tag = honestyTag(entry);
  const refs = Array.isArray(entry.source_refs) ? entry.source_refs : [];
  const sensing = entry.sensing_time ? esc(entry.sensing_time) : "&mdash;";
  // Payload rows with a sensing time get an illustrative footprint on the globe;
  // mark them selectable and carry the entry id so app.js can wire the click.
  const selectable = entry.origin === "payload" && entry.sensing_time;
  return `
    <div class="row${selectable ? " selectable" : ""}" data-origin="${esc(entry.origin)}" data-entry-id="${esc(entry.entry_id)}">
      <div class="row-top">
        <span class="tag ${tag.cls}">${tag.text}</span>
        <span class="origin">${esc(originLabel(entry))}</span>
        <span class="ptype">${esc(entry.product_type)}</span>
        <span class="status status-${esc(entry.status)}">${esc(entry.status)}</span>
      </div>
      <div class="row-ref" title="${esc(entry.reference)}">${esc(entry.reference)}</div>
      <div class="row-meta">
        <span>sensing: ${sensing}</span>
        <span>src: ${esc(entry.source_version)}</span>
        ${refs.length ? `<span>derives from ${refs.length} ref(s)</span>` : ""}
      </div>
      ${entry.detail ? `<div class="row-detail">${esc(entry.detail)}</div>` : ""}
    </div>`;
}

/** Build one anomaly row's HTML. */
function anomalyRowHtml(anom) {
  const tag = honestyTag(anom);
  return `
    <div class="row" data-origin="${esc(anom.origin)}">
      <div class="row-top">
        <span class="tag ${tag.cls}">${tag.text}</span>
        <span class="origin">${esc(originLabel(anom))}</span>
        <span class="ptype">${esc(anom.kind)}</span>
        <span class="severity sev-${esc(anom.severity)}">${esc(anom.severity)}</span>
        <span class="status status-${esc(anom.state)}">${esc(anom.state)}</span>
      </div>
      <div class="row-ref" title="${esc(anom.source_ref)}">${esc(anom.source_ref)}</div>
      <div class="row-meta">
        <span>opened: ${esc(anom.opened_at)}</span>
      </div>
      ${anom.detail ? `<div class="row-detail">${esc(anom.detail)}</div>` : ""}
    </div>`;
}

/**
 * Fetch the snapshot and render the side panel. Returns the parsed snapshot so the
 * caller (app.js) can reuse the platform block.
 * @returns {Promise<object>} the parsed snapshot JSON
 */
export async function loadSnapshotAndRenderPanel() {
  const platformLine = document.getElementById("platformLine");
  const catList = document.getElementById("catalogueList");
  const anomList = document.getElementById("anomalyList");
  const meta = document.getElementById("snapshotMeta");

  let snapshot;
  try {
    const resp = await fetch("data/snapshot.json", { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    snapshot = await resp.json();
  } catch (err) {
    const msg = `Failed to load snapshot.json: ${err.message}`;
    if (catList) catList.textContent = msg;
    if (anomList) anomList.textContent = "";
    throw err;
  }

  const platform = snapshot.platform || {};
  if (platformLine) {
    platformLine.innerHTML =
      `Platform: <strong>${esc(platform.name)}</strong> ` +
      `(NORAD ${esc(platform.norad_id)}) &mdash; ` +
      `<span class="tag tag-real">REAL</span> TLE / SGP4`;
  }

  const catalogue = Array.isArray(snapshot.catalogue) ? snapshot.catalogue : [];
  if (catList) {
    catList.innerHTML = catalogue.length
      ? catalogue.map(catalogueRowHtml).join("")
      : "<div class=\"empty\">No catalogue entries.</div>";
  }

  const anomalies = Array.isArray(snapshot.anomalies) ? snapshot.anomalies : [];
  if (anomList) {
    anomList.innerHTML = anomalies.length
      ? anomalies.map(anomalyRowHtml).join("")
      : "<div class=\"empty\">No open anomalies.</div>";
  }

  if (meta) {
    const counts = {
      payload: catalogue.filter((e) => e.origin === "payload").length,
      control: catalogue.filter((e) => e.origin === "control").length,
    };
    meta.innerHTML =
      `Snapshot ${esc(snapshot.generated_at)} &mdash; ` +
      `${counts.payload} payload (REAL), ${counts.control} control (SIMULATED), ` +
      `${anomalies.length} anomal${anomalies.length === 1 ? "y" : "ies"}.`;
  }

  return snapshot;
}
