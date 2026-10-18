"""Self-contained visual inspection of development predictions; never runs inference."""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

from .datasets import load_dataset
from .experiment import fingerprint
from .schemas import Box


STYLE = """
:root{color-scheme:dark;--bg:#0c1317;--panel:#131e23;--line:#293a41;--text:#e9f0ef;
--muted:#a5b8bd;--mint:#9ef1cb;--amber:#ffd18c}*{box-sizing:border-box}body{margin:0;
background:var(--bg);color:var(--text);font:15px/1.6 'Segoe UI',system-ui,sans-serif}
a{color:var(--mint)}button,select,input{font:inherit}header{border-bottom:1px solid var(--line);
padding:19px 4vw;display:flex;justify-content:space-between;align-items:center;gap:20px}
.brand{letter-spacing:.22em;font-size:17px;font-weight:750}.brand small{font-weight:400;
letter-spacing:.04em;color:var(--muted);padding-left:22px;font-size:12px}
main{max-width:1320px;margin:auto;padding:36px 4vw 60px}.eyebrow{font-size:12px;
letter-spacing:.15em;text-transform:uppercase;color:var(--mint)}h1{font-size:clamp(29px,4vw,46px);
letter-spacing:-.04em;font-weight:600;line-height:1.16;margin:10px 0 16px}p{margin:8px 0}
.lede{max-width:760px;color:var(--muted)}.badge{border:1px solid #4a584c;border-radius:6px;
padding:5px 11px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--amber)}
.notice{background:#22261e;border:1px solid #485140;border-radius:10px;padding:16px 20px;
margin:26px 0;color:#dce5ce}.notice p{color:#b8c2ad;font-size:13px}.notice ul{padding-left:20px;
font-size:13px;margin:10px 0}.controls{display:flex;flex-wrap:wrap;gap:20px;align-items:center;
justify-content:space-between;margin:28px 0 18px}select{background:var(--panel);color:var(--text);
border:1px solid var(--line);border-radius:7px;padding:9px 12px;max-width:100%}
.toggles{display:flex;gap:20px;flex-wrap:wrap;font-size:13px}.toggles label{cursor:pointer}
input{accent-color:var(--mint);margin-right:6px}.proposal-key{color:var(--amber)}.truth-key{color:var(--mint)}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0 26px}
.metric{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px 20px}
.metric b{display:block;font-size:30px;font-weight:550;letter-spacing:-.03em}.metric span{font-size:12px;
color:var(--muted)}.section-title{display:flex;justify-content:space-between;align-items:baseline;gap:15px}
h2{font-size:20px;font-weight:550;margin:18px 0}.section-title span,.muted{font-size:12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.card{overflow:hidden;
border:1px solid var(--line);border-radius:10px;background:var(--panel)}.card-head{padding:14px 18px;
display:flex;justify-content:space-between;gap:10px;font-size:13px}.condition{color:var(--muted)}
.scene{display:block;width:100%;height:auto;background:#1d292e}.scene text{font:14px 'Segoe UI',sans-serif;
paint-order:stroke;stroke:#101719;stroke-width:4px;stroke-linejoin:round}.predicted{color:var(--amber)}
.reference{color:var(--mint)}.scene rect{vector-effect:non-scaling-stroke;fill:none;stroke:currentColor;
stroke-width:2}.predicted rect{stroke-dasharray:7 4}.scene text{fill:currentColor}
.card-foot{padding:14px 18px;font-size:12px}.stats{display:flex;gap:18px;flex-wrap:wrap}
.error{color:var(--amber);margin-top:8px}.hide-predictions .predicted{display:none}
.hide-reference .reference{display:none}[hidden]{display:none!important}
.table-wrap{overflow:auto;margin:26px 0}table{border-collapse:collapse;width:100%;text-align:left;font-size:13px}
td,th{padding:11px 14px;border-bottom:1px solid var(--line)}th{font-weight:500;color:var(--muted)}
footer{padding-top:30px;margin-top:32px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
code{overflow-wrap:anywhere}.gate-detail{font-size:12px;color:var(--muted)}
@media(max-width:800px){header{padding:16px 5vw}.brand small{display:none}main{padding:25px 5vw}
.metrics{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.metric{padding:13px}
.metric b{font-size:25px}.controls{align-items:stretch;flex-direction:column}.section-title{display:block}}
@media print{body{background:white;color:black}.controls{display:none}.card,.notice,.metric{break-inside:avoid}
section[hidden]{display:block!important}}
"""

