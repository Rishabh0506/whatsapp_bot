// WhatsApp simulator, customer side: behaves like the customer's WhatsApp (laid out like WhatsApp Web).
// It only shows what WhatsApp would show: messages, photos, ticks, and "typing…" when the bot sends a typing
// indicator. The bot's internal diagnosis is on the backend dashboard (separate port). No build step, no libraries.
const $ = (id) => document.getElementById(id);
const DEFAULT_WA = "919999999999";
const state = {
  waId: "", lastSeq: 0, lastDay: "", lastSender: "", typing: false,
  recent: [],            // [{waId, name}] test customers used on this computer
  pending: [], current: 0, // photos chosen but not sent yet
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hhmm = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const initials = (name) => (String(name || "").trim().split(/\s+/).map((w) => w[0]).join("").slice(0, 2) || "?").toUpperCase();

function dayLabel(t) {
  const d = new Date(t * 1000), today = new Date();
  const yest = new Date(); yest.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yest.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { day: "numeric", month: "long", year: "numeric" });
}

// WhatsApp text formatting: *bold* _italic_ ~strike~ ```mono``` `code`, plus clickable links.
function formatWhatsApp(raw) {
  let s = esc(raw);
  s = s.replace(/```([\s\S]+?)```/g, "<code>$1</code>");
  s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  const wrap = (mark, tag) => {
    const m = mark.replace(/[*~]/g, "\\$&");
    s = s.replace(new RegExp(`(^|[\\s(>])${m}(?=\\S)([^\\n]*?\\S)${m}(?=$|[\\s.,!?:;)<])`, "g"), `$1<${tag}>$2</${tag}>`);
  };
  wrap("*", "strong"); wrap("_", "em"); wrap("~", "del");
  s = s.replace(/(https?:\/\/[^\s<]+[^\s<.,!?:;)])/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  return s;
}

const TICK_ONE = '<svg viewBox="0 0 16 11" width="16" height="11"><path fill="currentColor" d="M11.07.65 10.4.1a.4.4 0 0 0-.56.07L4.1 7.3 1.7 5.07a.4.4 0 0 0-.56.02l-.6.64a.4.4 0 0 0 .02.56l3.2 2.98c.17.16.44.14.59-.04L11.14 1.2a.4.4 0 0 0-.07-.56z"/></svg>';
const TICK_TWO = '<svg viewBox="0 0 16 11" width="16" height="11"><path fill="currentColor" d="M11.07.65 10.4.1a.4.4 0 0 0-.56.07L4.1 7.3 1.7 5.07a.4.4 0 0 0-.56.02l-.6.64a.4.4 0 0 0 .02.56l3.2 2.98c.17.16.44.14.59-.04L11.14 1.2a.4.4 0 0 0-.07-.56zm4 0L14.4.1a.4.4 0 0 0-.56.07L8.1 7.3l-.9-.84-.97 1.13 1.6 1.5c.17.16.44.14.59-.04L15.14 1.2a.4.4 0 0 0-.07-.56z"/></svg>';
function ticks(status) {
  if (status === "read") return `<span class="tick read">${TICK_TWO}</span>`;
  if (status === "delivered") return `<span class="tick">${TICK_TWO}</span>`;
  return `<span class="tick">${TICK_ONE}</span>`;
}

