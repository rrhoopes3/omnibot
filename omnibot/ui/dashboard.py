from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from omnibot.core.coordination_kernel import CoordinationKernel


def dashboard_router(kernel: CoordinationKernel) -> APIRouter:
    router = APIRouter()

    @router.get("/api/events")
    async def events(limit: int = 120):
        return [event.model_dump() for event in await kernel.event_bus.recent(limit=limit)]

    @router.get("/api/events/{task_id}")
    async def task_events(task_id: str):
        return [event.model_dump() for event in await kernel.event_bus.replay(task_id=task_id)]

    @router.get("/api/trace/{task_id}")
    async def task_trace(task_id: str):
        events = [event.model_dump() for event in await kernel.event_bus.replay(task_id=task_id)]
        return _build_trace(task_id, events)

    @router.get("/api/traces")
    async def traces(limit: int = 200):
        events = [event.model_dump() for event in await kernel.event_bus.recent(limit=limit)]
        by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            task_id = event.get("task_id")
            if task_id:
                by_task[task_id].append(event)
        return [_build_trace(task_id, task_events) for task_id, task_events in by_task.items()]

    @router.get("/api/memory")
    async def memory(limit: int = 30):
        return [item.model_dump(exclude={"embedding"}) for item in await kernel.memory.recent(limit=limit)]

    @router.get("/", response_class=HTMLResponse)
    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        return HTMLResponse(DASHBOARD_HTML)

    return router


