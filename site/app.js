// IP & Media Brief front end (SPEC 14). No framework, no third-party requests.
const $ = (s) => document.querySelector(s);
const TZ = "Europe/London";
const KEY = "brief.v1.";
const DAY_MS = 86400000;

function get(k, d) { try { const v = localStorage.getItem(KEY + k); return v === null ? d : JSON.parse(v); } catch { return d; } }
function set(k, v) { try { localStorage.setItem(KEY + k, JSON.stringify(v)); } catch { /* storage blocked */ } }
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");

const fmtTime = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const fmtDay = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
const fmtShort = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short" });
const fmtIsoDay = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const londonDay = (d) => fmtIsoDay.format(d);

const S = {
  meta: null, items: new Map(), loadedDays: [], dayQueue: [], loading: false,
  desk: get("desk", null), topics: get("topics", { ip: [], media: [], both: [] }),
  picksOnly: get("picksOnly", false), sort: get("sort", "newest"), q: "",
  saved: get("saved", {}), read: get("read", {}), prevVisit: null, view: "today", olderRows: null,
};

// ---- visits (SPEC 14.8): prevVisit moves forward when 30 minutes have passed
(function visits() {
  const now = Date.now();
  const last = get("lastVisit", null);
  let prev = get("prevVisit", null);
  if (last && now - Date.parse(last) > 30 * 60000) { prev = last; set("prevVisit", prev); }
  set("lastVisit", new Date(now).toISOString());
  S.prevVisit = prev ? Date.parse(prev) : null;
})();

// ---- theme
function applyTheme() {
  const t = get("theme", "system");
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
}
applyTheme();

async function fetchJSON(path) {
  let r;
  try {
    r = await fetch(path, { cache: "no-cache" });
  } catch (e) { // network failure: fall back to the copy the service worker kept
    $("#offline").classList.remove("hidden");
    const c = typeof caches !== "undefined" ? await caches.match(path) : null;
    if (c) return c.json();
    throw e;
  }
  if (!r.ok) throw new Error(`HTTP ${r.status} for ${path}`);
  return r.json();
}

const dispTime = (it) => Date.parse(it.published_at || it.first_seen_at);
const isNew = (it) => {
  // First visit: everything published today counts, including the first big scan.
  if (!S.prevVisit) return londonDay(new Date(dispTime(it))) === londonDay(new Date());
  const seen = Date.parse(it.first_seen_at);
  const bf = S.meta?.backfill_until ? Date.parse(S.meta.backfill_until) : 0;
  return seen > bf && seen > S.prevVisit;
};
const onDesk = (it, d) => d === "both" || it.desk === d || (it.also_desks || []).includes(d);

function visible(it) {
  if (!onDesk(it, S.desk)) return false;
  if (S.picksOnly && !it.pick) return false;
  const active = S.topics[S.desk] || [];
  if (active.length && !(it.topics || []).some((t) => active.includes(t))) return false;
  if (S.q) {
    const hay = `${it.title} ${it.abstract} ${it.summary || ""} ${it.source_name} ${it.publisher || ""}`.toLowerCase();
    if (!S.q.split(/\s+/).every((w) => hay.includes(w))) return false;
  }
  return true;
}

function topicLabel(id) {
  for (const d of Object.values(S.meta.desks)) if (d.topics[id]) return d.topics[id];
  return id;
}

function renderChips() {
  const desks = S.desk === "both" ? ["ip", "media"] : [S.desk];
  const active = S.topics[S.desk] || [];
  $("#chips").innerHTML = desks.flatMap((d) => Object.entries(S.meta.desks[d].topics))
    .map(([id, label]) => `<button class="chip" data-topic="${esc(id)}" aria-pressed="${active.includes(id)}">${esc(label)}</button>`).join("");
}

