// Backend dashboard: the latest diagnosis the bot made, with the 10 fields, confidence, decision and raw output.
// (Every diagnosis is still stored in data/bot.db; only the newest one is shown here.)
// Polls the dashboard API on this same port. No build step, no libraries.
const $ = (id) => document.getElementById(id);
const state = { bands: { accept: 0.8, unknown_below: 0.5 }, fields: {}, lastKey: "" };
const ACTION = { accept: "Accept", follow_up: "Follow-up needed", better_photo: "Better photo needed", ask_problem: "Ask what the problem is" };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const prettyJson = (s) => { try { return JSON.stringify(JSON.parse(s), null, 2); } catch (e) { return s; } };

function bar(conf) {
  const b = state.bands, pct = Math.round(conf * 100);
  const color = conf >= b.accept ? "var(--ok)" : conf >= b.unknown_below ? "var(--warn)" : "var(--bad)";
  return `<div class="bar-row"><div class="bar" style="flex:1"><span style="width:${pct}%;background:${color}"></span>` +
    `<i class="mark" style="left:${b.unknown_below * 100}%"></i><i class="mark" style="left:${b.accept * 100}%"></i></div>` +
    `<span class="num">${conf.toFixed(2)}</span></div>`;
}


function renderDiagnosis(d) {
  const card = document.createElement("article");
  card.className = "card";
  const thumbs = (d.media_ids || []).map((id) => `<img src="media/${esc(id)}" alt="">`).join("");
  const when = new Date(d.created_at * 1000).toLocaleString();
  const who = `<span class="who">${esc(d.name ? `${d.name} · ${d.wa_id}` : d.wa_id)}</span>`;
  if (d.status === "error") {
    card.innerHTML = `<div class="card-head"><div class="thumbs">${thumbs}</div><span class="title">#${d.id}</span>${who}` +
      `<span class="badge error">Failed</span><span class="sub">${esc(when)}</span></div><div class="error-text">${esc(d.error)}</div>`;
    return card;
  }
  const r = d.result, m = r.meta;
  const rows = r.order.map((key) => {
    const f = r.fields[key], pd = state.fields[key] && state.fields[key].product_deciding;
    const was = f.value !== f.model_value ? `<span class="was">model said: ${esc(f.model_value)}</span>` : "";
    return `<tr><td class="lbl">${esc(f.label)}${pd ? '<span class="pd" title="Product-deciding field">●</span>' : ""}</td>` +
      `<td class="val">${esc(f.value)}${was}</td><td class="conf">${bar(f.confidence)}</td>` +
      `<td><span class="st ${esc(f.status)}">${esc(f.status)}</span></td></tr>`;
  }).join("");
  const dec = r.decision;
  const decText = (ACTION[dec.action] || dec.action) + (dec.action === "follow_up" ? ": " + dec.fields.map((k) => r.fields[k].label).join(", ") : "");
  const warnings = (r.warnings || []).map((w) => `<div class="warn">⚠ ${esc(w.message)}</div>`).join("");
  const usage = m.usage || {};
  card.innerHTML =
    `<div class="card-head"><div class="thumbs">${thumbs}</div><span class="title">#${d.id}</span>${who}` +
    `<span class="badge ${esc(dec.action)}">${esc(decText)}</span>` +
    `<span class="sub">${esc(m.model)} · ${esc(m.prompt_version)} · ${(m.latency_ms / 1000).toFixed(1)}s` +
    (usage.total_tokens ? ` · ${usage.total_tokens} tokens` : "") +
    (usage.cost_usd != null ? ` · $${Number(usage.cost_usd).toFixed(4)}` : "") +
    (usage.routed_to ? ` · via ${esc(usage.routed_to)}` : "") + ` · ${esc(when)}</span></div>` +
    `<table class="fields">${rows}</table>` +
    `<div class="notes"><div><span class="k">What the model saw:</span> ${esc(r.visible_evidence) || "—"}</div>` +
    `<div><span class="k">Observation note:</span> ${esc(r.observation_note) || "—"}</div>` +
    `<div><span class="k">Decision rule:</span> ${esc(dec.reason)}</div>${warnings}` +
    `<div><span class="k">Customer was told:</span><div class="reply">${esc(d.reply)}</div></div></div>` +
    `<details class="raw"><summary>Raw model output</summary><pre>${esc(prettyJson(r.raw_model_output))}</pre></details>`;
  return card;
}

async function pollDiagnoses() {
  try {
    const rows = await (await fetch("api/diagnoses?limit=1")).json();
    const key = rows.map((x) => x.id).join(",");
    if (key === state.lastKey) return;
    state.lastKey = key;
    const box = $("diagnoses");
    box.innerHTML = rows.length ? "" : '<p class="empty">No diagnosis yet. Send a photo from the chat page and it will appear here.</p>';
    rows.forEach((d) => box.appendChild(renderDiagnosis(d)));
  } catch (e) { /* server restarting */ }
}

async function loadInfo() {
  try {
    const i = await (await fetch("api/info")).json();
    state.bands = i.bands;
    i.fields.forEach((f) => (state.fields[f.key] = f));
    $("info").textContent = `${i.channel} · ${i.provider} · ${i.model} · prompt ${i.prompt} · bands ${i.bands.unknown_below} / ${i.bands.accept}`;
  } catch (e) {}
}

$("diagnoses").addEventListener("click", (e) => {
  if (e.target.tagName !== "IMG") return;
  const d = document.createElement("div");
  d.className = "lightbox";
  d.innerHTML = `<img src="${esc(e.target.src)}">`;
  d.onclick = () => d.remove();
  document.body.appendChild(d);
});

(async function start() {
  await loadInfo();
  pollDiagnoses();
  setInterval(pollDiagnoses, 2000);
})();
