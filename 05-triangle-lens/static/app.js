/* TriageLens front end: vanilla JS, no build step. */
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const CAT = {
  clinical: "Clinical",
  biomedical_computational: "Computational",
  preclinical_lab: "Preclinical",
  non_medical: "Non-medical",
};
const TABS = [["all", "All"], ["new", "New"], ["analyzed", "Analyzed"], ["assigned", "Assigned"], ["done", "Done"]];

const state = {
  subs: [], rules: null, settings: { checkers: [], model: "" }, status: { ollama: false, models: [] },
  tab: "all", q: "", cat: "", spec: "", check: "", openId: null, busy: new Set(),
};

/* ---------- helpers ---------- */
async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : "Request failed");
  }
  return res.json();
}
let toastTimer;
function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (err ? " err" : "");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add("hidden"), 3400);
}
const effSpec = s => s.specialty_override || s.analysis?.suggested_specialty || "";
const needed = s => s.analysis?.checks_required || [];
const short = k => state.rules?.checks?.[k]?.short || state.rules?.checks?.[k]?.label?.split(" ").slice(0, 2).join(" ") || k;
const fmtDate = iso => { const d = new Date(iso); return isNaN(d) ? "" : `${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`; };
const find = id => state.subs.find(s => s.id === id);

async function refresh() {
  state.subs = await api("/submissions");
  renderAll();
}
function replace(sub) {
  const i = state.subs.findIndex(s => s.id === sub.id);
  if (i >= 0) state.subs[i] = sub; else state.subs.unshift(sub);
}

/* ---------- filtering ---------- */
function visible() {
  const q = state.q.toLowerCase();
  return state.subs.filter(s => {
    if (state.tab !== "all" && s.status !== state.tab) return false;
    if (state.cat && s.analysis?.category !== state.cat) return false;
    if (state.spec && effSpec(s) !== state.spec) return false;
    if (state.check && !needed(s).includes(state.check)) return false;
    if (q && !(`${s.title} ${s.tags.join(" ")} ${s.external_id} ${s.id}`.toLowerCase().includes(q))) return false;
    return true;
  });
}

/* ---------- rendering ---------- */
function renderAll() {
  renderStats(); renderTabs(); renderFilters(); renderRows(); renderInsights();
  if (state.openId) renderDrawer();
}

function renderStats() {
  const s = state.subs;
  const open = s.filter(x => x.status !== "done");
  const pending = s.filter(x => !x.analysis).length;
  const openChecks = open.reduce((n, x) => n + needed(x).filter(c => !x.checks_done.includes(c)).length, 0);
  const assigned = s.filter(x => x.status === "assigned").length;
  const cards = [[s.length, "Submissions in queue"], [pending, "Awaiting analysis"], [openChecks, "Checks still open"], [assigned, "Assigned, in progress"]];
  $("#stats").innerHTML = cards.map(([n, l]) => `<div class="stat"><b>${n}</b><span>${l}</span></div>`).join("");
}

function renderTabs() {
  $("#tabs").innerHTML = TABS.map(([k, l]) => {
    const n = k === "all" ? state.subs.length : state.subs.filter(s => s.status === k).length;
    return `<button class="tab ${state.tab === k ? "on" : ""}" data-tab="${k}">${l}<span class="n">${n}</span></button>`;
  }).join("");
}