function card(it) {
  const t = new Date(dispTime(it));
  const time = londonDay(t) === londonDay(new Date()) ? fmtTime.format(t) : fmtShort.format(t);
  const src = it.publisher || it.source_name;
  const also = it.also || [];
  const badges = [
    it.pick ? '<span class="badge b-pick">Pick</span>' : "",
    it.revision > 1 ? '<span class="badge b-upd">Updated</span>' : "",
    it.paywalled ? '<span class="badge b-pay">Paywall</span>' : "",
    also.length ? `<span class="badge b-more">+${also.length} source${also.length > 1 ? "s" : ""}</span>` : "",
  ].join("");
  const saved = !!S.saved[it.id];
  const abs = it.abstract ? `<p class="abs">${esc(it.abstract)}</p>` : '<p class="abs">Headline only.</p>';
  const sum = it.summary ? `<button class="sumbtn" aria-expanded="false"><span class="chev">›</span>Summary</button>
    <div class="summary">${esc(it.summary)}<small>${esc(S.meta.summary_label)}${it.summary_model ? ` <span class="model">(${esc(it.summary_model)})</span>` : ""}</small></div>` : "";
  const tags = (it.topics || []).map((t) => `<button class="tag" data-topic="${esc(t)}">${esc(topicLabel(t))}</button>`).join("")
    + (it.jurisdictions || []).map((j) => `<span class="tag j">${esc(j)}</span>`).join("");
  return `<article class="card ${it.desk}${S.read[it.id] ? " read" : ""}" data-id="${esc(it.id)}" tabindex="-1">
    <div class="meta"><span class="src">${esc(src)}</span>${it.via ? '<span class="via">via Google News</span>' : ""}<span>· ${time}</span>${badges}</div>
    <h4><a href="${esc(safeUrl(it.url))}" target="_blank" rel="noopener noreferrer" data-open="${esc(it.id)}">${esc(it.title)}</a></h4>
    ${abs}${sum}
    <div class="foot">${tags}<span class="spacer"></span>
      <button class="act save" aria-pressed="${saved}" aria-label="${saved ? "Remove from saved" : "Save"}">${saved ? "★ Saved" : "☆ Save"}</button>
      <button class="act copy">Copy link</button></div>
    ${also.length ? `<div class="also">Also: ${also.map((a) => `<a href="${esc(safeUrl(a.url))}" target="_blank" rel="noopener noreferrer">${esc(a.source_name)}</a>`).join(", ")}</div>` : ""}
  </article>`;
}

function dayHeading(day) {
  const today = londonDay(new Date());
  const yest = londonDay(new Date(Date.now() - DAY_MS));
  if (day === today) return "Today";
  if (day === yest) return "Yesterday";
  return fmtDay.format(new Date(`${day}T12:00:00Z`)).replace(",", "");
}

function renderBrief() {
  const all = [...S.items.values()];
  const fresh = all.filter(isNew);
  const desks = S.desk === "both" ? ["ip", "media"] : [S.desk];
  const n = (d) => fresh.filter((it) => onDesk(it, d)).length;
  const picks = fresh.filter((it) => it.pick && desks.some((d) => onDesk(it, d))).length;
  const lead = S.prevVisit ? "Since your last visit" : "Today";
  $("#since").innerHTML = `${lead}: <b>${n("ip")} IP</b> · <b>${n("media")} Media</b> · <b>${picks} picks</b>`;
  const cutoff = Date.now() - 2 * DAY_MS;
  const top = [];
  for (const d of desks) {
    top.push(...all.filter((it) => it.desk === d && it.pick && dispTime(it) >= cutoff)
      .sort((a, b) => b.score - a.score || dispTime(b) - dispTime(a)).slice(0, 5));
  }
  $("#picks").innerHTML = top.length ? top.map((it) => `<li><span class="k ${it.desk}">${it.desk === "ip" ? "IP" : "MEDIA"}</span><a href="${esc(safeUrl(it.url))}" target="_blank" rel="noopener noreferrer" data-open="${esc(it.id)}">${esc(it.title)}</a></li>`).join("")
    : '<li class="note">No picks in the last 48 hours.</li>';
}

