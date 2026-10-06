"""Markdown and self-contained HTML renderings of a :class:`~sealgrade.matrix.MatrixResult`."""

from __future__ import annotations

from jinja2 import Environment, select_autoescape

from sealgrade.matrix import MatrixResult
from sealgrade.runner import TIER_LABELS

_SYMBOL = {"exploit": "EXPLOIT", "blocked": "blocked", "partial": "PARTIAL", None: "-"}


def render_markdown(result: MatrixResult) -> str:
    """A GitHub-flavoured table: one row per attack, one column per tier."""
    header = ["Attack", "Classes", *[TIER_LABELS.get(t, t) for t in result.tiers]]
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for attack in result.attacks:
        row = [f"`{attack.id}`", ", ".join(attack.classes)]
        for tier in result.tiers:
            observed = result.observed(attack.id, tier)
            expected = attack.expected.for_tier(tier)
            mark = "" if expected is None or expected == observed else " (!)"
            row.append(_SYMBOL[observed] + mark)
        lines.append("| " + " | ".join(row) + " |")
    totals = ["**Exploits that worked**", ""]
    for tier in result.tiers:
        exploited, measured = result.exploit_counts()[tier]
        totals.append(f"**{exploited} / {measured}**")
    lines.append("| " + " | ".join(totals) + " |")
    latency = result.mean_latency()
    if latency:
        cells = ["Mean seconds per grading run", ""] + [
            f"{latency.get(t, 0):.1f}" for t in result.tiers
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    controls_ok = sum(1 for c in result.controls if c.ok)
    lines.append(
        f"Controls (oracle passes, do-nothing and near-miss fail): "
        f"{controls_ok} / {len(result.controls)} ok."
    )
    if result.mismatches():
        lines.append("")
        lines.append("Mismatches between claim and measurement:")
        for attack_id, tier, want, got in result.mismatches():
            lines.append(f"- `{attack_id}` on {tier}: expected {want}, observed {got}")
    return "\n".join(lines) + "\n"


_HTML = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SealGrade proof matrix</title>
<style>
  :root { --bg:#0b0f14; --panel:#111820; --line:#1f2a35; --text:#d6e2ee; --muted:#7d8fa0;
          --bad:#ff7b72; --good:#3ddc97; --warn:#ffb454; }
  * { box-sizing: border-box; }
  body { margin:0; padding:32px 20px; background:var(--bg); color:var(--text);
         font:15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 1000px; margin: 0 auto; }
  h1 { font: 700 1.5rem ui-monospace, Consolas, monospace; margin: 0 0 4px; }
  p.sub { color: var(--muted); margin: 0 0 24px; }
  table { width:100%; border-collapse: collapse; background: var(--panel);
          border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  th, td { padding: 10px 14px; text-align:left; border-bottom:1px solid var(--line); }
  th { font: 600 .78rem ui-monospace, Consolas, monospace; color: var(--muted);
       text-transform: uppercase; letter-spacing:.06em; background:#0e141b; }
  td.id { font-family: ui-monospace, Consolas, monospace; font-size:.9rem; }
  td.cls { color: var(--muted); font-size:.85rem; }
  td.cell { font: 700 .8rem ui-monospace, Consolas, monospace; text-align:center; }
  .exploit { background: rgba(255,123,114,.16); color: var(--bad); }
  .blocked { background: rgba(61,220,151,.14); color: var(--good); }
  .partial { background: rgba(255,180,84,.16); color: var(--warn); }
  .na { color: var(--muted); }
  tr.total td { font-weight: 700; background:#0e141b; }
  .flag { color: var(--warn); margin-left: 6px; }
  .foot { margin-top: 18px; color: var(--muted); font-size:.9rem; }
  .bad { color: var(--bad); }
</style>
</head>
<body>
<main>
  <h1>SealGrade proof matrix</h1>
  <p class="sub">Each attack is a submission that does <b>not</b> solve the task. If the verdict says pass, the exploit worked.</p>
  <table>
    <thead><tr><th>Attack</th><th>Classes</th>{% for t in tiers %}<th>{{ labels.get(t, t) }}</th>{% endfor %}</tr></thead>
    <tbody>
    {% for row in rows %}
      <tr>
        <td class="id">{{ row.id }}</td>
        <td class="cls">{{ row.classes }}</td>
        {% for c in row.cells %}
          <td class="cell {{ c.css }}">{{ c.text }}{% if c.flag %}<span class="flag" title="differs from the documented expectation">(!)</span>{% endif %}</td>
        {% endfor %}
      </tr>
    {% endfor %}
      <tr class="total"><td>Exploits that worked</td><td></td>
        {% for t in tiers %}<td class="cell">{{ totals[t][0] }} / {{ totals[t][1] }}</td>{% endfor %}
      </tr>
      <tr class="total"><td>Mean seconds per grading run</td><td></td>
        {% for t in tiers %}<td class="cell">{{ latency.get(t, 0) }}</td>{% endfor %}
      </tr>
    </tbody>
  </table>
  <p class="foot">Controls (oracle passes, do-nothing and near-miss fail): {{ controls_ok }} / {{ controls_total }} ok.
  {% if mismatches %}<span class="bad">{{ mismatches|length }} mismatch(es) between claim and measurement.</span>{% endif %}</p>
</main>
</body>
</html>
"""


def render_html(result: MatrixResult) -> str:
    """A single self-contained HTML page with the attack x tier heat map."""
    env = Environment(autoescape=select_autoescape(default=True))
    template = env.from_string(_HTML)
    rows = []
    for attack in result.attacks:
        cells = []
        for tier in result.tiers:
            observed = result.observed(attack.id, tier)
            expected = attack.expected.for_tier(tier)
            cells.append(
                {
                    "text": _SYMBOL[observed],
                    "css": observed or "na",
                    "flag": expected is not None and expected != observed,
                }
            )
        rows.append({"id": attack.id, "classes": ", ".join(attack.classes), "cells": cells})
    return template.render(
        tiers=result.tiers,
        labels=TIER_LABELS,
        rows=rows,
        totals=result.exploit_counts(),
        latency=result.mean_latency(),
        controls_ok=sum(1 for c in result.controls if c.ok),
        controls_total=len(result.controls),
        mismatches=result.mismatches(),
    )
