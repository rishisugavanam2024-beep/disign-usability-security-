import os

from flask import Flask, Response, jsonify, render_template

from saferevoke.benchmark import run_comparative_benchmark
from saferevoke.engine import SafeRevokeEngine
from saferevoke.lab import build_lab
from saferevoke.config import load_lab
from saferevoke.shared_example import RUNNERS
from saferevoke.report import render_html, render_json


app = Flask(__name__)
config_path = os.environ.get("SAFEREVOKE_CONFIG")
engine = SafeRevokeEngine(load_lab(config_path, RUNNERS) if config_path else build_lab())


@app.get("/api/report/<report_format>")
def download_report(report_format: str):
    if report_format not in {"html", "json"}:
        return jsonify({"error": "Choose html or json"}), 400
    report = engine.analyze()
    content = render_html(report) if report_format == "html" else render_json(report)
    return Response(content, mimetype="text/html" if report_format == "html" else "application/json",
                    headers={"Content-Disposition": f'attachment; filename="saferevoke-report.{report_format}"'})


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/lab")
def lab_state():
    return jsonify(engine.describe_lab())


@app.post("/api/analyze")
def analyze():
    report = engine.analyze()
    report["comparative_benchmark"] = run_comparative_benchmark()
    return jsonify(report)


@app.post("/api/simulate/<grant_id>")
def simulate_grant(grant_id: str):
    result = engine.simulate_grant(grant_id)
    if result is None:
        return jsonify({"error": "Unknown permission"}), 404
    return jsonify(result)


@app.get("/api/workflows/<workflow_id>")
def run_workflow(workflow_id: str):
    result = engine.run_demo_workflow(workflow_id)
    if result is None:
        return jsonify({"error": "Unknown workflow"}), 404
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