function renderFeed() {
  const rows = [...S.items.values()].filter(visible);
  if (!rows.length) {
    $("#feed").innerHTML = S.loading ? '<p class="loading">Loading</p>'
      : '<p class="empty">Nothing matches these filters. <button class="pill" id="clear">Clear filters</button></p>';
    return;
  }
  const byDay = new Map();
  for (const it of rows) {
    const d = londonDay(new Date(dispTime(it)));
    if (!byDay.has(d)) byDay.set(d, []);
    byDay.get(d).push(it);
  }
  let html = "";
  let sawNew = false, markedSeen = false;
  for (const d of [...byDay.keys()].sort().reverse()) {
    const list = byDay.get(d);
    list.sort(S.sort === "relevant" ? (a, b) => b.score - a.score || dispTime(b) - dispTime(a) : (a, b) => dispTime(b) - dispTime(a));
    html += `<h3 class="day">${esc(dayHeading(d))}</h3>`;
    for (const it of list) {
      if (S.sort === "newest") {
        const fresh = isNew(it);
        if (fresh && !sawNew) { html += '<div class="divider">New since your last visit</div>'; sawNew = true; }
        if (!fresh && sawNew && !markedSeen) { html += '<div class="divider">Seen before</div>'; markedSeen = true; }
      }
      html += card(it);
    }
  }
  $("#feed").innerHTML = html;
}

function renderControls() {
  document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.desk === S.desk)));
  $("#picksOnly").setAttribute("aria-pressed", String(S.picksOnly));
  $("#sort").textContent = S.sort === "relevant" ? "Most relevant" : "Newest";
  $("#sort").setAttribute("aria-pressed", String(S.sort === "relevant"));
  $("#savedCount").textContent = `(${Object.keys(S.saved).length})`;
  renderChips();
}

function renderOlder() {
  const box = $("#older");
  if (!S.q) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  if (!S.olderRows) { box.innerHTML = '<button class="pill" id="searchOlder">Search older months</button>'; return; }
  const words = S.q.split(/\s+/);
  const hits = S.olderRows.filter((r) => !S.items.has(r[0]) && words.every((w) => `${r[3]} ${r[4]}`.toLowerCase().includes(w))
    && (S.desk === "both" || r[2] === S.desk)).slice(0, 100);
  box.innerHTML = `<h3 class="day">Older months: ${hits.length}${hits.length === 100 ? "+" : ""} matches</h3><ul class="results">`
    + hits.map((r) => `<li><div class="r-meta">${esc(r[4])} · ${esc(fmtShort.format(new Date(r[1] + "T12:00:00Z")))}${r[7] ? " · Pick" : ""}</div><a href="${esc(safeUrl(r[5]))}" target="_blank" rel="noopener noreferrer">${esc(r[3])}</a></li>`).join("")
    + "</ul>";
}

function render() {
  renderControls();
  renderBrief();
  renderFeed();
  renderOlder();
}

async function loadNextDay() {
  if (S.loading || !S.dayQueue.length) return;
  S.loading = true;
  const d = S.dayQueue.shift();
  try {
    const rows = await fetchJSON(`data/days/${d}.json`);
    for (const it of rows) S.items.set(it.id, it);
    S.loadedDays.push(d);
  } catch { /* a missing day file leaves a gap */ }
  S.loading = false;
}

async function loadMore(n) { for (let i = 0; i < n; i++) await loadNextDay(); render(); }

// ---- saved and sources views
function renderSaved() {
  const list = Object.values(S.saved).sort((a, b) => (b._savedAt || 0) - (a._savedAt || 0));
  $("#savedList").innerHTML = list.length ? list.map(card).join("") : '<p class="empty">No saved items yet. Tap ☆ Save on any story.</p>';
}

