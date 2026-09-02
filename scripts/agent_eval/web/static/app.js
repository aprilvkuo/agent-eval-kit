const state = { datasets: [], selectedDataset: null, runs: [], selectedRun: null, config: {}, models: [], poller: null };
const $ = (selector) => document.querySelector(selector);

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadConfig();
  await Promise.all([loadModels(), loadDatasets()]);
});

function bindEvents() {
  $("#open-import").addEventListener("click", () => $("#import-dialog").showModal());
  document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
  $("#import-form").addEventListener("submit", importDataset);
  $("#run-form").addEventListener("submit", createRun);
  $("#agent").addEventListener("change", syncAgentFields);
  $("#view-tasks").addEventListener("click", showTasks);
  $("#delete-dataset").addEventListener("click", deleteDataset);
  $("#close-detail").addEventListener("click", closeDetail);
  $("#drawer-backdrop").addEventListener("click", closeDetail);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try { message = (await response.json()).detail || message; } catch (_) {}
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function loadConfig() {
  try {
    state.config = await api("/api/config");
    $("#model-name").textContent = state.config.model || "未配置模型";
    $("#endpoint-name").textContent = state.config.base_url || "Oracle 可直接运行";
    $("#auth-dot").classList.toggle("ready", state.config.auth_configured);
  } catch (error) { toast(error.message, true); }
}

async function loadModels() {
  const select = $("#model");
  try {
    const catalog = await api("/api/models");
    state.models = catalog.models || [];
    if (!state.models.length) {
      select.innerHTML = '<option value="">未发现可用模型</option>';
    } else {
      select.innerHTML = state.models.map((model) => `
        <option value="${escapeHtml(model)}" ${model === catalog.current ? "selected" : ""}>${escapeHtml(model)}</option>`).join("");
    }
    if (catalog.warning) toast(catalog.warning, true);
  } catch (error) {
    state.models = state.config.model ? [state.config.model] : [];
    select.innerHTML = state.models.length
      ? `<option value="${escapeHtml(state.models[0])}">${escapeHtml(state.models[0])}</option>`
      : '<option value="">模型列表读取失败</option>';
    toast(error.message, true);
  }
  syncAgentFields();
}

async function loadDatasets(preferredId = null) {
  try {
    state.datasets = await api("/api/datasets");
    renderDatasets();
    const id = preferredId || state.selectedDataset?.id || state.datasets[0]?.id;
    if (id) await selectDataset(id);
    else resetWorkspace();
  } catch (error) { toast(error.message, true); }
}

function renderDatasets() {
  const root = $("#dataset-list");
  if (!state.datasets.length) {
    root.innerHTML = '<div class="sidebar-empty">还没有测试集<br>点击右上角 ＋ 导入</div>';
    return;
  }
  root.innerHTML = state.datasets.map((dataset) => `
    <button class="dataset-item ${state.selectedDataset?.id === dataset.id ? "active" : ""}" data-dataset="${escapeHtml(dataset.id)}">
      <strong>${escapeHtml(dataset.name)}</strong><span>${dataset.task_count} 条</span>
      <span>${escapeHtml(dataset.source_filename || "JSONL")}</span><span>${formatDate(dataset.created_at)}</span>
    </button>`).join("");
  root.querySelectorAll("[data-dataset]").forEach((button) => button.addEventListener("click", () => selectDataset(button.dataset.dataset)));
}

async function selectDataset(id) {
  state.selectedDataset = state.datasets.find((item) => item.id === id);
  state.selectedRun = null;
  clearInterval(state.poller);
  renderDatasets();
  $("#page-title").textContent = state.selectedDataset.name;
  $("#page-subtitle").textContent = `${state.selectedDataset.task_count} 条任务 · ${state.selectedDataset.source_filename || "JSONL"}`;
  $("#run-button").disabled = false;
  $("#view-tasks").disabled = false;
  $("#delete-dataset").disabled = false;
  resetMetrics();
  await loadRuns();
}

async function importDataset(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    const dataset = await api("/api/datasets", { method: "POST", body: new FormData(form) });
    form.reset();
    $("#import-dialog").close();
    toast(`已导入 ${dataset.task_count} 条任务`);
    await loadDatasets(dataset.id);
  } catch (error) { toast(error.message, true); }
  finally { submit.disabled = false; }
}

async function showTasks() {
  if (!state.selectedDataset) return;
  try {
    const tasks = await api(`/api/datasets/${state.selectedDataset.id}/tasks`);
    $("#tasks-content").innerHTML = tasks.map((task, index) => `
      <details class="task-row"><summary>${index + 1}. ${escapeHtml(task.id || "未命名任务")} · ${escapeHtml(task.extra?.scenario || "未标注场景")}</summary>
      <pre>${escapeHtml(JSON.stringify(task, null, 2))}</pre></details>`).join("");
    $("#tasks-dialog").showModal();
  } catch (error) { toast(error.message, true); }
}

