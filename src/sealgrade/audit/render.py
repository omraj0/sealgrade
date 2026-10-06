"""JSON and self-contained HTML renderings of audit reports."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from jinja2 import Environment, select_autoescape

from sealgrade.audit.model import AuditReport, Severity


def to_dict(reports: Iterable[AuditReport]) -> dict[str, Any]:
    items = list(reports)
    counts = {s.label: 0 for s in Severity}
    for report in items:
        for finding in report.findings:
            counts[finding.severity.label] += 1
    return {
        "tasks": [
            {
                "task": r.target,
                "kind": r.kind,
                "findings": [f.as_dict() for f in r.findings],
                "mutation": r.mutation,
            }
            for r in items
        ],
        "summary": {"tasks": len(items), "findings_by_severity": counts},
    }


def to_json(reports: Iterable[AuditReport]) -> str:
    return json.dumps(to_dict(reports), indent=2)


_HTML = """\
<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SealGrade audit</title>
<style>
  :root { --bg:#0b0f14; --panel:#111820; --line:#1f2a35; --text:#d6e2ee; --muted:#7d8fa0;
          --high:#ff7b72; --medium:#ffb454; --low:#4cc9f0; --info:#7d8fa0; --good:#3ddc97; }
  * { box-sizing: border-box; }
  body { margin:0; padding:32px 20px; background:var(--bg); color:var(--text);
         font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }
  main { max-width: 1000px; margin: 0 auto; }
  h1 { font: 700 1.5rem ui-monospace,Consolas,monospace; margin:0 0 6px; }
  h2 { font: 700 1.1rem ui-monospace,Consolas,monospace; margin:30px 0 10px; }
  p.sub { color:var(--muted); margin:0 0 20px; }
  .counts { display:flex; gap:10px; flex-wrap:wrap; margin-bottom: 8px; }
  .pill { padding:4px 12px; border-radius:999px; border:1px solid var(--line); background:var(--panel);
          font:600 .8rem ui-monospace,Consolas,monospace; }
  .high { color:var(--high); } .medium { color:var(--medium); } .low { color:var(--low); }
  .info { color:var(--info); }
  table { width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line);
          border-radius:10px; overflow:hidden; }
  th, td { padding:9px 12px; text-align:left; vertical-align:top; border-bottom:1px solid var(--line); }
  th { font:600 .75rem ui-monospace,Consolas,monospace; text-transform:uppercase; letter-spacing:.06em;
       color:var(--muted); background:#0e141b; }
  td.sev { font:700 .78rem ui-monospace,Consolas,monospace; text-transform:uppercase; white-space:nowrap; }
  td.rule { font:600 .85rem ui-monospace,Consolas,monospace; white-space:nowrap; }
  td.where { font:.8rem ui-monospace,Consolas,monospace; color:var(--muted); }
  .detail { color:var(--muted); font-size:.9rem; }
  .clean { color:var(--good); font-weight:600; }
  pre { background:#0e141b; border:1px solid var(--line); border-radius:8px; padding:10px 12px;
        overflow:auto; font:.8rem ui-monospace,Consolas,monospace; }
</style></head>
<body><main>
  <h1>SealGrade audit</h1>
  <p class="sub">Static checks for the reward-hacking flaw classes V1 to V8. Heuristics, not proofs.</p>
  <div class="counts">
    {% for label, n in summary.items() %}<span class="pill {{ label }}">{{ label }}: {{ n }}</span>{% endfor %}
  </div>
  {% for task in tasks %}
  <h2>{{ task.task }} <span class="detail">({{ task.kind }})</span></h2>
  {% if task.findings %}
  <table>
    <thead><tr><th>Severity</th><th>Rule</th><th>Finding</th><th>Where</th></tr></thead>
    <tbody>
    {% for f in task.findings %}
      <tr>
        <td class="sev {{ f.severity }}">{{ f.severity }}</td>
        <td class="rule">{{ f.rule }}</td>
        <td><b>{{ f.title }}</b><div class="detail">{{ f.detail }}</div></td>
        <td class="where">{{ f.path }}{% if f.line %}:{{ f.line }}{% endif %}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}<p class="clean">No findings.</p>{% endif %}
  {% if task.mutation %}
  <p class="detail">Mutation score: <b>{{ (task.mutation.score * 100) | round(1) }}%</b>
    ({{ task.mutation.killed }} killed, {{ task.mutation.survived }} survived,
    {{ task.mutation.invalid }} invalid of {{ task.mutation.mutants }} mutants).</p>
  {% for s in task.mutation.survivors[:5] %}<pre>{{ s.operator }} (line {{ s.line }})
{{ s.diff }}</pre>{% endfor %}
  {% endif %}
  {% endfor %}
</main></body></html>
"""


def to_html(reports: Iterable[AuditReport]) -> str:
    data = to_dict(reports)
    env = Environment(autoescape=select_autoescape(default=True))
    return env.from_string(_HTML).render(
        tasks=data["tasks"], summary=data["summary"]["findings_by_severity"]
    )