function renderSources() {
  const m = S.meta;
  const h = m.health;
  $("#healthLine").textContent = `Health ${h.status}: ${h.ok} sources OK, ${h.failing} failing, ${h.empty} empty. Built ${fmtDay.format(new Date(m.generated_at))} ${fmtTime.format(new Date(m.generated_at))}, version ${m.version}.`;
  const rows = [...m.sources].sort((a, b) => a.desk.localeCompare(b.desk) || a.priority - b.priority || a.name.localeCompare(b.name));
  $("#sourcesTable").innerHTML = `<table class="src"><thead><tr><th>Source</th><th>Desk</th><th class="hide-sm">Priority</th><th>New 7d</th><th class="hide-sm">Last OK</th></tr></thead><tbody>`
    + rows.map((s) => `<tr><td><span class="st ${esc(s.status)}" title="${esc(s.status)}"></span>${s.homepage ? `<a href="${esc(safeUrl(s.homepage))}" target="_blank" rel="noopener noreferrer">${esc(s.name)}</a>` : esc(s.name)}</td><td>${s.desk === "ip" ? "IP" : "Media"}</td><td class="hide-sm">${s.priority}</td><td>${s.new_7d}</td><td class="hide-sm">${s.last_ok_at ? esc(fmtShort.format(new Date(s.last_ok_at))) : "never"}</td></tr>`).join("")
    + "</tbody></table>";
}

function showView(v) {
  S.view = v;
  for (const id of ["today", "saved", "sources"]) $(`#v-${id}`).classList.toggle("hidden", id !== v);
  document.querySelectorAll("nav.views button").forEach((b) => (b.dataset.view === v ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
  if (v === "saved") renderSaved();
  if (v === "sources") renderSources();
  if (location.hash !== (v === "today" ? "" : `#${v}`)) history.replaceState(null, "", v === "today" ? location.pathname : `#${v}`);
}

function findItem(id) { return S.items.get(id) || S.saved[id]; }

function markRead(id) {
  S.read[id] = Date.now();
  const ids = Object.keys(S.read);
  if (ids.length > 5000) ids.sort((a, b) => S.read[a] - S.read[b]).slice(0, ids.length - 5000).forEach((k) => delete S.read[k]);
  set("read", S.read);
  document.querySelectorAll(`.card[data-id="${CSS.escape(id)}"]`).forEach((c) => c.classList.add("read"));
}

function toggleSave(id) {
  if (S.saved[id]) delete S.saved[id];
  else { const it = findItem(id); if (it) S.saved[id] = { ...it, _savedAt: Date.now() }; }
  set("saved", S.saved);
  if (S.view === "saved") renderSaved(); else render();
  $("#savedCount").textContent = `(${Object.keys(S.saved).length})`;
}

// ---- events
document.addEventListener("click", async (e) => {
  const open = e.target.closest("[data-open]");
  if (open) { markRead(open.dataset.open); return; }
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.view) { showView(b.dataset.view); return; }
  if (b.dataset.desk) { S.desk = b.dataset.desk; set("desk", S.desk); render(); return; }
  if (b.dataset.topic) {
    const t = b.dataset.topic;
    const list = S.topics[S.desk] || (S.topics[S.desk] = []);
    const i = list.indexOf(t);
    if (b.classList.contains("tag")) { S.topics[S.desk] = i >= 0 ? list : [...list, t]; } else if (i >= 0) list.splice(i, 1); else list.push(t);
    set("topics", S.topics); render(); window.scrollTo({ top: 0 }); return;
  }
  if (b.id === "picksOnly") { S.picksOnly = !S.picksOnly; set("picksOnly", S.picksOnly); render(); return; }
  if (b.id === "sort") { S.sort = S.sort === "newest" ? "relevant" : "newest"; set("sort", S.sort); render(); return; }
  if (b.id === "clear") { S.topics[S.desk] = []; S.picksOnly = false; S.q = ""; $("#q").value = ""; set("topics", S.topics); set("picksOnly", false); render(); return; }
  if (b.id === "theme") { const order = ["system", "dark", "light"]; set("theme", order[(order.indexOf(get("theme", "system")) + 1) % 3]); applyTheme(); return; }
  if (b.id === "searchOlder") {
    b.textContent = "Loading";
    const rows = [];
    for (const m of S.meta.months) { try { rows.push(...await fetchJSON(`data/search/${m}.json`)); } catch { /* skip month */ } }
    S.olderRows = rows; renderOlder(); return;
  }
  if (b.id === "exportSaved") {
    const blob = new Blob([JSON.stringify(Object.values(S.saved), null, 1)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `brief-saved-${londonDay(new Date())}.json` });
    a.click(); URL.revokeObjectURL(a.href); return;
  }
  const cardEl = b.closest(".card");
  if (!cardEl) return;
  const id = cardEl.dataset.id;
  if (b.classList.contains("sumbtn")) { const openNow = b.getAttribute("aria-expanded") !== "true"; b.setAttribute("aria-expanded", String(openNow)); b.nextElementSibling.classList.toggle("open", openNow); return; }
  if (b.classList.contains("save")) { toggleSave(id); return; }
  if (b.classList.contains("copy")) {
    const it = findItem(id);
    try { await navigator.clipboard.writeText(it.url); b.textContent = "Copied"; } catch { b.textContent = "Copy failed"; }
    setTimeout(() => (b.textContent = "Copy link"), 1200);
  }
});

$("#importFile").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    const list = JSON.parse(await f.text());
    for (const it of Array.isArray(list) ? list : []) if (it && it.id && it.url) S.saved[it.id] = it;
    set("saved", S.saved); renderSaved(); $("#savedCount").textContent = `(${Object.keys(S.saved).length})`;
  } catch { alert("That file is not a saved-items export."); }
  e.target.value = "";
});