async function deleteDataset() {
  if (!state.selectedDataset) return;
  if (!window.confirm(`删除“${state.selectedDataset.name}”及其全部评测记录？此操作不可撤销。`)) return;
  try {
    await api(`/api/datasets/${state.selectedDataset.id}`, { method: "DELETE" });
    state.selectedDataset = null;
    state.selectedRun = null;
    toast("测试集已删除");
    await loadDatasets();
  } catch (error) { toast(error.message, true); }
}

async function loadRuns(selectNewest = true) {
  if (!state.selectedDataset) return;
  try {
    state.runs = await api(`/api/runs?dataset_id=${encodeURIComponent(state.selectedDataset.id)}`);
    renderRuns();
    if (selectNewest && state.runs.length) await selectRun(state.runs[0].id);
    else if (!state.runs.length) resetTrials();
  } catch (error) { toast(error.message, true); }
}

function renderRuns() {
  $("#run-count").textContent = `${state.runs.length} 次运行`;
  const root = $("#runs-list");
  if (!state.runs.length) {
    root.className = "table-wrap empty-box";
    root.textContent = "还没有评测记录";
    return;
  }
  root.className = "table-wrap";
  root.innerHTML = `<table><thead><tr><th>时间 / Agent</th><th>进度</th><th>结果</th></tr></thead><tbody>${state.runs.map((run) => {
    const progress = run.total_trials ? Math.round(run.completed_trials / run.total_trials * 100) : 0;
    const result = run.summary ? `${pct(run.summary.pass_rate)} 通过` : statusLabel(run.status);
    return `<tr data-run="${run.id}" class="${state.selectedRun?.id === run.id ? "active" : ""}">
      <td><strong>${escapeHtml(run.agent === "oracle" ? "Oracle" : (run.model || "OpenAI"))}</strong><br><span class="muted">${formatDate(run.created_at, true)}</span></td>
      <td><div class="progress"><i style="width:${progress}%"></i></div><span class="muted">${run.completed_trials}/${run.total_trials}</span></td>
      <td><span class="badge ${run.status}">${escapeHtml(result)}</span></td></tr>`;
  }).join("")}</tbody></table>`;
  root.querySelectorAll("[data-run]").forEach((row) => row.addEventListener("click", () => selectRun(row.dataset.run)));
}