function fillSelect(sel, first, options, value) {
  const cur = value;
  sel.innerHTML = `<option value="">${first}</option>` + options.map(([v, l]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`).join("");
}
function renderFilters() {
  fillSelect($("#fCat"), "All categories", Object.entries(CAT), state.cat);
  const specs = [...Object.keys(state.rules?.specialties || {}), state.rules?.default_specialty].filter(Boolean);
  fillSelect($("#fSpec"), "All specialties", specs.map(x => [x, x]), state.spec);
  fillSelect($("#fCheck"), "Any check", Object.keys(state.rules?.checks || {}).map(k => [k, short(k)]), state.check);
}

function renderRows() {
  const list = visible();
  $("#empty").classList.toggle("hidden", state.subs.length > 0);
  $(".queue").classList.toggle("hidden", state.subs.length === 0);
  $(".toolbar").classList.toggle("hidden", state.subs.length === 0);
  $("#rows").innerHTML = list.length || !state.subs.length ? list.map(rowHtml).join("") :
    `<tr><td colspan="8" style="text-align:center;color:var(--ink-3);padding:40px">No submissions match these filters.</td></tr>`;
}

function rowHtml(s) {
  const a = s.analysis;
  const busy = state.busy.has(s.id);
  const checks = needed(s).map(c => `<span class="cp ${s.checks_done.includes(c) ? "done" : ""}">${esc(short(c))}</span>`).join("");
  const conf = a?.confidence != null
    ? `<div class="conf"><div class="bar"><i style="width:${Math.round(a.confidence * 100)}%"></i></div><small>${Math.round(a.confidence * 100)}%</small></div>`
    : `<span class="muted">${a ? "rules only" : ""}</span>`;
  return `<tr data-id="${s.id}">
    <td class="date">${fmtDate(s.created_at)}</td>
    <td class="eid">${esc(s.external_id || "#" + s.id)}</td>
    <td>
      <div class="t-title">${esc(s.title)}</div>
      <div class="chips">${s.tags.map(t => `<span class="chip">${esc(t)}</span>`).join("")}</div>
      ${s.dup_of ? `<div class="dup">Possible duplicate of #${s.dup_of}</div>` : ""}
      <span class="status-dot st-${s.status}">${s.status}${s.assigned_to ? " · " + esc(s.assigned_to) : ""}</span>
    </td>
    <td>${a?.category ? `<span class="cat ${a.category}">${CAT[a.category]}</span>` : '<span class="muted">—</span>'}</td>
    <td class="spec">${esc(effSpec(s)) || '<span class="muted">—</span>'}${s.specialty_override ? "<small>manual override</small>" : ""}</td>
    <td><div class="pills">${checks || (a ? '<span class="muted">none flagged</span>' : "")}</div></td>
    <td>${conf}</td>
    <td class="acts">
      <button class="btn btn-outline btn-sm" data-act="analyze" ${busy ? "disabled" : ""}>${busy ? '<i class="spin"></i> Analyzing' : a ? "Re-analyze" : "Analyze"}</button>
      <button class="btn btn-primary btn-sm" data-act="open">Open</button>
    </td></tr>`;
}

function barRows(entries, emptyMsg) {
  if (!entries.length) return `<div class="ins-empty">${emptyMsg}</div>`;
  const max = Math.max(...entries.map(e => e[1]));
  return entries.map(([l, n]) => `<div class="bar-row"><span>${esc(l)}</span><b>${n}</b><div class="track"><i style="width:${(n / max) * 100}%"></i></div></div>`).join("");
}
function tally(items) {
  const m = new Map(); items.filter(Boolean).forEach(x => m.set(x, (m.get(x) || 0) + 1));
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}
function renderInsights() {
  const analyzed = state.subs.filter(s => s.analysis);
  const msg = "Analyze some submissions to see this.";
  $("#insSpec").innerHTML = barRows(tally(analyzed.map(effSpec)), msg);
  $("#insChecks").innerHTML = barRows(tally(analyzed.flatMap(needed)).map(([k, n]) => [short(k), n]), msg);
  $("#insCat").innerHTML = barRows(tally(analyzed.map(s => s.analysis.category)).map(([k, n]) => [CAT[k] || k, n]), msg);
}

/* ---------- drawer ---------- */
function openDrawer(id) { state.openId = id; renderDrawer(); $("#drawer").classList.add("open"); $("#scrim").classList.remove("hidden"); $("#drawer").setAttribute("aria-hidden", "false"); }
function closeDrawer() { state.openId = null; $("#drawer").classList.remove("open"); $("#scrim").classList.add("hidden"); $("#drawer").setAttribute("aria-hidden", "true"); }

function renderDrawer() {
  const s = find(state.openId);
  if (!s) return closeDrawer();
  const a = s.analysis;
  const specs = [...Object.keys(state.rules.specialties), state.rules.default_specialty];
  const checkers = state.settings.checkers;
  const doneN = needed(s).filter(c => s.checks_done.includes(c)).length;
  const busy = state.busy.has(s.id);

  $("#drawer").innerHTML = `
  <div class="d-head">
    <div class="top"><span>${esc(s.external_id || "#" + s.id)} · submitted ${fmtDate(s.created_at)}</span><button class="d-close" data-d="close" aria-label="Close">×</button></div>
    <h2>${esc(s.title)}</h2>
  </div>
  <div class="d-body">
    ${s.dup_of ? `<div class="warn">This title is very similar to submission #${s.dup_of}. Check for a duplicate submission.</div>` : ""}
    <div class="sec"><div class="chips">${s.tags.map(t => `<span class="chip">${esc(t)}</span>`).join("") || '<span class="muted">No subject tags</span>'}</div></div>

    <div class="sec">
      <h4>Abstract</h4>
      <textarea id="dAbs" rows="5" placeholder="Paste the abstract here for a much more accurate analysis…">${esc(s.abstract)}</textarea>
      <div class="btn-row"><button class="btn btn-outline btn-sm" data-d="saveabs" ${busy ? "disabled" : ""}>Save abstract and re-analyze</button></div>
    </div>

    <div class="sec">
      <h4>Analysis ${a ? `<span class="muted" style="text-transform:none;letter-spacing:0">· ${a.source === "llama" ? "Llama" : "rules only"}</span>` : ""}</h4>
      ${a ? `<div class="card">
        ${a.summary ? `<p class="summary">${esc(a.summary)}</p>` : ""}
        <dl class="kv">
          <dt>Category</dt><dd>${a.category ? `<span class="cat ${a.category}">${CAT[a.category]}</span>` : "—"}</dd>
          ${a.study_type ? `<dt>Study type</dt><dd>${esc(a.study_type)}</dd>` : ""}
          <dt>Suggested</dt><dd>${esc(a.suggested_specialty) || "—"}</dd>
          <dt>Confidence</dt><dd>${a.confidence != null ? Math.round(a.confidence * 100) + "%" : "n/a"}</dd>
          <dt>Why</dt><dd style="font-weight:400">${esc(a.reason)}</dd>
        </dl>
        ${a.attention_points?.length ? `<h4 style="margin:14px 0 6px">Double-check</h4><ul class="points">${a.attention_points.map(p => `<li>${esc(p)}</li>`).join("")}</ul>` : ""}
      </div>` : `<div class="card"><span class="muted">Not analyzed yet.</span><div class="btn-row"><button class="btn btn-primary btn-sm" data-d="analyze" ${busy ? "disabled" : ""}>${busy ? '<i class="spin"></i> Analyzing' : "Analyze with Llama"}</button></div></div>`}
      ${a ? `<div class="btn-row"><button class="btn btn-outline btn-sm" data-d="analyze" ${busy ? "disabled" : ""}>${busy ? '<i class="spin"></i> Analyzing' : "Re-analyze"}</button></div>` : ""}
    </div>

    ${a ? `<div class="sec">
      <h4>Checks to complete</h4>
      <div class="prog">${doneN} of ${needed(s).length} done</div>
      ${needed(s).map(c => `<label class="check ${s.checks_done.includes(c) ? "done" : ""}"><input type="checkbox" data-check="${esc(c)}" ${s.checks_done.includes(c) ? "checked" : ""}>
        <div><b>${esc(short(c))}</b><span>${esc(state.rules.checks[c]?.label || c)}</span></div></label>`).join("") || '<div class="muted">No checks flagged.</div>'}
    </div>` : ""}

    <div class="sec">
      <h4>Routing</h4>
      <div class="grid2">
        <div class="fld"><label>Specialty</label><select id="dSpec">
          <option value="">${a ? "Use suggestion: " + esc(a.suggested_specialty || "none") : "Not set"}</option>
          ${specs.map(x => `<option ${s.specialty_override === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div>
        <div class="fld"><label>Assign to</label><select id="dAssign">
          <option value="">Unassigned</option>${checkers.map(x => `<option ${s.assigned_to === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div>
      </div>
      <div class="fld" style="margin-top:12px"><label>Notes</label><textarea id="dNotes" rows="3" placeholder="Notes for yourself or the assignee…">${esc(s.notes)}</textarea></div>
      <div class="btn-row">
        <button class="btn btn-primary btn-sm" data-d="assign">Assign</button>
        <button class="btn btn-outline btn-sm" data-d="done">${s.status === "done" ? "Reopen" : "Mark done"}</button>
        <button class="btn btn-outline btn-sm" data-d="copy">Copy summary</button>
        <div class="spacer"></div>
        <button class="btn btn-danger btn-sm" data-d="delete">Delete</button>
      </div>
    </div>
  </div>`;
}

/* ---------- actions ---------- */
async function patch(id, fields) {
  const sub = await api(`/submissions/${id}`, { method: "PATCH", body: fields });
  replace(sub); return sub;
}
async function analyze(id) {
  if (state.busy.has(id)) return;
  state.busy.add(id); renderAll();
  try { replace(await api(`/submissions/${id}/analyze`, { method: "POST" })); }
  catch (e) { toast(e.message, true); }
  finally { state.busy.delete(id); renderAll(); }
}
async function analyzeAll() {
  const todo = state.subs.filter(s => !s.analysis).map(s => s.id);
  if (!todo.length) return toast("Everything is already analyzed.");
  const p = $("#progress"); p.classList.remove("hidden"); $("#btnAnalyzeAll").disabled = true;
  for (let i = 0; i < todo.length; i++) {
    $("#progressText").textContent = `Analyzing ${i + 1} of ${todo.length}`;
    $("#progressBar").style.width = `${(i / todo.length) * 100}%`;
    await analyze(todo[i]);
  }
  $("#progressBar").style.width = "100%"; $("#progressText").textContent = "Done";
  setTimeout(() => p.classList.add("hidden"), 1200); $("#btnAnalyzeAll").disabled = false;
  toast(`Analyzed ${todo.length} submission${todo.length > 1 ? "s" : ""}.`);
}
function summaryText(s) {
  const a = s.analysis || {};
  const lines = [`${s.external_id || "#" + s.id}: ${s.title}`, `Category: ${CAT[a.category] || "n/a"}${a.study_type ? " (" + a.study_type + ")" : ""}`,
    `Specialty: ${effSpec(s) || "n/a"}`, `Assigned to: ${s.assigned_to || "unassigned"}`,
    `Checks: ${needed(s).map(c => `${s.checks_done.includes(c) ? "[x]" : "[ ]"} ${short(c)}`).join(", ") || "none"}`];
  if (a.attention_points?.length) lines.push("Double-check: " + a.attention_points.join("; "));
  if (s.notes) lines.push("Notes: " + s.notes);
  return lines.join("\n");
}

/* ---------- events ---------- */
document.addEventListener("click", async e => {
  const tab = e.target.closest("[data-tab]");
  if (tab) { state.tab = tab.dataset.tab; return renderAll(); }

  const act = e.target.closest("[data-act]");
  if (act) {
    e.stopPropagation();
    const id = +act.closest("tr").dataset.id;
    return act.dataset.act === "analyze" ? analyze(id) : openDrawer(id);
  }
  const tr = e.target.closest("#rows tr[data-id]");
  if (tr) return openDrawer(+tr.dataset.id);

  const d = e.target.closest("[data-d]");
  if (d) {
    const s = find(state.openId); if (!s) return;
    const k = d.dataset.d;
    try {
      if (k === "close") closeDrawer();
      else if (k === "analyze") await analyze(s.id);
      else if (k === "saveabs") { await patch(s.id, { abstract: $("#dAbs").value }); await analyze(s.id); }
      else if (k === "assign") {
        const who = $("#dAssign").value, spec = $("#dSpec").value;
        await patch(s.id, { assigned_to: who, specialty_override: spec, notes: $("#dNotes").value, status: who ? "assigned" : (s.analysis ? "analyzed" : "new") });
        toast(who ? `Assigned to ${who}.` : "Assignment cleared."); renderAll();
      } else if (k === "done") { await patch(s.id, { status: s.status === "done" ? (s.assigned_to ? "assigned" : "analyzed") : "done", notes: $("#dNotes").value }); renderAll(); }
      else if (k === "copy") { await navigator.clipboard.writeText(summaryText(s)); toast("Summary copied."); }
      else if (k === "delete") {
        if (!confirm("Delete this submission?")) return;
        await api(`/submissions/${s.id}`, { method: "DELETE" });
        state.subs = state.subs.filter(x => x.id !== s.id); closeDrawer(); renderAll();
      }
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (e.target.id === "scrim") closeDrawer();
});

document.addEventListener("change", async e => {
  const s = find(state.openId);
  if (e.target.matches("[data-check]") && s) {
    const k = e.target.dataset.check;
    const done = e.target.checked ? [...new Set([...s.checks_done, k])] : s.checks_done.filter(x => x !== k);
    try { await patch(s.id, { checks_done: done }); renderAll(); } catch (err) { toast(err.message, true); }
  } else if (e.target.id === "dNotes" && s) {
    try { await patch(s.id, { notes: e.target.value }); } catch (err) { toast(err.message, true); }
  }
});

$("#q").addEventListener("input", e => { state.q = e.target.value; renderRows(); });
$("#fCat").addEventListener("change", e => { state.cat = e.target.value; renderRows(); });
$("#fSpec").addEventListener("change", e => { state.spec = e.target.value; renderRows(); });
$("#fCheck").addEventListener("change", e => { state.check = e.target.value; renderRows(); });
$("#btnAnalyzeAll").addEventListener("click", analyzeAll);
document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeDrawer();
  if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); $("#q").focus(); }
});

/* ---------- add dialog ---------- */
const addDlg = $("#addDlg");
const openAdd = () => addDlg.showModal();
$("#btnAdd").addEventListener("click", openAdd);
$("#btnEmptyAdd").addEventListener("click", openAdd);
document.querySelectorAll(".dlg-tabs button").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll(".dlg-tabs button").forEach(x => x.classList.toggle("on", x === b));
  document.querySelectorAll("[data-p]").forEach(p => p.classList.toggle("hidden", p.dataset.p !== b.dataset.t));
}));
async function afterAdd(msg) { addDlg.close(); await refresh(); toast(msg); }
$("#goPaste").addEventListener("click", async () => {
  try { const r = await api("/import/titles", { method: "POST", body: { text: $("#pasteText").value } }); $("#pasteText").value = ""; await afterAdd(`Added ${r.added} submission${r.added === 1 ? "" : "s"}.`); }
  catch (e) { toast(e.message, true); }
});
$("#goCsv").addEventListener("click", async () => {
  const f = $("#csvFile").files[0]; if (!f) return toast("Choose a CSV file first.", true);
  try { const r = await api("/import/csv", { method: "POST", body: { text: await f.text() } }); await afterAdd(`Imported ${r.added} submissions.`); }
  catch (e) { toast(e.message, true); }
});
$("#goOne").addEventListener("click", async () => {
  try {
    const sub = await api("/submissions", { method: "POST", body: { title: $("#oneTitle").value, abstract: $("#oneAbs").value, tags: $("#oneTags").value.split(/[;,]/).map(t => t.trim()).filter(Boolean) } });
    ["#oneTitle", "#oneAbs", "#oneTags"].forEach(i => $(i).value = "");
    await afterAdd("Added. Analyzing…"); analyze(sub.id);
  } catch (e) { toast(e.message, true); }
});
$("#btnDemo").addEventListener("click", async () => {
  try { const r = await api("/demo", { method: "POST" }); await refresh(); toast(`Loaded ${r.added} sample submissions. Try “Analyze all new”.`); }
  catch (e) { toast(e.message, true); }
});
$("#navAbout").addEventListener("click", e => { e.preventDefault(); $("#aboutDlg").showModal(); });

/* ---------- settings dialog ---------- */
const setDlg = $("#setDlg");
$("#btnSettings").addEventListener("click", async () => {
  await loadStatus();
  const models = state.status.models, cur = state.settings.model;
  const opts = models.includes(cur) || !cur ? models : [cur, ...models];
  $("#setModel").innerHTML = opts.length ? opts.map(m => `<option ${m === cur ? "selected" : ""}>${esc(m)}</option>`).join("") : `<option value="">No models found</option>`;
  $("#setModelCustom").value = "";
  $("#modelHint").textContent = state.status.ollama
    ? "Installed models from your local Ollama. Pull more with: ollama pull llama3.1:8b"
    : "Ollama is not reachable. Start it (ollama serve) or the app will use rules only.";
  $("#setCheckers").value = state.settings.checkers.join("\n");
  $("#setRules").value = JSON.stringify(state.rules, null, 2);
  $("#rulesErr").textContent = ""; $("#rulesErr").className = "hint";
  setDlg.showModal();
});
$("#saveSettings").addEventListener("click", async () => {
  let rules;
  try { rules = JSON.parse($("#setRules").value); } catch (e) { $("#rulesErr").textContent = "Rules JSON is invalid: " + e.message; $("#rulesErr").className = "hint err"; return; }
  try {
    state.rules = await api("/rules", { method: "PUT", body: rules });
    state.settings = await api("/settings", { method: "PUT", body: {
      model: $("#setModelCustom").value.trim() || $("#setModel").value,
      checkers: $("#setCheckers").value.split("\n"),
    } });
    setDlg.close(); await loadStatus(); renderAll(); toast("Settings saved. Re-analyze to apply new rules.");
  } catch (e) { $("#rulesErr").textContent = e.message; $("#rulesErr").className = "hint err"; }
});

/* ---------- status + boot ---------- */
async function loadStatus() {
  try { state.status = await api("/status"); state.settings = await api("/settings"); } catch (_) {}
  const pill = $("#statusPill");
  pill.className = "pill-status " + (state.status.ollama ? "ok" : "bad");
  pill.querySelector("span").textContent = state.status.ollama ? `Llama ready · ${state.settings.model}` : "Ollama offline · rules only";
}
(async function boot() {
  try {
    state.rules = await api("/rules");
    await loadStatus();
    await refresh();
  } catch (e) { toast("Could not reach the server: " + e.message, true); }
  setInterval(loadStatus, 20000);
})();