def _build_trace(task_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    agents = [e["payload"] for e in events if e["type"] == "agent.completed"]
    tools = [e["payload"] for e in events if e["type"] == "tool.completed"]
    artifacts = [e["payload"] for e in events if e["type"] == "artifact.created"]
    memories = [e["payload"] for e in events if e["type"] == "memory.written"]
    arbiter_events = [e for e in events if e["type"] == "arbiter.decided"]
    task_events = [e for e in events if e["type"] == "task.created"]
    statuses = [e["payload"].get("status") for e in events if e["type"] == "task.status"]
    decision = arbiter_events[-1]["payload"] if arbiter_events else {}
    return {
        "task_id": task_id,
        "request": task_events[-1]["payload"].get("user_request", "") if task_events else "",
        "status": statuses[-1] if statuses else "unknown",
        "agents": agents,
        "tools": tools,
        "artifacts": artifacts,
        "arbiter": decision,
        "memory_writes": memories,
        "causal_chain": [
            {
                "event_id": e["event_id"],
                "type": e["type"],
                "parents": e["causal_parent_ids"],
                "audit_hash": e["audit_hash"],
            }
            for e in events
        ],
    }


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OmniBot Visible Arbiter</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17202a;
      --muted: #5c6975;
      --line: #d9e0e7;
      --panel: #ffffff;
      --band: #f5f7fa;
      --accent: #0f766e;
      --accent-soft: #d9f3ef;
      --warn: #a15c00;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px/1.45 system-ui, -apple-system, Segoe UI, sans-serif;
      color: var(--ink);
      background: var(--band);
    }
    header {
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
    }
    h1 { font-size: 18px; margin: 0; }
    button {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 6px;
      padding: 8px 12px;
      cursor: pointer;
    }
    main { padding: 20px 24px 40px; max-width: 1180px; margin: 0 auto; }
    .trace {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 18px;
      overflow: hidden;
    }
    .trace-head {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 6px;
    }
    .task-id { color: var(--muted); font-size: 12px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      padding: 14px;
    }
    section {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-width: 0;
    }
    section.wide { grid-column: 1 / -1; }
    h2 { font-size: 13px; margin: 0 0 8px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      background: #f8fafc;
      border: 1px solid #edf1f5;
      border-radius: 6px;
      padding: 8px;
      max-height: 260px;
      overflow: auto;
    }
    .pill {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      margin-right: 5px;
    }
    .metric {
      display: grid;
      grid-template-columns: 150px 1fr 42px;
      gap: 8px;
      align-items: center;
      margin: 6px 0;
    }
    .bar { height: 8px; background: #edf1f5; border-radius: 999px; overflow: hidden; }
    .bar span { display: block; height: 100%; background: var(--accent); }
    .empty { color: var(--muted); padding: 18px; }
    @media (max-width: 780px) {
      .grid { grid-template-columns: 1fr; }
      section.wide { grid-column: auto; }
      header { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>OmniBot v0.1.1 Visible Arbiter</h1>
      <div class="task-id">One page for what happened, why it happened, and what evidence carried the decision.</div>
    </div>
    <button onclick="loadTraces()">Refresh</button>
  </header>
  <main id="app"><div class="empty">Loading traces...</div></main>
  <script>
    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
    }
    function metric(label, value) {
      const n = Number(value || 0);
      return `<div class="metric"><div>${esc(label)}</div><div class="bar"><span style="width:${Math.max(0, Math.min(1, n)) * 100}%"></span></div><div>${n.toFixed(2)}</div></div>`;
    }
    function renderTrace(trace) {
      const arb = trace.arbiter || {};
      const score = arb.coherence_score || {};
      const agentHtml = (trace.agents || []).map(a => `<p><span class="pill">${esc(a.agent_name)}</span>${esc(a.summary)}<br><small>confidence ${esc(a.confidence)} | tools ${(a.tool_calls || []).map(esc).join(', ') || 'none'}</small></p>`).join('') || '<p class="empty">No agents yet.</p>';
      const toolHtml = (trace.tools || []).map(t => `<p><span class="pill">${esc(t.tool_name)}</span><pre>${esc(JSON.stringify(t.result, null, 2))}</pre></p>`).join('') || '<p class="empty">No tool calls yet.</p>';
      const artifactHtml = (trace.artifacts || []).map(a => `<p><span class="pill">${esc(a.artifact_type)}</span>${esc(a.path)}<pre>${esc(a.content)}</pre></p>`).join('') || '<p class="empty">No artifacts yet.</p>';
      const causal = (trace.causal_chain || []).map(e => `${e.type} ${e.event_id}\\n  parents: ${(e.parents || []).join(', ') || '(none)'}\\n  ${e.audit_hash}`).join('\\n\\n');
      return `<article class="trace">
        <div class="trace-head">
          <strong>${esc(trace.request || 'Request unavailable')}</strong>
          <span class="task-id">${esc(trace.task_id)} | status: ${esc(trace.status)}</span>
        </div>
        <div class="grid">
          <section><h2>Agents</h2>${agentHtml}</section>
          <section><h2>Coherence Score</h2>
            ${metric('Overall', score.overall)}
            ${metric('Evidence coverage', score.evidence_coverage)}
            ${metric('Agent agreement', score.agent_agreement)}
            ${metric('Tool provenance', score.tool_provenance)}
            ${metric('Confidence spread', score.confidence_spread)}
            ${metric('Unresolved risk', score.unresolved_risk)}
          </section>
          <section class="wide"><h2>Arbiter Decision</h2><pre>${esc(JSON.stringify(arb, null, 2))}</pre></section>
          <section><h2>Tool Calls</h2>${toolHtml}</section>
          <section><h2>Patch Artifacts</h2>${artifactHtml}</section>
          <section><h2>Memory Writes</h2><pre>${esc(JSON.stringify(trace.memory_writes || [], null, 2))}</pre></section>
          <section><h2>Causal Chain</h2><pre>${esc(causal)}</pre></section>
        </div>
      </article>`;
    }
    async function loadTraces() {
      const app = document.getElementById('app');
      const res = await fetch('/api/traces');
      const traces = await res.json();
      app.innerHTML = traces.length ? traces.reverse().map(renderTrace).join('') : '<div class="empty">No task traces yet. POST to /chat or run the CLI demo.</div>';
    }
    loadTraces();
  </script>
</body>
</html>
"""
