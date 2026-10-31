// WhatsApp simulator page: the left side behaves like the user's phone, the right side shows
// the bot's internal diagnosis (debug API). No build step, no libraries.
const $ = (id) => document.getElementById(id);
const state = { waId: "", lastSeq: 0, waitingSince: 0, bands: { accept: 0.8, unknown_below: 0.5 }, fields: {} };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const time = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem("fwbot-user") || "{}");
    if (saved.waId) $("waId").value = saved.waId;
    if (saved.name) $("name").value = saved.name;
  } catch (e) { /* storage unavailable */ }
  switchUser();
}
function save() {
  try { localStorage.setItem("fwbot-user", JSON.stringify({ waId: $("waId").value, name: $("name").value })); } catch (e) {}
}
function switchUser() {
  state.waId = $("waId").value.trim() || "919999999999";
  state.lastSeq = 0;
  state.waitingSince = 0;
  lastDiagKey = "";
  $("thread").innerHTML = "";
  $("diagnoses").innerHTML = '<p class="empty">Send a photo to see the 10 fields here.</p>';
  save();
  pollMessages();
  pollDiagnoses();
}

// ------------------------------------------------------------------ chat
function renderMessage(m) {
  const b = m.body, el = document.createElement("div");
  el.className = "msg " + (m.sender === "user" ? "user" : "bot");
  let html = "";
  if (m.type === "image") {
    const media = b.image || {};
    html += `<img src="/sim/api/media/${esc(media.id)}" alt="photo">`;
    if (media.caption) html += esc(media.caption);
  } else if (m.type === "text") {
    html += esc((b.text || {}).body);
  } else if (m.type === "interactive") {
    const it = b.interactive || {};
    if (m.sender === "user") {
      const r = it.button_reply || it.list_reply || {};
      html += esc(r.title);
    } else {
      html += esc((it.body || {}).text);
      const btns = it.type === "button" ? (it.action.buttons || []).map((x) => x.reply)
        : ((it.action.sections || [])[0] || { rows: [] }).rows;
      html += `<div class="buttons">${btns.map((x) => `<button data-id="${esc(x.id)}" data-title="${esc(x.title)}" data-kind="${it.type === "button" ? "button_reply" : "list_reply"}">${esc(x.title)}</button>`).join("")}</div>`;
    }
  }
  const ticks = m.sender === "user" ? ` <span class="ticks ${m.status === "read" ? "read" : ""}">✓✓</span>` : "";
  html += `<div class="meta">${time(m.created_at)}${ticks}</div>`;
  el.innerHTML = html;
  el.dataset.id = m.id;
  return el;
}

async function pollMessages() {
  const wa = state.waId;
  try {
    const r = await fetch(`/sim/api/messages?wa_id=${encodeURIComponent(wa)}&after=${state.lastSeq}`);
    const rows = await r.json();
    if (wa !== state.waId) return;
    const thread = $("thread");
    const typing = thread.querySelector(".typing");
    if (typing) typing.remove();
    for (const m of rows) {
      thread.appendChild(renderMessage(m));
      state.lastSeq = Math.max(state.lastSeq, m.seq);
      if (m.sender === "bot") state.waitingSince = 0;
    }
    if (state.waitingSince) {
      const t = document.createElement("div");
      t.className = "typing";
      t.textContent = "Bot is diagnosing…";
      thread.appendChild(t);
    }
    if (rows.length) thread.scrollTop = thread.scrollHeight;
  } catch (e) { /* server restarting */ }
}

async function refreshTicks() {
  // read receipts arrive after a message was rendered; re-fetch the user's recent messages' status
  try {
    const r = await fetch(`/sim/api/messages?wa_id=${encodeURIComponent(state.waId)}&after=${Math.max(0, state.lastSeq - 20)}`);
    for (const m of await r.json()) {
      if (m.sender !== "user" || m.status !== "read") continue;
      const el = document.querySelector(`.msg[data-id="${CSS.escape(m.id)}"] .ticks`);
      if (el) el.classList.add("read");
    }
  } catch (e) {}
}

