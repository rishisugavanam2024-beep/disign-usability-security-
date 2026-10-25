"""Portable report rendering without a web-server dependency."""
import json
from html import escape


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)


def render_html(report: dict) -> str:
    coverage = report["coverage"]
    rows = "".join(
        "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in (
            item["grant"]["description"], item["classification"],
            ", ".join(item["failed_workflows"]) or "None",
            item["reason"],
        )) + "</tr>"
        for item in report["experiments"]
    )
    plans = "".join(f"<li>{escape(plan['recommendation'])}</li>" for plan in report["sequence_plans"])
    # Escape all report content, including application-supplied names and outputs.
    evidence = escape(render_json(report))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SafeRevoke permission-removal report</title>
<style>body{{font:16px/1.5 system-ui;margin:32px;max-width:1100px;color:#17202a}}
table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:10px;border:1px solid #bbb}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.table-wrap{{overflow-x:auto}}</style>
<h1>SafeRevoke permission-removal report</h1>
<p>{escape(coverage['scope'])}</p>
<p>Grants exercised in the baseline: {len(coverage['baseline_exercised_grants'])}/{coverage['configured_grants']}.
Workflows executed: {len(coverage['executed_workflows'])}.</p>
<p>Unexercised grants: {escape(', '.join(coverage['baseline_unexercised_grants']) or 'None')}.</p>
<div class="table-wrap"><table><thead><tr><th>Permission</th><th>Classification</th><th>Failed tasks</th><th>Reason</th></tr></thead>
<tbody>{rows}</tbody></table></div><h2>Removal recommendations</h2><ul>{plans}</ul>
<details><summary>Full execution evidence and coverage</summary><pre>{evidence}</pre></details></html>"""
