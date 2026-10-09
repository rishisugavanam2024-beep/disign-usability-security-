const names = {
  SAFE: "Safe in tested flows",
  UNKNOWN: "Unknown",
  PARTIAL_REMOVAL: "Partial removal",
  REQUIRED_ACCESS: "Required access",
  DELAYED_REMOVAL: "Delayed removal",
  UNSAFE_FALLBACK: "Unsafe fallback",
};

const badgeClass = (value) => value.toLowerCase().replaceAll("_", "-");
const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const outcomeNames = {
  UNCHANGED: "Unchanged",
  FAILED: "Task failed",
  FALLBACK: "Fallback used",
  ACCESS_REMAINS: "Access remains",
  CHANGED: "Path changed",
};

let labData;

function eventPath(event) {
  const decision = event.allowed ? "allowed" : "denied";
  const grants = event.grant_ids.length ? ` via ${event.grant_ids.join(", ")}` : "";
  return `<li class="${decision}"><strong>${escapeHtml(event.identity)}</strong><span>${escapeHtml(event.resource)}:${escapeHtml(event.action)} · ${decision}${escapeHtml(grants)}</span></li>`;
}

function renderSimulation(data) {
  document.querySelector("#simulation-placeholder").classList.add("hidden");
  document.querySelector("#simulation-result").classList.remove("hidden");
  document.querySelector("#denied-permission").textContent =
    `${data.grant.description} (${data.grant.id})`;
  const classification = document.querySelector("#simulation-classification");
  classification.className = `badge ${badgeClass(data.classification)}`;
  classification.textContent = names[data.classification];
  document.querySelector("#simulation-reason").textContent = data.reason;
  document.querySelector("#workflow-comparison").innerHTML = data.workflows.map((workflow) => `
    <article class="trace-row ${workflow.outcome === "UNCHANGED" ? "trace-muted" : ""}">
      <div class="trace-task"><strong>${escapeHtml(workflow.name)}</strong><small>${workflow.used_selected_grant ? "Used selected permission" : "Did not use selected permission"}</small></div>
      <div class="trace-state" data-label="Before denial"><span class="state-label ${workflow.before.success ? "success" : "failure"}">${workflow.before.success ? "Success" : "Failed"}</span><ul>${workflow.before.events.map(eventPath).join("") || "<li>No protected access</li>"}</ul></div>
      <div class="trace-state" data-label="After denial"><span class="state-label ${workflow.after.success ? "success" : "failure"}">${workflow.after.success ? "Success" : "Failed"}</span><ul>${workflow.after.events.map(eventPath).join("") || "<li>No protected access</li>"}</ul></div>
      <div class="trace-outcome"><span class="badge outcome-${workflow.outcome.toLowerCase()}">${outcomeNames[workflow.outcome]}</span></div>
    </article>
  `).join("");
  document.querySelector("#simulation-result").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function loadLab() {
  const data = await fetch("/api/lab").then((response) => response.json());
  labData = data;
  const select = document.querySelector("#permission-select");
  select.innerHTML = data.grants.map((grant) => `
    <option value="${escapeHtml(grant.id)}">${escapeHtml(grant.description)} — ${escapeHtml(grant.id)}</option>
  `).join("");
  const updatePermissionDetail = () => {
    const grant = labData.grants.find((item) => item.id === select.value);
    document.querySelector("#permission-detail").textContent = grant
      ? `${grant.probe_identity} can ${grant.action} ${grant.resource}`
      : "Select a permission to see its protected resource.";
  };
  select.addEventListener("change", updatePermissionDetail);
  updatePermissionDetail();
  document.querySelector("#workflows").innerHTML = data.workflows.map((workflow) => `
    <article class="workflow-card">
      <div class="workflow-icon">${workflow.name.slice(0, 2).toUpperCase()}</div>
      <h3>${workflow.name}</h3>
      <p>${workflow.description}</p>
      <button class="secondary" data-workflow="${workflow.id}">Run normal workflow</button>
      <pre id="output-${workflow.id}" class="hidden"></pre>
    </article>
  `).join("");

  document.querySelectorAll("[data-workflow]").forEach((button) => {
    button.addEventListener("click", async () => {
      const output = document.querySelector(`#output-${button.dataset.workflow}`);
      const result = await fetch(`/api/workflows/${button.dataset.workflow}`).then((response) => response.json());
      output.textContent = `${result.success ? "SUCCESS" : "FAILED"}: ${result.message}`;
      output.classList.remove("hidden");
    });
  });
}

document.querySelector("#simulate").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const grantId = document.querySelector("#permission-select").value;
  if (!grantId) return;
  button.disabled = true;
  button.textContent = "Denying and rerunning all tasks…";
  try {
    const response = await fetch(`/api/simulate/${encodeURIComponent(grantId)}`, { method: "POST" });
    if (!response.ok) throw new Error("The permission test could not be completed.");
    renderSimulation(await response.json());
  } catch (error) {
    document.querySelector("#simulation-placeholder").classList.remove("hidden");
    document.querySelector("#simulation-placeholder").innerHTML = `<strong>Simulation failed</strong><span>${escapeHtml(error.message)} Try again.</span>`;
  } finally {
    button.disabled = false;
    button.textContent = "Simulate denial";
  }
});