// ------------------------------------------------------------------ sending
const pendingFiles = [];
$("photos").addEventListener("change", (e) => {
  for (const f of e.target.files) pendingFiles.push(f);
  e.target.value = "";
  showPending();
});
function showPending() {
  const box = $("pending");
  box.hidden = !pendingFiles.length;
  box.innerHTML = pendingFiles.map((f) => `<img src="${URL.createObjectURL(f)}" title="${esc(f.name)}">`).join("");
}
$("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("text").value.trim();
  if (!text && !pendingFiles.length) return;
  const fd = new FormData();
  fd.append("wa_id", state.waId);
  fd.append("name", $("name").value);
  fd.append("text", text);
  pendingFiles.forEach((f) => fd.append("photos", f));
  $("send").disabled = true;
  try {
    const r = await fetch("/sim/api/send", { method: "POST", body: fd });
    if (!r.ok) { alert((await r.json()).error || "Sending failed"); return; }
    $("text").value = "";
    pendingFiles.length = 0;
    showPending();
    state.waitingSince = Date.now();
    pollMessages();
  } finally {
    $("send").disabled = false;
  }
});
$("thread").addEventListener("click", async (e) => {
  const btn = e.target.closest(".buttons button");
  if (btn) {
    await fetch("/sim/api/reply", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wa_id: state.waId, name: $("name").value, reply_id: btn.dataset.id, title: btn.dataset.title, kind: btn.dataset.kind }) });
    pollMessages();
    return;
  }
  if (e.target.tagName === "IMG") lightbox(e.target.src);
});
$("diagnoses").addEventListener("click", (e) => { if (e.target.tagName === "IMG") lightbox(e.target.src); });
function lightbox(src) {
  const d = document.createElement("div");
  d.className = "lightbox";
  d.innerHTML = `<img src="${esc(src)}">`;
  d.onclick = () => d.remove();
  document.body.appendChild(d);
}
$("newUser").addEventListener("click", () => {
  $("waId").value = "91" + String(Math.floor(7000000000 + Math.random() * 2999999999));
  switchUser();
});
$("waId").addEventListener("change", switchUser);
$("name").addEventListener("change", save);

// ------------------------------------------------------------------ debug panel
const ACTION = { accept: "Accept", follow_up: "Follow-up needed", better_photo: "Better photo needed", ask_problem: "Ask what the problem is" };
let lastDiagKey = "";

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
  const thumbs = (d.media_ids || []).map((id) => `<img src="/debug/media/${esc(id)}" alt="">`).join("");
  const when = new Date(d.created_at * 1000).toLocaleString();
  if (d.status === "error") {
    card.innerHTML = `<div class="card-head"><div class="thumbs">${thumbs}</div><span class="title">#${d.id}</span>` +
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
  const decText = ACTION[dec.action] + (dec.action === "follow_up" ? ": " + dec.fields.map((k) => r.fields[k].label).join(", ") : "");
  const warnings = (r.warnings || []).map((w) => `<div class="warn">⚠ ${esc(w.message)}</div>`).join("");
  const usage = m.usage || {};
  card.innerHTML =
    `<div class="card-head"><div class="thumbs">${thumbs}</div><span class="title">#${d.id}</span>` +
    `<span class="badge ${esc(dec.action)}">${esc(decText)}</span>` +
    `<span class="sub">${esc(m.model)} · ${esc(m.prompt_version)} · ${(m.latency_ms / 1000).toFixed(1)}s` +
    (usage.total_tokens ? ` · ${usage.total_tokens} tokens` : "") + ` · ${esc(when)}</span></div>` +
    `<table class="fields">${rows}</table>` +
    `<div class="notes"><div><span class="k">What the model saw:</span> ${esc(r.visible_evidence) || "—"}</div>` +
    `<div><span class="k">Observation note:</span> ${esc(r.observation_note) || "—"}</div>` +
    `<div><span class="k">Decision rule:</span> ${esc(dec.reason)}</div>${warnings}</div>` +
    `<details class="raw"><summary>Raw model output</summary><pre>${esc(prettyJson(r.raw_model_output))}</pre></details>`;
  return card;
}
function prettyJson(s) { try { return JSON.stringify(JSON.parse(s), null, 2); } catch (e) { return s; } }

async function pollDiagnoses() {
  const wa = state.waId;
  try {
    const r = await fetch(`/debug/api/diagnoses?wa_id=${encodeURIComponent(wa)}&limit=30`);
    const rows = await r.json();
    if (wa !== state.waId) return;
    const key = rows.map((x) => x.id).join(",");
    if (key === lastDiagKey) return;
    lastDiagKey = key;
    const box = $("diagnoses");
    box.innerHTML = rows.length ? "" : '<p class="empty">Send a photo to see the 10 fields here.</p>';
    rows.forEach((d) => box.appendChild(renderDiagnosis(d)));
  } catch (e) {}
}

async function loadInfo() {
  try {
    const i = await (await fetch("/debug/api/info")).json();
    state.bands = i.bands;
    i.fields.forEach((f) => (state.fields[f.key] = f));
    $("info").textContent = `${i.provider} · ${i.model} · prompt ${i.prompt} · bands ${i.bands.unknown_below} / ${i.bands.accept}`;
  } catch (e) {}
}

loadInfo().then(load);
setInterval(pollMessages, 1200);
setInterval(pollDiagnoses, 2000);
setInterval(refreshTicks, 4000);