// ------------------------------------------------------------------ test customer (who this page is)
function loadProfile() {
  try {
    const saved = JSON.parse(localStorage.getItem("fwbot-user") || "{}");
    $("waId").value = saved.waId || DEFAULT_WA;
    $("name").value = saved.name || "Test user";
    state.recent = JSON.parse(localStorage.getItem("fwbot-recent") || "[]");
  } catch (e) {
    $("waId").value = DEFAULT_WA; $("name").value = "Test user";
  }
}
function saveProfile() {
  const me = { waId: state.waId, name: $("name").value.trim() || "Test user" };
  state.recent = [me, ...state.recent.filter((r) => r.waId !== me.waId)].slice(0, 12);
  try {
    localStorage.setItem("fwbot-user", JSON.stringify(me));
    localStorage.setItem("fwbot-recent", JSON.stringify(state.recent));
  } catch (e) { /* storage unavailable */ }
  renderProfile();
}
function renderProfile() {
  const name = $("name").value.trim() || "Test user";
  $("me").textContent = initials(name);
  $("me").title = `Test customer: ${name} (${state.waId})`;
  $("bigAvatar").textContent = initials(name);
  $("recent").innerHTML = state.recent.map((r) =>
    `<li data-wa="${esc(r.waId)}" class="${r.waId === state.waId ? "current" : ""}"><div class="avatar">${esc(initials(r.name))}</div>` +
    `<div class="who"><div>${esc(r.name)}</div><div>+${esc(r.waId)}</div></div></li>`).join("");
}
function switchUser(waId, name) {
  if (waId !== undefined) $("waId").value = waId;
  if (name !== undefined) $("name").value = name;
  state.waId = $("waId").value.replace(/\D/g, "") || DEFAULT_WA;
  $("waId").value = state.waId;
  state.lastSeq = 0; state.lastDay = ""; state.lastSender = ""; state.typing = false; stick = true;
  $("thread").innerHTML = "";
  setLastMessage(null);
  setTyping(false);
  saveProfile();
  pollMessages();
}
function newCustomer() {
  const n = "91" + String(Math.floor(7000000000 + Math.random() * 2999999999));
  switchUser(n, "Customer " + n.slice(-4));
  $("profilePanel").hidden = true;
}

// ------------------------------------------------------------------ messages
function bodyOf(m) {
  const b = m.body || {};
  if (m.type === "text") return { text: (b.text || {}).body || "" };
  if (m.type === "image") return { image: (b.image || {}).id, link: (b.image || {}).link, text: (b.image || {}).caption || "" };
  if (m.type === "audio" || m.type === "video") return { media: (b[m.type] || {}).id, kind: m.type };
  if (m.type === "interactive") {
    const it = b.interactive || {};
    if (m.sender === "user") return { text: (it.button_reply || it.list_reply || {}).title || "" };
    return { text: (it.body || {}).text || "", interactive: it };
  }
  return { text: `[${m.type} message]` };
}

function renderMessage(m) {
  const frag = document.createDocumentFragment();
  const day = dayLabel(m.created_at);
  if (day !== state.lastDay) {
    const chip = document.createElement("div");
    chip.className = "day"; chip.textContent = day;
    frag.appendChild(chip);
    state.lastDay = day; state.lastSender = "";
  }
  const who = m.sender === "user" ? "user" : "bot";
  const row = document.createElement("div");
  row.className = `row ${who}` + (state.lastSender !== who ? " first" : "");
  row.dataset.id = m.id;
  state.lastSender = who;

  const c = bodyOf(m);
  const meta = `<span class="meta">${hhmm(m.created_at)}${who === "user" ? ticks(m.status) : ""}</span>`;
  let html = "";
  if (c.image || c.link) {
    const src = c.image ? `/sim/api/media/${encodeURIComponent(c.image)}` : c.link;
    html += `<img src="${esc(src)}" alt="Photo">`;
  }
  if (c.media) {
    const src = `/sim/api/media/${encodeURIComponent(c.media)}`;
    html += c.kind === "audio" ? `<div class="voice">🎤 Voice message<audio controls preload="none" src="${esc(src)}"></audio></div>`
      : `<video controls preload="metadata" src="${esc(src)}"></video>`;
  }
  if (c.text) html += `<div class="text">${formatWhatsApp(c.text)}<span class="spacer"></span></div>`;
  else if (!c.image && !c.link && !c.media) html += `<div class="text"><span class="spacer"></span></div>`;
  const actions = c.interactive ? renderActions(c.interactive, m.id) : "";

  const bubble = document.createElement("div");
  bubble.className = "bubble" + ((c.image || c.link) ? " photo" + (c.text ? "" : " bare") : "");
  bubble.innerHTML = `<div class="content">${html}${meta}</div>${actions}`;
  bubble.querySelectorAll("img").forEach((img) => img.addEventListener("load", () => { if (stick) scrollDown(); }));
  row.appendChild(bubble);
  frag.appendChild(row);
  return frag;
}