let qTimer;
$("#q").addEventListener("input", (e) => { clearTimeout(qTimer); qTimer = setTimeout(() => { S.q = e.target.value.trim().toLowerCase(); render(); }, 120); });

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea")) { if (e.key === "Escape") { e.target.value = ""; S.q = ""; render(); e.target.blur(); } return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const cards = [...document.querySelectorAll(`#v-${S.view} .card`)];
  const i = cards.indexOf(document.activeElement);
  if (e.key === "j" || e.key === "k") {
    const next = cards[Math.max(0, Math.min(cards.length - 1, i + (e.key === "j" ? 1 : -1)))] || cards[0];
    if (next) { next.focus(); next.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }
  } else if (e.key === "o" && i >= 0) { const a = cards[i].querySelector("h4 a"); markRead(cards[i].dataset.id); window.open(a.href, "_blank", "noopener"); }
  else if (e.key === "s" && i >= 0) { toggleSave(cards[i].dataset.id); }
  else if (e.key === "/") { e.preventDefault(); showView("today"); $("#q").focus(); }
  else if (["1", "2", "3"].includes(e.key)) { S.desk = ["ip", "media", "both"][+e.key - 1]; set("desk", S.desk); render(); }
});

// ---- start
async function start() {
  try {
    S.meta = await fetchJSON("data/meta.json");
  } catch {
    $("#feed").innerHTML = '<p class="empty">The news data could not load. Try again in a minute.</p>';
    return;
  }
  const m = S.meta;
  document.title = m.title;
  $("#title").textContent = m.title;
  const g = new Date(m.generated_at);
  $("#utext").textContent = `Updated ${fmtTime.format(g)}, ${fmtDay.format(g).replace(",", "")} · ${m.health.ok} sources OK`;
  $("#hdot").className = `dot ${m.health.status === "green" ? "" : m.health.status}`;
  $("#hdot").title = `Source health: ${m.health.status}`;
  if (!S.desk || !["ip", "media", "both"].includes(S.desk)) S.desk = m.default_desk || "ip";
  for (const d of ["ip", "media", "both"]) if (!Array.isArray(S.topics[d])) S.topics[d] = [];
  $("#footer").innerHTML = `${m.sources.filter((s) => s.status !== "disabled").length} sources, collected every 3 hours. Summaries are written by AI: check the source before you rely on one.<br>${m.licence_notes.map(esc).join("<br>")}`;
  S.dayQueue = m.days.map((d) => d.date);
  await loadMore(3);
  showView(["saved", "sources"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "today");
  new IntersectionObserver((entries) => { if (entries.some((x) => x.isIntersecting) && S.view === "today") loadMore(1); }, { rootMargin: "800px" }).observe($("#sentinel"));
}
start();

if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(() => {});