SCRIPT = """
const selector = document.getElementById('model');
selector.addEventListener('change', () => {
  document.querySelectorAll('.candidate').forEach((panel, i) => { panel.hidden = i !== Number(selector.value); });
});
document.getElementById('proposals').addEventListener('change', (event) => {
  document.body.classList.toggle('hide-predictions', !event.target.checked);
});
document.getElementById('references').addEventListener('change', (event) => {
  document.body.classList.toggle('hide-reference', !event.target.checked);
});
"""


def overlay(boxes: list[Box], group: str, image_width: int, image_height: int) -> str:
    result = [f'<g class="{group}">']
    for box in boxes:
        x1, y1, x2, y2 = box.bbox
        # Label anchors stay inside the viewBox even for boxes touching an edge.
        x = min(x1 + 4, max(0, image_width - len(box.label) * 9))
        y = max(18, min(image_height - 5, y1 - 7 if group == "reference" else y2 + 18))
        result.append(f'<rect x="{x1:g}" y="{y1:g}" width="{x2-x1:g}" height="{y2-y1:g}"/>'
                      f'<text x="{x:g}" y="{y:g}">{escape(box.label)}</text>')
    return "".join(result) + "</g>"


def visual_report(manifest: Path, report: dict) -> str:
    dataset, images = load_dataset(manifest)
    if report["dataset_fingerprint"] != fingerprint(dataset, images):
        raise ValueError("Report and dataset contents do not match; use the original dataset snapshot")
    samples = [s for s in dataset.samples if s.split == "development"]
    fixture = report["evidence_kind"] != "live_nebius" or dataset.kind != "real_photographs"
    badge = "Scripted offline example" if fixture else "Saved live experiment"
    reason_items = "".join(f'<li>{escape(r)}</li>' for r in report["gate"]["reasons"])
    options, panels = [], []
    for index, candidate in enumerate(report["models"]):
        options.append(f'<option value="{index}">{escape(candidate["model"])}</option>')
        overall = candidate["metrics"]["overall"]
        metrics = [(f'{overall["precision"]:.0%}', "Precision · IoU ≥ 0.5"),
                   (f'{overall["recall"]:.0%}', "Recall · IoU ≥ 0.5"),
                   (f'{overall["f1"]:.3f}', "Detection F1"),
                   (f'{candidate["completed_images"]}/{len(samples)}', "Images with valid proposals")]
        metric_html = "".join(f'<div class="metric"><b>{value}</b><span>{label}</span></div>'
                              for value, label in metrics)
        per_image = {r["sample_id"]: r for r in candidate["metrics"]["per_image"]}
        outcomes = {r["sample_id"]: r for r in candidate["images"]}
        cards = []
        for sample in samples:
            image = images[sample.id]
            boxes = [Box.model_validate(b) for b in candidate["predictions"].get(sample.id, [])]
            for box in boxes:
                box.validate_frame(image.width, image.height, dataset.classes)
            outcome = outcomes.get(sample.id, {"status": "not attempted", "attempts": 0, "latency_seconds": 0})
            counts = per_image[sample.id]
            error = f'<div class="error">{escape(outcome["error"])}</div>' if outcome.get("error") else ""
            cached = " · cached" if outcome.get("cached") else ""
            encoded = base64.b64encode(image.png).decode("ascii")
            cards.append(f'''<article class="card"><div class="card-head"><strong>{escape(sample.id)}</strong>
<span class="condition">{escape(sample.condition)} · {image.width} × {image.height}</span></div>
<svg class="scene" role="img" aria-label="{escape(sample.id)} annotation comparison" viewBox="0 0 {image.width} {image.height}">
<image width="{image.width}" height="{image.height}" href="data:image/png;base64,{encoded}"/>
{overlay(sample.objects, "reference", image.width, image.height)}{overlay(boxes, "predicted", image.width, image.height)}</svg>
<div class="card-foot"><div class="stats"><span>{counts['tp']} matched</span>
<span>{counts['fn']} missed</span><span>{counts['fp']} extra</span></div>
<div class="muted">{escape(outcome['status'])}{cached} · {outcome['attempts']} attempts · {outcome['latency_seconds']:.2f}s recorded wait</div>
{error}</div></article>''')
        rows = "".join(f'<tr><td>{escape(condition)}</td><td>{m["precision"]:.0%}</td>'
                       f'<td>{m["recall"]:.0%}</td><td>{m["f1"]:.3f}</td><td>{m["fn"]}</td></tr>'
                       for condition, m in candidate["metrics"]["by_condition"].items())
        panels.append(f'''<section class="candidate" {'hidden' if index else ''}>
<div class="metrics">{metric_html}</div>
<div class="section-title"><h2>Inspect the proposals</h2><span>{len(samples)} development images · original coordinates</span></div>
<div class="grid">{''.join(cards)}</div><div class="table-wrap"><table>
<thead><tr><th>Condition</th><th>Precision</th><th>Recall</th><th>F1</th><th>Missed objects</th></tr></thead>
<tbody>{rows}</tbody></table></div><p class="gate-detail">Recorded cost for this run: ${candidate['accounted_usd']:.6f}.
Cost used to compare models, including cached originals: ${candidate['comparison_cost_usd']:.6f}.</p></section>''')
    notice = ("No model was called. Shapes and predictions are software fixtures; these scores are not model evidence."
              if fixture else "Saved predictions from a development experiment. These are proposals, not reviewed labels or held-out results.")
    gate = "passed" if report["gate"]["status"] == "passed" else "not passed"
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Skylark — experiment review</title><style>{STYLE}</style></head><body>
<header><div class="brand">SKYLARK <small>ROBOT VISION / EXPERIMENT REVIEW</small></div><span class="badge">{badge}</span></header>
<main><div class="eyebrow">Evidence before automation</div><h1>See what the model misses.</h1>
<p class="lede">Compare proposed boxes with manual reference labels. Inspect difficult scenes before choosing a model for the labeling workflow.</p>
<aside class="notice"><strong>{badge}</strong><p>{notice}</p><p>Development gate: <strong>{gate}</strong> · Run: {escape(report['state'])}</p>
<details><summary>Gate requirements</summary><ul>{reason_items or '<li>Development criteria met. Inspect image-level errors before continuing.</li>'}</ul></details></aside>
<div class="controls"><label>Candidate <select id="model" aria-label="Model candidate">{''.join(options)}</select></label>
<div class="toggles"><label class="proposal-key"><input id="proposals" type="checkbox" checked>Proposed boxes · dashed</label>
<label class="truth-key"><input id="references" type="checkbox" checked>Reference boxes · solid</label></div></div>
{''.join(panels)}<footer><p>Dataset: {escape(dataset.name)} · Development only · IoU threshold 0.5</p>
<p>Local ledger: ${report['budget']['accounted_usd']:.6f} accounted · ${report['budget']['uncertain_or_reserved_usd']:.6f} unconfirmed/reserved.</p>
<p>Run <code>{escape(report['run_id'])}</code> · {escape(report['started_at'])}</p>
<p>Snapshot report. Model prices and token usage require provider reconciliation. This page sends no network requests and cannot start inference.</p>
</footer></main><script>{SCRIPT}</script></body></html>'''