// reply buttons and list messages, drawn the way WhatsApp draws them under the bubble
function renderActions(it, msgId) {
  const act = it.action || {};
  if (it.type === "button") {
    return `<div class="actions">${(act.buttons || []).map((x) => x.reply || {}).map((r) =>
      `<button type="button" data-kind="button_reply" data-id="${esc(r.id)}" data-title="${esc(r.title)}">↩ ${esc(r.title)}</button>`).join("")}</div>`;
  }
  if (it.type === "list") {
    return `<div class="actions"><button type="button" data-list="${esc(msgId)}">☰ ${esc(act.button || "Options")}</button></div>`;
  }
  return "";
}

function setLastMessage(m) {
  if (!m) { $("lastMsg").textContent = "Send a photo of the footwear that needs fixing"; $("lastTime").textContent = ""; return; }
  const c = bodyOf(m);
  const text = (c.image || c.link) ? "📷 " + (c.text || "Photo")
    : c.media ? (c.kind === "audio" ? "🎤 Voice message" : "🎥 Video")
    : (c.text || "").split("\n").find((l) => l.trim()) || "";
  $("lastMsg").innerHTML = (m.sender === "user" ? ticks(m.status) : "") + `<span>${esc(text)}</span>`;
  $("lastTime").textContent = hhmm(m.created_at);
}

const messages = new Map();   // id -> message, for list sheets and tick updates
let stick = true;             // keep the newest message in view unless the user scrolled up
const scrollDown = () => { const t = $("thread"); t.scrollTop = t.scrollHeight; };
$("thread").addEventListener("scroll", () => {
  const t = $("thread");
  stick = t.scrollHeight - t.scrollTop - t.clientHeight < 120;
});
async function pollMessages() {
  const wa = state.waId;
  try {
    const r = await fetch(`/sim/api/messages?wa_id=${encodeURIComponent(wa)}&after=${state.lastSeq}`);
    const rows = await r.json();
    if (wa !== state.waId || !rows.length) return;
    const thread = $("thread");
    for (const m of rows) {
      if (m.seq <= state.lastSeq) continue;
      messages.set(m.id, m);
      thread.appendChild(renderMessage(m));
      state.lastSeq = m.seq;
    }
    setLastMessage(rows[rows.length - 1]);
    if (stick || rows.some((m) => m.sender === "user")) { stick = true; scrollDown(); }
  } catch (e) { /* server restarting */ }
}

async function refreshTicks() {
  try {
    const r = await fetch(`/sim/api/messages?wa_id=${encodeURIComponent(state.waId)}&after=${Math.max(0, state.lastSeq - 30)}`);
    const rows = await r.json();
    for (const m of rows) {
      if (m.sender !== "user") continue;
      messages.set(m.id, m);
      const el = document.querySelector(`.row[data-id="${CSS.escape(m.id)}"] .meta`);
      if (el) el.innerHTML = hhmm(m.created_at) + ticks(m.status);
    }
    if (rows.length) setLastMessage(rows[rows.length - 1]);
  } catch (e) {}
}

function setTyping(on) {
  state.typing = on;
  $("sub").textContent = on ? "typing…" : "Business account";
  $("sub").classList.toggle("typing", on);
  if (on) $("lastMsg").innerHTML = '<span style="color:var(--green-dark)">typing…</span>';
}
async function pollPresence() {
  const wa = state.waId;
  try {
    const p = await (await fetch(`/sim/api/presence?wa_id=${encodeURIComponent(wa)}`)).json();
    if (wa !== state.waId || p.typing === state.typing) return;
    setTyping(p.typing);
    if (!p.typing) refreshTicks();
  } catch (e) {}
}