async function createRun(event) {
  event.preventDefault();
  if (!state.selectedDataset) return;
  const agent = $("#agent").value;
  const payload = {
    dataset_id: state.selectedDataset.id,
    agent,
    trials_per_task: Number($("#trials-per-task").value),
    max_steps: $("#max-steps").value ? Number($("#max-steps").value) : null,
  };
  if (agent === "openai") payload.model = $("#model").value || state.config.model || null;
  const button = $("#run-button");
  button.disabled = true;
  button.textContent = "正在启动…";
  try {
    const run = await api("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    toast("评测已启动");
    await loadRuns(false);
    await selectRun(run.id);
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.textContent = "开始评测"; }
}

async function selectRun(id) {
  clearInterval(state.poller);
  try {
    state.selectedRun = await api(`/api/runs/${id}`);
    const local = state.runs.findIndex((item) => item.id === id);
    if (local >= 0) state.runs[local] = state.selectedRun;
    renderRuns();
    renderMetrics(state.selectedRun);
    await loadTrials(id);
    if (["queued", "running"].includes(state.selectedRun.status)) {
      state.poller = setInterval(() => refreshRun(id), 1200);
    }
  } catch (error) { toast(error.message, true); }
}

async function refreshRun(id) {
  try {
    const run = await api(`/api/runs/${id}`);
    state.selectedRun = run;
    const index = state.runs.findIndex((item) => item.id === id);
    if (index >= 0) state.runs[index] = run;
    renderRuns();
    renderMetrics(run);
    await loadTrials(id);
    if (!["queued", "running"].includes(run.status)) clearInterval(state.poller);
  } catch (error) { clearInterval(state.poller); toast(error.message, true); }
}

function renderMetrics(run) {
  const summary = run.summary;
  const values = summary ? [pct(summary.pass_rate), pct(summary.average_score), pct(summary.pass_at_k), number(summary.average_tool_calls)] : ["—", "—", "—", "—"];
  $("#metric-grid").querySelectorAll(".metric strong").forEach((node, index) => node.textContent = values[index]);
  const statusNode = $("#run-status");
  statusNode.className = `badge ${run.status}`;
  statusNode.textContent = run.status === "running" ? `${run.completed_trials}/${run.total_trials} 运行中` : statusLabel(run.status);
  if (run.error) toast(run.error, true);
}

async function loadTrials(runId) {
  try {
    const trials = await api(`/api/runs/${runId}/trials`);
    $("#trial-count").textContent = `${trials.length} / ${state.selectedRun.total_trials} 条完成`;
    const root = $("#trials-list");
    if (!trials.length) {
      root.className = "table-wrap empty-box";
      root.textContent = state.selectedRun.status === "failed" ? (state.selectedRun.error || "运行失败") : "等待模型输出…";
      return;
    }
    root.className = "table-wrap";
    root.innerHTML = `<table><thead><tr><th>任务</th><th>结果</th><th>得分</th><th>工具</th><th>耗时</th></tr></thead><tbody>${trials.map(({trial, evaluation}) => `
      <tr data-trial="${trial.trial_id}"><td><strong>${escapeHtml(trial.task_id)}</strong><br><span class="muted">${escapeHtml(trial.metadata?.scenario || "—")}</span></td>
      <td><span class="badge ${evaluation.passed ? "pass" : "fail"}">${evaluation.passed ? "通过" : "失败"}</span></td>
      <td>${pct(evaluation.score)}</td><td>${evaluation.metrics?.tool_call_count ?? "—"}</td><td>${number(trial.duration_ms)} ms</td></tr>`).join("")}</tbody></table>`;
    root.querySelectorAll("[data-trial]").forEach((row) => row.addEventListener("click", () => showTrial(row.dataset.trial)));
  } catch (error) { toast(error.message, true); }
}

async function showTrial(id) {
  try {
    const detail = await api(`/api/trials/${id}`);
    renderTrialDetail(detail);
    $("#detail-drawer").classList.add("open");
    $("#detail-drawer").setAttribute("aria-hidden", "false");
    $("#drawer-backdrop").classList.add("open");
  } catch (error) { toast(error.message, true); }
}

function renderTrialDetail({ task, trial, evaluation }) {
  $("#detail-title").textContent = trial.task_id;
  const failures = evaluation.failures?.length ? `<ul class="failure-list">${evaluation.failures.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : '<span class="badge pass">全部校验通过</span>';
  const timeline = trial.transcript.map(renderTraceEvent).join("");
  const diagnostics = evaluation.diagnostics || {};
  const visibleInput = task?.input || {};
  const taskInput = {
    prompt: visibleInput.prompt || "",
    files: visibleInput.files || [],
    initial_state: visibleInput.initial_state || {},
    available_tools: (visibleInput.tools || []).map((tool) => tool.name),
  };
  $("#detail-content").innerHTML = `
    <div class="detail-summary">
      <div class="mini-metric"><span>结果</span><strong class="${evaluation.passed ? "" : "fail-text"}">${evaluation.passed ? "通过" : "失败"}</strong></div>
      <div class="mini-metric"><span>总分</span><strong>${pct(evaluation.score)}</strong></div>
      <div class="mini-metric"><span>状态准确率</span><strong>${pct(evaluation.metrics?.state_key_accuracy)}</strong></div>
      <div class="mini-metric"><span>逐项覆盖率</span><strong>${pct(evaluation.metrics?.item_coverage)}</strong></div>
    </div>
    <section class="detail-section"><h3>Task 输入</h3><pre class="json-block">${escapeHtml(JSON.stringify(taskInput, null, 2))}</pre></section>
    <section class="detail-section"><h3>Harness 调用链 · ${trial.transcript.length} 个事件</h3><div class="trace">${timeline || '<p class="muted">没有调用事件</p>'}</div></section>
    <section class="detail-section"><h3>Outcome · 模型最终输出</h3><div class="answer">${escapeHtml(trial.outcome?.final_answer || "（无文字输出）")}</div><pre class="json-block">${escapeHtml(JSON.stringify(trial.outcome?.final_state || {}, null, 2))}</pre></section>
    <section class="detail-section"><h3>Grade · 评估结论</h3>${failures}<pre class="json-block">${escapeHtml(JSON.stringify(diagnostics, null, 2))}</pre></section>
    <section class="detail-section"><h3>Target State</h3><pre class="json-block">${escapeHtml(JSON.stringify(task?.output?.target_state || {}, null, 2))}</pre></section>`;
}

function renderTraceEvent(event) {
  if (event.type === "assistant") {
    const request = event.model_request;
    const response = { content: event.content || "", tool_calls: event.tool_calls || [] };
    const usage = event.usage || {};
    return `<article class="trace-step assistant"><div class="trace-head"><strong>Turn ${event.turn} · Model</strong><span>${number(event.duration_ms)} ms</span></div>
      <div class="trace-meta"><span>${escapeHtml(request?.model || "Oracle / scripted")}</span><span>finish: ${escapeHtml(event.finish_reason || "—")}</span><span>tokens: ${usage.total_tokens ?? 0}</span></div>
      ${request ? traceDetails("完整 Model Request", request) : ""}
      ${traceDetails("Model Response", response, true)}</article>`;
  }
  if (event.type === "tool_result") {
    const changes = stateChanges(event.state_before || {}, event.state_after || {});
    return `<article class="trace-step tool_result"><div class="trace-head"><strong>Step ${event.step} · Tool · ${escapeHtml(event.name)}</strong><span>${number(event.duration_ms)} ms</span></div>
      <div class="trace-grid"><div class="trace-box"><b>Arguments</b>\n${escapeHtml(JSON.stringify(event.arguments, null, 2))}</div><div class="trace-box"><b>Result</b>\n${escapeHtml(JSON.stringify(event.result, null, 2))}</div></div>
      <div class="state-change">${changes.length ? changes.map((change) => `<span class="state-chip">${escapeHtml(change)}</span>`).join("") : '<span class="muted">状态无变化</span>'}</div>
      ${traceDetails("完整 State Before / After", { state_before: event.state_before, state_after: event.state_after })}</article>`;
  }
  if (event.type === "agent_error") {
    return `<article class="trace-step agent_error"><div class="trace-head"><strong>Turn ${event.turn} · Agent Error</strong><span>${number(event.duration_ms)} ms</span></div><div class="trace-error">${escapeHtml(event.error)}</div></article>`;
  }
  return `<article class="trace-step"><pre class="trace-box">${escapeHtml(JSON.stringify(event, null, 2))}</pre></article>`;
}

function traceDetails(label, payload, open = false) {
  return `<details class="trace-details" ${open ? "open" : ""}><summary>${escapeHtml(label)}</summary><pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre></details>`;
}

function closeDetail() {
  $("#detail-drawer").classList.remove("open");
  $("#detail-drawer").setAttribute("aria-hidden", "true");
  $("#drawer-backdrop").classList.remove("open");
}

function syncAgentFields() {
  const isModel = $("#agent").value === "openai";
  $("#model").disabled = !isModel || !state.models.length;
}

function resetWorkspace() {
  state.selectedDataset = null;
  $("#page-title").textContent = "选择一个测试集";
  $("#page-subtitle").textContent = "导入 JSONL 后即可运行 Agent 并查看全过程。";
  $("#run-button").disabled = true;
  $("#view-tasks").disabled = true;
  $("#delete-dataset").disabled = true;
  $("#runs-list").className = "table-wrap empty-box";
  $("#runs-list").textContent = "选择测试集后显示运行记录";
  resetMetrics(); resetTrials();
}

function resetMetrics() {
  $("#metric-grid").querySelectorAll(".metric strong").forEach((node) => node.textContent = "—");
  $("#run-status").textContent = "";
  $("#run-status").className = "";
}

function resetTrials() {
  $("#trial-count").textContent = "选择一条评测记录";
  $("#trials-list").className = "table-wrap empty-box";
  $("#trials-list").textContent = "这里会显示模型输出与评分";
}

function stateChanges(before, after) {
  const changes = [];
  new Set([...Object.keys(before), ...Object.keys(after)]).forEach((key) => {
    if (JSON.stringify(before[key]) !== JSON.stringify(after[key])) changes.push(`${key}: ${short(before[key])} → ${short(after[key])}`);
  });
  return changes;
}

function short(value) { const text = JSON.stringify(value); return text?.length > 32 ? text.slice(0, 29) + "…" : text; }
function pct(value) { return typeof value === "number" ? `${(value * 100).toFixed(value === 1 || value === 0 ? 0 : 1)}%` : "—"; }
function number(value) { return typeof value === "number" ? Number(value.toFixed(1)).toLocaleString() : "—"; }
function statusLabel(status) { return ({ queued: "排队中", running: "运行中", completed: "已完成", failed: "失败" })[status] || status; }
function formatDate(value, withTime = false) { if (!value) return "—"; const date = new Date(value); return new Intl.DateTimeFormat("zh-CN", withTime ? { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" } : { month: "2-digit", day: "2-digit" }).format(date); }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]); }
function toast(message, isError = false) { const node = $("#toast"); node.textContent = message; node.className = `toast show${isError ? " error" : ""}`; clearTimeout(node.timer); node.timer = setTimeout(() => node.className = "toast", 2800); }
