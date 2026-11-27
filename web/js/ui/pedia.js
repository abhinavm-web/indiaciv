// The Almanac: what every number means and exactly where it comes from.
import { resolveTables } from "../terrain.js";
import { esc } from "../format.js";
import { parseHex, luminance } from "../color.js";
import { icon, glyph } from "./icon.js";

const COVER_ICON = { forest_deciduous: "l-forest", forest_evergreen: "l-forest", forest_mixed: "l-forest", cropland: "l-farmland", pasture: "l-farmland", urban: "l-developed" };
// Glyph colour that reads on a resource medallion (dark on light faces such as nuclear yellow or silver).
const inkOn = (hex) => {
  try { return /^#[0-9a-f]{6}$/i.test(hex || "") && luminance(parseHex(hex)) > 0.4 ? "#1c1710" : "#f8f0d8"; } catch { return "#f8f0d8"; }
};
const CATEGORY = { energy: "Energy", mineral: "Minerals", agri: "Agriculture" };

export function initPedia(data) {
  const modal = document.getElementById("pedia");
  const card = modal.querySelector(".modal-card");
  const nav = document.getElementById("pedia-nav");
  const body = document.getElementById("pedia-body");
  const srcName = (id) => data.sources?.find((s) => s.id === id)?.title || id || "";
  let restoreFocus = null;

  const h2 = (ic, fb, text) => `<h2>${icon(ic, fb, { size: 24 })}<span>${esc(text)}</span></h2>`;

  const pages = {
    "About this map": () => `
      ${h2("pedia", "📖", "About this map")}
      <p>This is the real India, drawn like a 4X strategy game. Nothing is invented: every tile, city and number comes
      from public data, listed under <i>Sources</i>, and anything not yet found in a public source is left blank and
      listed under <i>Pending data</i> rather than estimated. It is a port of Andrej Karpathy's
      <a href="https://karpathy.ai/usaciv/" target="_blank" rel="noopener">usaciv</a> (via the
      <a href="https://github.com/zanganeh/iranciv" target="_blank" rel="noopener">iranciv</a> port's pipeline).</p>
      <h4>How it's built</h4>
      <p>India is projected (Albers equal-area) and cut into ${data.world.grid.cols}×${data.world.grid.rows}
      hexes, each ${data.world.grid.radius * 2} km corner to corner. Borders follow the official boundary of India. Each
      hex belongs to the state and district under most of it; Chandigarh, Puducherry and Lakshadweep are smaller than a
      hex and are given the hex at their centre. Terrain comes from elevation samples inside each hex.</p>
      <p><b>Population</b> is the 2011 census, the latest India has published. Districts have been redrawn since (640
      then, about 790 now), so each 2011 sub-district's counts are added to the district of today it lies in.</p>
      <p><b>Cities</b> are the 2011 census urban agglomerations and towns of 100,000 or more people, placed at the
      GeoNames point of the same name inside their own census sub-district. A city's area on the map is its district
      when it is the district's largest city.</p>
      <h4>Controls</h4>
      <p>Drag or arrow keys / WASD to pan · scroll, +/– or double-click to zoom · click a city or a state to open it ·
      / or ⌘K to search · L to cycle lenses · R to show or hide resources · ? for all shortcuts · Esc to close.</p>
      <p>The address bar always holds a link to what you're looking at (lens, selection and view); use <i>Share</i> to copy it
      or to download a picture.</p>`,
    Yields: () => `
      ${h2("y-production", "⚙️", "Yields")}
      <p>Strategy-game yields mapped onto real measures. <b>Gold is GDP</b>: Gross State Domestic Product at current
      prices for 2022-23 (National Statistical Office, published in the RBI's Handbook of Statistics on Indian States).
      India publishes no comparable district or city GDP, so those stay Pending instead of being split from the state.</p>
      <table>${data.nation.yields.map((y) => `<tr><td class="ic" style="color:${esc(y.color)}">${glyph(y, 26)}</td><td><b style="color:${esc(y.color)}">${esc(y.label)}${y.key === "gold" ? " (GDP)" : ""}</b><br>${esc(y.description)}</td></tr>`).join("")}</table>`,
    States: () => `
      ${h2("terrain", "🗺️", "States")}
      <p>Click any land hex without a city to open its state or union territory. A state's population is the sum of its
      districts at the 2011 census and its GDP its own 2022-23 figure (${data.nation.gdp_vintage ? esc(data.nation.gdp_vintage) : "state accounts"}),
      not the sum of its cities, so rural areas count too.</p>
      <p><b>Ranks</b> ("#3 of 36") compare the states and union territories; 1 is the largest.</p>
      ${data.states ? "" : `<p class="muted">This data build has no states.json, so state panels show names and cities only.</p>`}`,
    "Pending data": () => {
      const pend = data.nation.pending || {};
      const label = { always: "Not published anywhere yet", state_gdp: "State GDP", districts: "Districts without census figures",
        cities: "Cities not placed", state_capitals: "Capitals not marked", sources: "Sources that did not answer",
        city_growth: "City growth 2001–2011", district_growth: "District growth 2001–2011", state_growth: "State growth 2001–2011",
        district_nfhs: "Districts without NFHS-5 figures", district_mpi: "Districts without NITI poverty figures", district_pop_est: "Districts without a population estimate", oil_gas: "Oil & gas blocks not placed", city_jobs: "Cities without Economic Census jobs", district_jobs: "Districts without Economic Census jobs", district_gdp: "Districts without GDP", district_gdp_unmatched: "Published district GDP not matched", boundaries: "Boundaries" };
      const line = (x) => esc(Object.entries(x).filter(([k]) => k !== "why").map(([, v]) => v).join(" · ") + (x.why ? ` — ${x.why}` : ""));
      return `
      ${h2("pedia", "📖", "Pending data")}
      <p>The rule of this map: no number is invented. Where no systematic public source has been found yet, the value is
      left blank ("–") and listed here, so the gaps are as visible as the data.</p>
      <p>A few figures are marked <span class="fact-tag derived">derived</span>: they are not published anywhere, but are
      calculated only from sourced numbers, with the method in the tooltip (today's district population, carried forward
      from the 2011 census and scaled to the official state projection). Figures marked
      <span class="fact-tag projection">projection</span> are the government's own projections, not counts. Derived
      figures are shown beside the data, never mixed into totals or yields. The health and poverty lenses draw the
      surveys on the districts as they were surveyed, so a district created after 2017 takes the colour of the district
      it was part of.</p>
      ${Object.entries(pend).filter(([, v]) => v && v.length).map(([k, v]) => `<h4>${esc(label[k] || k)} (${v.length})</h4>
        <ul>${v.map((x) => `<li>${line(x)}</li>`).join("")}</ul>`).join("")}`;
    },
    Terrain: () => {
      const t = data.w?.tables || resolveTables(data.world.tables);
      const hasCover = Array.isArray(data.world.cover);
      const row = (x) => `<tr><td class="nm">${x.color ? `<span class="swatch" style="background:${esc(x.color)}"></span>` : ""}${
        COVER_ICON[x.key] ? icon(COVER_ICON[x.key], "", { size: 15 }) + " " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.rule || "")}</td></tr>`;
      return `
      ${h2("terrain", "🗺️", "Terrain")}
      <p>Each hex averages the elevation samples (AWS Terrain Tiles: SRTM, GMTED and ETOPO1) inside it. Relief comes from the mean elevation and roughness
      (standard deviation) of those samples; shading comes from elevation differences with neighbouring hexes, lit from the
      north-west.</p>
      <h4>${icon("l-forest", "🌲", { size: 16 })} Land cover</h4>
      ${hasCover
        ? `<p>The base colour of each hex is its dominant land-cover group: the largest group among the land samples inside it.
           Small symbols show the mix: trees scale with the forest share, and fields, reeds, shrubs and grass tufts mark farmland,
           wetland, scrub and grassland.</p>
           <table>${t.cover.filter((x) => x.id > 0).map(row).join("")}</table>`
        : `<p class="muted">This data build has no land-cover layer yet; land is coloured by elevation.</p>`}
      <h4>Relief</h4>
      <table>${t.relief.map(row).join("")}</table>
      <h4>${icon("r-hydro", "💧", { size: 16 })} Water</h4>
      <table>${t.water.filter((x) => x.id > 0).map(row).join("")}</table>
      <h4>Beyond the borders</h4>
      <p class="muted">Neighbouring countries (Pakistan, Afghanistan, China, Nepal, Bhutan, Bangladesh, Myanmar and Sri Lanka) are drawn under a light fog:
      it is shown for context and not mapped in detail.</p>`;
    },
    Lenses: () => `
      ${h2("layers", "▤", "Lenses")}
      <p>Lenses recolour the map by one measure. District values are spread to hexes: each hex is sampled at 7 points, and a
      district covering some of them is assumed to cover that share of the hex. State values colour the whole state.</p>
      <p>The legend shows how many hexes fall at each value. Hover or drag on it to show only that range on the map.</p>
      ${(data.lenses.groups || [{ id: null, name: "" }]).map((g) => {
        const ls = data.lenses.lenses.filter((l) => !g.id || l.group === g.id);
        if (!ls.length) return "";
        return `${g.name ? `<h3 class="grp">${icon(`g-${g.id}`, "", { size: 16 })} ${esc(g.name)}</h3>` : ""}${ls.map((l) => `
          <div class="lens-entry"><div class="le-ic">${glyph(l, 26)}</div><div>
          <h4>${esc(l.name)}</h4><p>${esc(l.description)}<br>
          <i class="le-ramp" style="background:linear-gradient(90deg, ${(l.ramp || []).map(esc).join(",")})"></i>
          <span class="muted">Scale: ${esc(l.scale)}, ${l.domain[0].toLocaleString()}–${l.domain[1].toLocaleString()} ${esc(l.unit)}${
            l.higher_is === "good" ? " · higher is better" : l.higher_is === "bad" ? " · higher is worse" : ""}${l.source ? " · " + esc(srcName(l.source)) : ""}</span></p></div></div>`).join("")}`;
      }).join("")}`,
    Resources: () => {
      const r = data.resources;
      if (!r?.types?.length) return `${h2("resources", "⛏️", "Resources")}<p class="muted">This data build has no resources layer.</p>`;
      const count = new Map();
      for (const it of r.items || []) count.set(it.type, (count.get(it.type) || 0) + 1);
      const cats = [...new Set(r.types.map((t) => t.category || "other"))];
      return `
      ${h2("resources", "⛏️", "Resources")}
      <p>Resources mark power plants, coal and iron ore mines and the larger oil &amp; gas blocks on the tiles where
      they are (other minerals are still pending). What each type
      includes is in its description (nuclear plants are left out of this map). When zoomed out, a hex shows its
      highest-ranked resource; zoom in to see more. Press <b>R</b> to show or hide them.</p>
      ${cats.map((c) => `<h4>${esc(CATEGORY[c] || c)}</h4><table class="res-table">
        <tr><th></th><th>Type</th><th>What counts</th><th>Sites</th></tr>
        ${r.types.filter((t) => (t.category || "other") === c).map((t) => `<tr>
          <td class="ic"><span class="res-ic" style="background:${esc(t.color || "#24384f")};color:${inkOn(t.color)}">${glyph(t, 20)}</span></td>
          <td class="nm"><b>${esc(t.name)}</b>${t.unit ? `<br><span class="muted">value in ${esc(t.unit)}</span>` : ""}</td>
          <td>${esc(t.description || "")}<br><span class="muted">Source: ${esc(srcName(t.source))}</span></td>
          <td class="num">${count.get(t.id) || 0}</td></tr>`).join("")}</table>`).join("")}`;
    },
    Sources: () => `
      ${h2("pedia", "📖", "Sources")}
      ${data.sources.map((s) => `
        <h4>${esc(s.title)}</h4>
        <p>${esc(s.description)}<br>
        <span class="muted">${esc(s.publisher)} · ${esc(s.license)}${s.vintage ? " · " + esc(s.vintage) : ""} ·
        <a href="${esc(s.homepage)}" target="_blank" rel="noopener">homepage</a></span></p>
        <table>${(s.files || []).map((f) => `<tr><td><code>${esc(f.url)}</code></td><td class="muted" style="white-space:nowrap">${esc((f.retrieved || "").slice(0, 10))}<br>${((f.bytes || 0) / 1e6).toFixed(1)} MB</td></tr>`).join("")}</table>`).join("")}`,
  };

  const show = (name) => {
    if (!pages[name]) name = "About this map";
    body.innerHTML = pages[name]();
    body.scrollTop = 0;
    nav.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.page === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
    });
  };
  nav.innerHTML = `<div class="hd">Almanac</div>` + Object.keys(pages).map((p) => `<button data-page="${esc(p)}">${esc(p)}</button>`).join("");
  nav.onclick = (e) => {
    const b = e.target.closest("button[data-page]");
    if (b) show(b.dataset.page);
  };
  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
  };
  modal.onclick = (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  };
  // Keep Tab inside the dialog.
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...card.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  return {
    open(page = "About this map") {
      if (modal.hidden) restoreFocus = document.activeElement;
      show(page);
      modal.hidden = false;
      (nav.querySelector("button.active") || card.querySelector("[data-close]"))?.focus();
    },
    close,
    get isOpen() {
      return !modal.hidden;
    },
  };
}