// ------------------------------------------------------------------ sending
async function send(fields, files = []) {
  const fd = new FormData();
  fd.append("wa_id", state.waId);
  fd.append("name", $("name").value.trim() || "Test user");
  for (const [k, v] of Object.entries(fields)) fd.append(k, v);
  files.forEach((f) => fd.append("photos", f));
  const r = await fetch("/sim/api/send", { method: "POST", body: fd });
  if (!r.ok) { notice((await r.json().catch(() => ({}))).error || "Sending failed"); return false; }
  await pollMessages();
  return true;
}
function notice(text) {
  const n = document.createElement("div");
  n.className = "notice"; n.textContent = text;
  $("thread").appendChild(n);
  $("thread").scrollTop = $("thread").scrollHeight;
}

const textBox = $("text");
function autosize() {
  textBox.style.height = "auto";
  textBox.style.height = Math.min(textBox.scrollHeight, 140) + "px";
  $("send").classList.toggle("ready", !!textBox.value.trim());
}
textBox.addEventListener("input", autosize);
textBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("composer").requestSubmit(); }
});
$("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = textBox.value.trim();
  if (!text) return;
  textBox.value = ""; autosize();
  if (!(await send({ text }))) { textBox.value = text; autosize(); }
});

// photo preview (WhatsApp Web asks for a caption before sending photos).
// Voice notes and videos are sent straight away, as their own messages.
function addPhotos(files) {
  const other = [...files].filter((f) => f.type.startsWith("audio/") || f.type.startsWith("video/"));
  if (other.length) send({}, other);
  const imgs = [...files].filter((f) => f.type.startsWith("image/"));
  if (!imgs.length) return;
  imgs.forEach((f) => state.pending.push({ file: f, url: URL.createObjectURL(f) }));
  state.current = state.pending.length - 1;
  renderPreview();
}
function renderPreview() {
  const p = state.pending;
  $("preview").hidden = !p.length;
  if (!p.length) return;
  state.current = Math.min(state.current, p.length - 1);
  $("previewImg").src = p[state.current].url;
  $("previewName").textContent = p[state.current].file.name;
  $("previewThumbs").innerHTML = p.map((x, i) =>
    `<button type="button" data-i="${i}" class="${i === state.current ? "on" : ""}" title="${esc(x.file.name)}">` +
    `<img src="${x.url}" alt=""><span class="rm" data-rm="${i}">×</span></button>`).join("");
  $("caption").focus();
}
function closePreview() {
  state.pending.forEach((x) => URL.revokeObjectURL(x.url));
  state.pending = []; $("caption").value = "";
  renderPreview();
}
$("photos").addEventListener("change", (e) => { addPhotos(e.target.files); e.target.value = ""; });
$("morePhotos").addEventListener("change", (e) => { addPhotos(e.target.files); e.target.value = ""; });
$("closePreview").addEventListener("click", closePreview);
$("previewThumbs").addEventListener("click", (e) => {
  const rm = e.target.closest("[data-rm]");
  if (rm) {
    const [x] = state.pending.splice(+rm.dataset.rm, 1);
    URL.revokeObjectURL(x.url);
    if (!state.pending.length) return closePreview();
    return renderPreview();
  }
  const b = e.target.closest("button[data-i]");
  if (b) { state.current = +b.dataset.i; renderPreview(); }
});
$("caption").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("sendPhotos").click(); } });
$("sendPhotos").addEventListener("click", async () => {
  if (!state.pending.length) return;
  $("sendPhotos").disabled = true;
  try {
    const ok = await send({ text: $("caption").value.trim() }, state.pending.map((x) => x.file));
    if (ok) closePreview();
  } finally { $("sendPhotos").disabled = false; }
});

