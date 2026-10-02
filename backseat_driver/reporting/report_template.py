"""HTML/CSS/JS for the report page. `__REPORT_DATA__` is replaced with the report JSON."""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Backseat Driver Report</title>
<style>
  :root {
    --bg: #f6f7f9; --card: #fff; --text: #1b1f24; --muted: #66707c; --border: #dde1e6;
    --accent: #2f6fed; --match: #cfeedd; --good: #1f9d57; --mid: #d99a00; --bad: #d64545;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14171b; --card: #1d2228; --text: #e6e9ed; --muted: #98a2ae; --border: #2e353d;
      --accent: #6c9bff; --match: #1f5237; --good: #4cc786; --mid: #e6b73a; --bad: #ef7676;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 system-ui, sans-serif; }
  header { padding: 20px 24px 0; }
  h1 { margin: 0 0 4px; font-size: 22px; }
  h2 { margin: 0 0 12px; font-size: 16px; }
  .sub { color: var(--muted); margin: 0; }
  main { padding: 16px 24px 48px; display: grid; gap: 20px; max-width: 1200px; margin: 0 auto; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
  .filters { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; }
  label { color: var(--muted); font-size: 13px; }
  select, input[type=search] {
    font: inherit; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--bg); color: var(--text); min-width: 180px;
  }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chips label { display: inline-flex; gap: 6px; align-items: center; color: var(--text); }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { color: var(--muted); font-weight: 600; font-size: 13px; }
  .bar { display: inline-block; height: 8px; border-radius: 4px; background: var(--accent); vertical-align: middle; margin-right: 8px; }
  .scene { display: grid; grid-template-columns: minmax(220px, 340px) 1fr; gap: 16px; }
  .scene img { width: 100%; border-radius: 8px; display: block; }
  .scene h3 { margin: 0 0 4px; font-size: 16px; }
  .ref { color: var(--muted); margin: 0 0 12px; }
  .entry { border-top: 1px solid var(--border); padding: 10px 0; }
  .entry:first-of-type { border-top: 0; }
  .entry-head { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: baseline; margin-bottom: 4px; }
  .model { font-weight: 600; }
  .metric { font-size: 13px; color: var(--muted); }
  .f1 { font-weight: 700; }
  mark { background: var(--match); color: inherit; border-radius: 3px; padding: 0 1px; }
  .empty { color: var(--muted); text-align: center; padding: 32px; }
  .note { font-size: 13px; color: var(--muted); margin: 12px 0 0; }
  @media (max-width: 700px) { .scene { grid-template-columns: 1fr; } main, header { padding-left: 16px; padding-right: 16px; } }
</style>
</head>
<body>
<header>
  <h1>Backseat Driver — model comparison</h1>
  <p class="sub" id="subtitle"></p>
</header>
<main>
  <section class="card filters">
    <div><label for="scene">Scene</label><br><select id="scene"></select></div>
    <div><label for="search">Search descriptions</label><br><input id="search" type="search" placeholder="e.g. pedestrian"></div>
    <div><label>Models</label><div class="chips" id="models"></div></div>
  </section>
  <section class="card">
    <h2>Metrics by model <span class="sub" id="metrics-scope"></span></h2>
    <div class="table-wrap"><table id="summary"></table></div>
    <p class="note">Scored against the nuScenes scene label by content-word overlap (stopwords removed, plurals folded).
      <b>Precision</b>: share of the model's words found in the label. <b>Recall</b>: share of the label's words the model mentioned.
      Synonyms don't match, and verbose models are naturally low on precision — compare models with it in mind.</p>
  </section>
  <div id="scenes"></div>
</main>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
const report = JSON.parse(document.getElementById("report-data").textContent);
const el = id => document.getElementById(id);
const enabled = new Set(report.models.map(m => m.model_name));
const pct = v => v == null ? "–" : (v * 100).toFixed(1) + "%";
const tone = v => v == null ? "" : v >= 0.5 ? "var(--good)" : v >= 0.25 ? "var(--mid)" : "var(--bad)";

function node(tag, props = {}, ...children) {
  const n = Object.assign(document.createElement(tag), props);
  n.append(...children);
  return n;
}

el("subtitle").textContent = `${report.scenes.length} scenes · ${report.models.length} model(s)`;

const sceneSelect = el("scene");
sceneSelect.append(node("option", { value: "", textContent: "All scenes" }));
for (const s of report.scenes) sceneSelect.append(node("option", { value: s.scene_token, textContent: s.scene_name }));

for (const m of report.models) {
  const box = node("input", { type: "checkbox", checked: true });
  box.addEventListener("change", () => { box.checked ? enabled.add(m.model_name) : enabled.delete(m.model_name); render(); });
  el("models").append(node("label", {}, box, m.model_name));
}
sceneSelect.addEventListener("change", render);
el("search").addEventListener("input", render);

function visibleScenes() {
  const token = sceneSelect.value, q = el("search").value.trim().toLowerCase();
  return report.scenes
    .filter(s => !token || s.scene_token === token)
    .map(s => ({ ...s, entries: s.entries.filter(e => enabled.has(e.model_name) && (!q || e.description.toLowerCase().includes(q))) }))
    .filter(s => s.entries.length);
}

// Metrics are recomputed from the visible scenes so the table follows the scene filter.
function summarise(scenes) {
  return report.models.filter(m => enabled.has(m.model_name)).map(m => {
    const entries = scenes.flatMap(s => s.entries).filter(e => e.model_name === m.model_name);
    const scored = entries.filter(e => e.score);
    const mean = k => scored.length ? scored.reduce((a, e) => a + e.score[k], 0) / scored.length : null;
    const words = entries.length ? entries.reduce((a, e) => a + e.description.split(/\s+/).length, 0) / entries.length : 0;
    return { name: m.model_name, n: entries.length, scored: scored.length, p: mean("precision"), r: mean("recall"), f1: mean("f1"), words };
  });
}

function renderSummary(scenes) {
  const t = el("summary"); t.replaceChildren();
  const head = node("tr", {}, ...["Model", "Scenes", "Precision", "Recall", "F1", "Avg words"].map(h => node("th", { textContent: h })));
  t.append(head);
  const rows = summarise(scenes).sort((a, b) => (b.f1 ?? -1) - (a.f1 ?? -1));
  for (const r of rows) {
    const f1Cell = node("td", {}, node("span", { className: "bar", style: `width:${Math.round((r.f1 ?? 0) * 100)}px;background:${tone(r.f1)}` }), pct(r.f1));
    t.append(node("tr", {}, node("td", { textContent: r.name }), node("td", { textContent: `${r.scored}/${r.n} scored` }),
      node("td", { textContent: pct(r.p) }), node("td", { textContent: pct(r.r) }), f1Cell, node("td", { textContent: r.words.toFixed(1) })));
  }
  el("metrics-scope").textContent = sceneSelect.value ? "· selected scene" : "· all visible scenes";
}

function renderEntry(e) {
  const text = node("div", {});
  for (const seg of e.segments) text.append(seg.matched ? node("mark", { textContent: seg.text }) : document.createTextNode(seg.text));
  const head = node("div", { className: "entry-head" }, node("span", { className: "model", textContent: e.model_name }));
  if (e.score) {
    head.append(
      node("span", { className: "metric f1", style: `color:${tone(e.score.f1)}`, textContent: `F1 ${pct(e.score.f1)}` }),
      node("span", { className: "metric", textContent: `P ${pct(e.score.precision)} · R ${pct(e.score.recall)} · ${e.score.word_count} words` }));
  } else {
    head.append(node("span", { className: "metric", textContent: `no reference label · ${e.description.split(/\s+/).length} words` }));
  }
  return node("div", { className: "entry" }, head, text);
}

function render() {
  const scenes = visibleScenes();
  renderSummary(scenes);
  const root = el("scenes"); root.replaceChildren();
  if (!scenes.length) { root.append(node("div", { className: "card empty", textContent: "No descriptions match the current filters." })); return; }
  for (const s of scenes) {
    const body = node("div", {}, node("h3", { textContent: s.scene_name }),
      node("p", { className: "ref", textContent: s.reference ? `Reference: ${s.reference}` : "No reference label" }),
      ...s.entries.map(renderEntry));
    root.append(node("section", { className: "card scene" }, node("img", { src: s.image, alt: `Keyframe of ${s.scene_name}`, loading: "lazy" }), body));
    root.lastChild.style.marginBottom = "20px";
  }
}
render();
</script>
</body>
</html>
"""
