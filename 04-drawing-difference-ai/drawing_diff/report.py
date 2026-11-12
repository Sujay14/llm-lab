"""Write report.html (self-contained), changes.json and changes.csv."""
from __future__ import annotations

import base64
import csv
import html
import json
import os

SEV_COLOR = {"high": "#c62828", "medium": "#ef6c00", "low": "#546e7a"}


def _data_uri(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    with open(path, "rb") as f:
        return f"data:image/{mime};base64," + base64.b64encode(f.read()).decode()


def build_html(result, out_dir):
    e = html.escape
    m, st = result["meta"], result["stats"]
    parts = [f"""<!doctype html><html><head><meta charset="utf-8"><title>Comparison report</title>
<style>
body{{font-family:system-ui,Arial,sans-serif;margin:24px auto;max-width:1200px;color:#222;padding:0 16px}}
h1{{margin-bottom:4px}} .muted{{color:#666;font-size:13px}}
.card{{border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin:12px 0;background:#fafafa}}
.badge{{color:#fff;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid #e3e3e3;padding:6px 8px;text-align:left;vertical-align:top;font-size:14px}}
img{{max-width:100%;border:1px solid #ccc;margin-top:6px}} .warn{{background:#fff8e1;border-color:#ffe082}}
code{{background:#eee;padding:1px 4px;border-radius:3px}}
</style></head><body>
<h1>Document comparison report</h1>
<div class="muted">A: <b>{e(m['file_a'])}</b> &nbsp;|&nbsp; B: <b>{e(m['file_b'])}</b> &nbsp;|&nbsp; domain: {e(m['domain'])}
 &nbsp;|&nbsp; LLM: {e(m['llm'])} &nbsp;|&nbsp; {m['sheets_compared']} sheet(s) &nbsp;|&nbsp; {m['seconds']}s</div>"""]
    if m.get("disclaimer"):
        parts.append(f'<div class="card warn"><b>Note:</b> {e(m["disclaimer"])}</div>')
    sev = st["by_severity"]
    parts.append(f'<div class="card"><h2>Summary</h2><p>{e(result["summary"])}</p><p>'
                 + " ".join(f'<span class="badge" style="background:{SEV_COLOR[k]}">{k}: {sev.get(k, 0)}</span>'
                            for k in ("high", "medium", "low")) + f' &nbsp; total: <b>{st["total"]}</b></p></div>')
    for p in result["pages"]:
        chs = [c for c in result["changes"] if c["page"] == p["label"]]
        parts.append(f'<h2>Sheet {e(str(p["label"]))} <span class="muted">({len(chs)} change(s), alignment: {e(p["align"])})</span></h2>')
        if p["entity_summary"]:
            parts.append('<div class="card"><b>Entity-level differences</b><ul>'
                         + "".join(f"<li>{e(s)}</li>" for s in p["entity_summary"]) + "</ul></div>")
        if p.get("overlay"):
            parts.append(f'<details><summary>Overlay (<span style="color:#c00">red = only in A</span>, '
                         f'<span style="color:#080">green = only in B</span>)</summary>'
                         f'<img src="{_data_uri(os.path.join(out_dir, p["overlay"]))}"></details>')
        if chs:
            parts.append("<table><tr><th>ID</th><th>Severity</th><th>Type</th><th>Description</th><th>Old &rarr; New</th><th>Conf.</th></tr>")
            for c in chs:
                img = (f'<br><img src="{_data_uri(os.path.join(out_dir, c["image"]))}">' if c.get("image") else "")
                on = f'{e(c["old"] or "-")} &rarr; {e(c["new"] or "-")}'
                parts.append(f'<tr><td>{c["id"]}</td><td><span class="badge" style="background:{SEV_COLOR[c["severity"]]}">{c["severity"]}</span></td>'
                             f'<td>{e(c["change_type"])}<br><span class="muted">{c["source"]}{" + LLM" if c.get("llm_used") else ""}</span></td>'
                             f'<td>{e(c["description"])}{img}</td><td>{on}</td><td>{c["confidence"]:.2f}</td></tr>')
            parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


def write_outputs(result, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    paths = dict(html=os.path.join(out_dir, "report.html"),
                 json=os.path.join(out_dir, "changes.json"),
                 csv=os.path.join(out_dir, "changes.csv"))
    with open(paths["html"], "w", encoding="utf-8") as f:
        f.write(build_html(result, out_dir))
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    with open(paths["csv"], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "page", "source", "change_type", "severity", "confidence", "description", "old", "new"])
        for c in result["changes"]:
            w.writerow([c["id"], c["page"], c["source"], c["change_type"], c["severity"],
                        f'{c["confidence"]:.2f}', c["description"], c.get("old") or "", c.get("new") or ""])
    return paths