// drag & drop photos onto the chat
let dragDepth = 0;
$("conv").addEventListener("dragenter", (e) => { if ([...e.dataTransfer.types].includes("Files")) { dragDepth++; $("dropHint").hidden = false; } });
$("conv").addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; $("dropHint").hidden = true; } });
$("conv").addEventListener("dragover", (e) => e.preventDefault());
$("conv").addEventListener("drop", (e) => { e.preventDefault(); dragDepth = 0; $("dropHint").hidden = true; addPhotos(e.dataTransfer.files); });
// paste a screenshot / photo
document.addEventListener("paste", (e) => { if (e.clipboardData && e.clipboardData.files.length) addPhotos(e.clipboardData.files); });

// ------------------------------------------------------------------ taps on bot buttons / lists, photos
$("thread").addEventListener("click", async (e) => {
  const btn = e.target.closest(".actions button[data-kind]");
  if (btn) return reply(btn.dataset.kind, btn.dataset.id, btn.dataset.title);
  const list = e.target.closest(".actions button[data-list]");
  if (list) return openList(messages.get(list.dataset.list));
  if (e.target.tagName === "IMG") lightbox(e.target.src);
});
async function reply(kind, id, title) {
  await fetch("/sim/api/reply", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ wa_id: state.waId, name: $("name").value, reply_id: id, title, kind }) });
  pollMessages();
}
function openList(m) {
  if (!m) return;
  const it = m.body.interactive, sheet = $("sheet");
  const secs = (it.action.sections || []).map((s) => `<div class="sec">${esc(s.title || "")}</div>` +
    (s.rows || []).map((r) => `<label><input type="radio" name="row" value="${esc(r.id)}" data-title="${esc(r.title)}">` +
      `<span>${esc(r.title)}${r.description ? `<small>${esc(r.description)}</small>` : ""}</span></label>`).join("")).join("");
  sheet.innerHTML = `<div class="sheet"><h4>${esc(it.action.button || "Options")}</h4>${secs}` +
    `<div class="sheet-foot"><button type="button" data-close>Cancel</button><button type="button" class="primary" data-send>Send</button></div></div>`;
  sheet.hidden = false;
}
$("sheet").addEventListener("click", (e) => {
  const sheet = $("sheet");
  if (e.target === sheet || e.target.closest("[data-close]")) { sheet.hidden = true; return; }
  if (e.target.closest("[data-send]")) {
    const pick = sheet.querySelector("input[name=row]:checked");
    if (!pick) return;
    sheet.hidden = true;
    reply("list_reply", pick.value, pick.dataset.title);
  }
});
function lightbox(src) {
  const d = document.createElement("div");
  d.className = "lightbox";
  d.innerHTML = `<img src="${esc(src)}" alt="">`;
  d.onclick = () => d.remove();
  document.body.appendChild(d);
}
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  document.querySelector(".lightbox")?.remove();
  $("sheet").hidden = true;
  if (!$("preview").hidden) closePreview();
  else $("profilePanel").hidden = true;
});

// ------------------------------------------------------------------ side panels
$("me").addEventListener("click", () => { $("profilePanel").hidden = !$("profilePanel").hidden; });
$("closeProfile").addEventListener("click", () => { $("profilePanel").hidden = true; });
$("newCustomer").addEventListener("click", newCustomer);
$("newCustomer2").addEventListener("click", newCustomer);
$("waId").addEventListener("change", () => switchUser());
$("name").addEventListener("input", renderProfile);
$("name").addEventListener("change", saveProfile);
$("recent").addEventListener("click", (e) => {
  const li = e.target.closest("li[data-wa]");
  if (!li) return;
  const r = state.recent.find((x) => x.waId === li.dataset.wa);
  switchUser(r.waId, r.name);
});
$("search").addEventListener("input", (e) => {
  const q = e.target.value.trim().toLowerCase();
  $("botChat").hidden = !!q && !"footwear helpline".includes(q);
});
$("botChat").addEventListener("click", () => $("app").classList.remove("show-list"));
$("showList").addEventListener("click", () => $("app").classList.add("show-list"));

// ------------------------------------------------------------------ start
loadProfile();
switchUser();
setInterval(pollMessages, 1200);
setInterval(pollPresence, 1000);
setInterval(refreshTicks, 3000);