function renderAnalysis(data) {
  const comparison = data.comparative_benchmark;
  document.querySelector("#results").classList.remove("hidden");
  document.querySelector("#method").textContent =
    `${data.method.single_tests} single tests; ${data.method.ordered_sequence_tests} ordered interaction tests. Synthetic benchmark: ${(data.benchmark.recall * 100).toFixed(0)}% planted-interaction recall with ${(data.benchmark.experiment_reduction * 100).toFixed(1)}% fewer experiments than exhaustive ordered-pair testing.`;

  document.querySelector("#summary").innerHTML = Object.entries(names).map(([key, label]) => `
    <div class="summary-card ${badgeClass(key)}"><span>${label}</span><strong>${data.summary[key] || 0}</strong></div>
  `).join("");

  document.querySelector("#comparison").textContent =
    `SafeRevoke found ${comparison.saferevoke.found}/${comparison.expected_total} planted interactions (${(comparison.saferevoke.recall * 100).toFixed(0)}% recall). Policy-only replay found ${comparison.policy_only_replay.found}/${comparison.expected_total} (${(comparison.policy_only_replay.recall * 100).toFixed(0)}%) and found ${(comparison.policy_only_replay.runtime_fallback_recall * 100).toFixed(0)}% of runtime fallbacks. Adaptive testing used ${(comparison.experiment_reduction * 100).toFixed(1)}% fewer experiments than exhaustive ordered-pair testing.`;
  document.querySelector("#benchmark-apps").innerHTML = comparison.applications.map((app) => `
    <div class="summary-card neutral">
      <span>${app.name}</span>
      <strong>${app.saferevoke_found}/${app.expected_interactions}</strong>
      <small>policy replay: ${app.policy_replay_found}/${app.expected_interactions}</small>
    </div>
  `).join("");
  document.querySelector("#benchmark-warning").textContent = comparison.warning;

  document.querySelector("#experiments").innerHTML = data.experiments.map((item) => `
    <article class="result-row">
      <div>
        <strong>${item.grant.description}</strong>
        <small>${item.grant.probe_identity} → ${item.grant.resource}:${item.grant.action}</small>
      </div>
      <span class="badge ${badgeClass(item.classification)}">${names[item.classification]}</span>
      <p>${item.reason}${item.risk_evidence.length ? ` Computed privilege impact: ${item.risk_evidence[0].baseline_scope.impact_score} → ${item.risk_evidence[0].alternate_scope.impact_score}.` : ""}</p>
    </article>
  `).join("");

  document.querySelector("#plans").innerHTML = data.sequence_plans.length
    ? data.sequence_plans.map((plan) => `
      <article class="plan">
        <span class="badge neutral">${plan.discovered_by}</span>
        <h4>${plan.preferred_order.join(" → ")}</h4>
        <p>${plan.recommendation}</p>
      </article>
    `).join("")
    : "<p>No interacting access paths were discovered.</p>";
  document.querySelector("#results").scrollIntoView({ behavior: "smooth" });
}

document.querySelector("#analyze").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "Testing permission changes…";
  try {
    const data = await fetch("/api/analyze", { method: "POST" }).then((response) => response.json());
    renderAnalysis(data);
  } finally {
    button.disabled = false;
    button.textContent = "Analyze all permissions";
  }
});

loadLab();
