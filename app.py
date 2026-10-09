from flask import Flask, jsonify, render_template

from saferevoke.benchmark import run_comparative_benchmark
from saferevoke.engine import SafeRevokeEngine
from saferevoke.lab import build_lab


app = Flask(__name__)
engine = SafeRevokeEngine(build_lab())


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
