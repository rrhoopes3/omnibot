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
        "timestamp": task_events[-1]["timestamp"] if task_events else "",
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
  <title>OmniBot Beautiful Trace</title>
  <style>
    :root {
      color-scheme: dark;
      --void: #0a0f1e;
      --abyss: #10182b;
      --stone: #172238;
      --stone-2: #1d2a42;
      --line: rgba(212, 175, 55, 0.28);
      --line-ice: rgba(79, 195, 247, 0.26);
      --gold: #d4af37;
      --gold-soft: #f2d57a;
      --ice: #4fc3f7;
      --blood: #c62828;
      --green: #4caf50;
      --ink: #edf6ff;
      --muted: #a8b5c7;
      --dim: #6f7f95;
      --parchment: #d8c190;
      --shadow: rgba(0, 0, 0, 0.55);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font: 14px/1.45 "Segoe UI", "Trebuchet MS", system-ui, sans-serif;
      color: var(--ink);
      background:
        linear-gradient(rgba(255,255,255,0.018) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.014) 1px, transparent 1px),
        linear-gradient(180deg, #0a0f1e 0%, #0d1426 48%, #080b13 100%);
      background-size: 30px 30px, 30px 30px, auto;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        radial-gradient(ellipse at top, rgba(79, 195, 247, 0.13), transparent 45%),
        linear-gradient(135deg, rgba(212, 175, 55, 0.06), transparent 22%, rgba(198, 40, 40, 0.05) 72%, transparent);
      mix-blend-mode: screen;
    }
    button, select {
      color: var(--ink);
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(29,42,66,.96), rgba(13,20,38,.96));
      border-radius: 6px;
      padding: 8px 11px;
      cursor: pointer;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.06), 0 8px 22px rgba(0,0,0,.22);
      transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
    }
    button:hover, select:hover {
      transform: translateY(-1px) scale(1.01);
      border-color: rgba(242,213,122,.72);
      box-shadow: 0 0 18px rgba(212,175,55,.18), inset 0 1px 0 rgba(255,255,255,.09);
    }
    .shell {
      width: min(1280px, calc(100vw - 40px));
      margin: 0 auto;
      padding: 24px 0 56px;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 5;
      margin: 0 -20px 24px;
      padding: 15px 20px;
      border-bottom: 1px solid rgba(212,175,55,.18);
      background: linear-gradient(180deg, rgba(10,15,30,.96), rgba(10,15,30,.78));
      backdrop-filter: blur(12px);
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
    }
    .brand {
      display: grid;
      gap: 4px;
      min-width: 0;
    }
    h1 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(22px, 3vw, 34px);
      font-weight: 700;
      color: var(--gold-soft);
      text-shadow: 0 0 18px rgba(212,175,55,.32), 0 2px 0 #000;
    }
    .subtitle {
      color: var(--muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 74vw;
    }
    .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
    .composer {
      margin-bottom: 24px;
      border: 1px solid rgba(79,195,247,.28);
      border-radius: 8px;
      background:
        linear-gradient(135deg, rgba(79,195,247,.08), transparent 30%),
        radial-gradient(ellipse at right, rgba(212,175,55,.09), transparent 42%),
        linear-gradient(180deg, rgba(23,34,56,.9), rgba(10,15,30,.94));
      box-shadow: 0 18px 44px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.06);
      padding: 18px 20px;
      display: grid;
      grid-template-columns: 230px minmax(0, 1fr);
      gap: 18px;
      align-items: center;
    }
    .composer-head {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 12px;
      color: var(--gold-soft);
      font-family: Georgia, "Times New Roman", serif;
      font-size: 18px;
      font-weight: 700;
      text-align: center;
    }
    .composer-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: stretch;
    }
    textarea {
      width: 100%;
      min-height: 74px;
      resize: vertical;
      color: var(--ink);
      background: rgba(0,0,0,.32);
      border: 1px solid rgba(79,195,247,.26);
      border-radius: 8px;
      padding: 11px 12px;
      font: 14px/1.45 "Segoe UI", system-ui, sans-serif;
      outline: none;
      box-shadow: inset 0 1px 10px rgba(0,0,0,.28);
      transition: border-color .16s ease, box-shadow .16s ease;
    }
    textarea:focus {
      border-color: rgba(79,195,247,.72);
      box-shadow: 0 0 18px rgba(79,195,247,.14), inset 0 1px 10px rgba(0,0,0,.28);
    }
    .run-button {
      min-width: 150px;
      color: #0a0f1e;
      font-weight: 800;
      background: linear-gradient(180deg, #f2d57a, #d4af37 54%, #9a6d10);
      border-color: rgba(242,213,122,.78);
      text-shadow: 0 1px rgba(255,255,255,.35);
    }
    .run-button:disabled {
      cursor: wait;
      opacity: .72;
      transform: none;
    }
    .composer-status {
      color: var(--muted);
      min-height: 18px;
      font-size: 12px;
      grid-column: 2;
    }
    .chapter {
      display: grid;
      gap: 22px;
      margin-bottom: 24px;
    }
    .hero {
      border: 1px solid rgba(212,175,55,.32);
      border-radius: 8px;
      background:
        linear-gradient(135deg, rgba(212,175,55,.08), transparent 28%),
        linear-gradient(180deg, rgba(23,34,56,.95), rgba(10,15,30,.96));
      box-shadow: 0 26px 60px var(--shadow), inset 0 1px 0 rgba(255,255,255,.07);
      padding: 22px;
      display: grid;
      grid-template-columns: 1.1fr .9fr;
      gap: 16px;
    }
    .task-title {
      font-size: clamp(18px, 2vw, 26px);
      font-weight: 800;
      margin: 0 0 14px;
      color: #ffffff;
      text-shadow: 0 0 16px rgba(79,195,247,.18);
    }
    .meta-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 12px;
    }
    .seal {
      justify-self: end;
      align-self: center;
      min-width: 210px;
      border: 1px solid rgba(212,175,55,.5);
      border-radius: 8px;
      padding: 14px;
      background: linear-gradient(180deg, rgba(18,27,47,.92), rgba(7,10,20,.92));
      text-align: center;
      box-shadow: 0 0 28px rgba(212,175,55,.16), inset 0 0 18px rgba(212,175,55,.05);
    }
    .overall {
      font-family: Georgia, "Times New Roman", serif;
      font-size: 54px;
      line-height: .9;
      color: var(--gold-soft);
      text-shadow: 0 0 24px rgba(212,175,55,.42);
    }
    .panel {
      border: 1px solid rgba(212,175,55,.24);
      border-radius: 8px;
      background:
        linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
        linear-gradient(180deg, rgba(23,34,56,.92), rgba(12,18,34,.94));
      background-size: 100% 22px, auto;
      box-shadow: 0 18px 44px rgba(0,0,0,.36), inset 0 1px 0 rgba(255,255,255,.05);
      padding: 18px;
      min-width: 0;
    }
    .panel:hover {
      border-color: rgba(79,195,247,.44);
      box-shadow: 0 18px 48px rgba(0,0,0,.42), 0 0 22px rgba(79,195,247,.08);
    }
    .panel-title {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 8px;
      align-items: center;
      margin: 0 0 12px;
      color: var(--gold-soft);
      font-family: Georgia, "Times New Roman", serif;
      font-size: 18px;
      font-weight: 700;
      text-shadow: 0 1px 0 #000;
      padding-bottom: 10px;
      border-bottom: 1px solid rgba(212,175,55,.14);
    }
    .sigil {
      width: 24px;
      height: 24px;
      border: 1px solid rgba(212,175,55,.54);
      border-radius: 6px;
      display: grid;
      place-items: center;
      color: var(--ice);
      font-size: 11px;
      font-weight: 900;
      box-shadow: 0 0 14px rgba(79,195,247,.16), inset 0 0 10px rgba(79,195,247,.08);
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 14px;
    }
    .stat {
      padding: 14px;
      border: 1px solid rgba(79,195,247,.18);
      border-radius: 8px;
      background: rgba(7,10,20,.42);
    }
    .stat-label { color: var(--muted); font-size: 12px; margin-bottom: 7px; }
    .stat-value { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .bar {
      height: 9px;
      flex: 1;
      border-radius: 999px;
      background: rgba(255,255,255,.08);
      overflow: hidden;
      box-shadow: inset 0 1px 5px rgba(0,0,0,.45);
    }
    .bar span {
      display: block;
      height: 100%;
      border-radius: 999px;
      box-shadow: 0 0 14px currentColor;
    }
    .score-num { min-width: 38px; text-align: right; font-weight: 800; }
    .green { color: var(--green); background: linear-gradient(90deg, #2e7d32, #81c784); }
    .gold { color: var(--gold); background: linear-gradient(90deg, #9a6d10, #f2d57a); }
    .red { color: var(--blood); background: linear-gradient(90deg, #8e1b1b, #ef5350); }
    .arbiter {
      border-color: rgba(212,175,55,.46);
      background:
        linear-gradient(135deg, rgba(212,175,55,.13), transparent 34%),
        linear-gradient(180deg, rgba(29,42,66,.98), rgba(10,15,30,.98));
    }
    .arbiter.high {
      box-shadow: 0 0 34px rgba(212,175,55,.22), 0 24px 58px rgba(0,0,0,.42), inset 0 1px 0 rgba(255,255,255,.08);
    }
    .arb-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 18px;
      align-items: start;
    }
    .callout {
      border-left: 3px solid var(--gold);
      padding: 10px 12px;
      background: rgba(212,175,55,.07);
      border-radius: 0 6px 6px 0;
      color: #fff8dc;
    }
    .rejected { color: var(--muted); margin-top: 10px; }
    .agent-grid, .tool-grid, .memory-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }
    details {
      border: 1px solid rgba(79,195,247,.2);
      border-radius: 8px;
      background:
        linear-gradient(180deg, rgba(23,34,56,.62), rgba(7,10,20,.48));
      overflow: hidden;
      transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
    }
    details:hover {
      transform: translateY(-1px);
      border-color: rgba(79,195,247,.5);
      box-shadow: 0 0 18px rgba(79,195,247,.11);
    }
    details[open] { border-color: rgba(212,175,55,.44); }
    summary {
      cursor: pointer;
      list-style: none;
      padding: 14px;
      display: grid;
      gap: 8px;
    }
    summary::-webkit-details-marker { display: none; }
    .quest-name {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      font-weight: 800;
      color: #f7fbff;
    }
    .small { color: var(--muted); font-size: 12px; }
    .body { padding: 0 14px 14px; }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      color: #eaf7ff;
      background: rgba(0,0,0,.3);
      border: 1px solid rgba(79,195,247,.16);
      border-radius: 6px;
      padding: 10px;
      max-height: 300px;
      overflow: auto;
      font: 12px/1.45 Consolas, "Cascadia Mono", monospace;
    }
    .pill {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      border: 1px solid rgba(212,175,55,.28);
      background: rgba(212,175,55,.09);
      color: var(--gold-soft);
      font-size: 12px;
    }
    .diff {
      border-color: rgba(212,175,55,.35);
      color: #f9f1d0;
    }
    .chain {
      display: grid;
      grid-template-columns: repeat(6, minmax(120px, 1fr));
      align-items: stretch;
      gap: 0;
      padding: 14px 8px 8px;
    }
    .rune {
      position: relative;
      min-height: 132px;
      margin: 0 8px;
      border: 1px solid rgba(79,195,247,.32);
      border-radius: 10px;
      padding: 13px 12px;
      background:
        radial-gradient(circle at top, rgba(79,195,247,.14), transparent 42%),
        linear-gradient(180deg, rgba(23,34,56,.86), rgba(7,10,20,.86));
      transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
      display: grid;
      align-content: center;
      justify-items: center;
      text-align: center;
    }
    .rune:hover {
      transform: translateY(-4px) scale(1.025);
      border-color: rgba(79,195,247,.68);
      box-shadow: 0 0 20px rgba(79,195,247,.18);
    }
    .rune:not(:last-child)::after {
      content: "";
      position: absolute;
      right: -17px;
      top: 50%;
      width: 18px;
      height: 1px;
      background: linear-gradient(90deg, var(--ice), transparent);
      box-shadow: 0 0 10px var(--ice);
      z-index: 2;
    }
    .rune-glyph {
      width: 46px;
      height: 46px;
      display: grid;
      place-items: center;
      margin-bottom: 9px;
      border: 1px solid rgba(212,175,55,.42);
      border-radius: 50%;
      color: var(--gold-soft);
      font-family: Georgia, "Times New Roman", serif;
      font-size: 22px;
      font-weight: 900;
      text-shadow: 0 0 16px rgba(212,175,55,.42);
      box-shadow: inset 0 0 18px rgba(212,175,55,.07), 0 0 18px rgba(79,195,247,.1);
    }
    .rune-type { color: var(--ice); font-weight: 800; font-size: 13px; }
    .rune-id { color: var(--dim); font-size: 11px; margin-top: 5px; }
    .audit-ledger { margin-top: 14px; }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .summary-stat {
      border: 1px solid rgba(212,175,55,.18);
      border-radius: 7px;
      padding: 9px;
      background: rgba(0,0,0,.18);
    }
    .summary-stat strong {
      display: block;
      color: #fff;
      font-size: 18px;
    }
    .journal {
      border-color: rgba(216,193,144,.3);
      background:
        linear-gradient(180deg, rgba(49,39,24,.36), rgba(12,18,34,.88)),
        repeating-linear-gradient(0deg, rgba(216,193,144,.035), rgba(216,193,144,.035) 1px, transparent 1px, transparent 24px);
    }
    .empty {
      color: var(--muted);
      padding: 22px;
      border: 1px dashed rgba(212,175,55,.25);
      border-radius: 8px;
      background: rgba(0,0,0,.18);
    }
    .fade-in {
      animation: rise .34s ease both;
      transform-origin: center top;
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(8px) scale(.995); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    @media (max-width: 980px) {
      .composer { grid-template-columns: 1fr; }
      .composer-row { grid-template-columns: 1fr; }
      .composer-status { grid-column: 1; }
      .hero, .arb-grid { grid-template-columns: 1fr; }
      .seal { justify-self: stretch; }
      .stats, .agent-grid, .tool-grid, .memory-grid { grid-template-columns: 1fr; }
      .chain { grid-template-columns: 1fr; gap: 12px; }
      .rune:not(:last-child)::after { display: none; }
      .summary-grid { grid-template-columns: 1fr; }
      .topbar { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <h1>OmniBot &bull; Visible Arbiter</h1>
        <div class="subtitle" id="currentTitle">Awaiting latest trace...</div>
      </div>
      <div class="controls">
        <select id="traceSelect" onchange="selectTrace(this.value)" aria-label="Recent traces"></select>
        <button onclick="loadTraces()">Refresh</button>
      </div>
    </header>
    <section class="composer">
      <div class="composer-head">
        <span><span class="sigil">RQ</span> Request Console</span>
        <span class="small">Run OmniBot and open the trace here.</span>
      </div>
      <div class="composer-row">
        <textarea id="requestInput">Look at the file examples/broken_test/test.py and tell me why the tests are failing, then propose a fix.</textarea>
        <button class="run-button" id="runButton" onclick="submitRequest()">Run Trace</button>
      </div>
      <div class="composer-status" id="composerStatus"></div>
    </section>
    <main id="app"><div class="empty">Loading traces...</div></main>
  </div>
  <script>
    let traces = [];
    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
    }
    function short(value, n = 12) {
      const s = String(value || '');
      return s.length > n ? s.slice(0, n) : s;
    }
    function pct(value) {
      const n = Number(value || 0);
      return Math.max(0, Math.min(1, n));
    }
    function tier(value, inverted = false) {
      const n = inverted ? 1 - pct(value) : pct(value);
      if (n >= .75) return 'green';
      if (n >= .45) return 'gold';
      return 'red';
    }
    function metric(label, value, inverted = false) {
      const n = pct(value);
      return `<div class="stat">
        <div class="stat-label">${esc(label)}</div>
        <div class="stat-value"><div class="bar"><span class="${tier(value, inverted)}" style="width:${n * 100}%"></span></div><div class="score-num">${n.toFixed(2)}</div></div>
      </div>`;
    }
    function formatTime(ts) {
      if (!ts) return 'timestamp unavailable';
      try { return new Date(ts).toLocaleString(); } catch { return ts; }
    }
    function firstLine(value, limit = 92) {
      const s = String(value || '').replace(/\\s+/g, ' ').trim();
      return s.length > limit ? s.slice(0, limit - 3) + '...' : s;
    }
    function selectedName(arb) {
      return (arb.selected_agents || [])[0] || 'none';
    }
    function rejectedHtml(arb) {
      const rejected = arb.rejected_alternatives || [];
      if (!rejected.length) return '<div class="rejected">No rejected alternatives.</div>';
      return `<div class="rejected">${rejected.map(r => `<span class="pill">${esc(r.agent)}</span> ${esc(r.reason || '')}`).join('<br>')}</div>`;
    }
    function evidencePreview(items) {
      const joined = (items || []).join(' ');
      return firstLine(joined, 150) || 'No evidence preview recorded.';
    }
    function agentCard(a) {
      const evidence = (a.evidence || []).join('\\n\\n---\\n\\n');
      const artifacts = (a.artifacts || []).map(x => `${x.type}: ${x.path}\\n${x.content || ''}`).join('\\n\\n');
      return `<details>
        <summary>
          <div class="quest-name"><span><span class="sigil">${esc((a.agent_name || '?').slice(0,2).toUpperCase())}</span> ${esc(a.agent_name || 'agent')}</span><span class="pill">${Number(a.confidence || 0).toFixed(2)}</span></div>
          <div class="small">${esc(a.summary || '')}</div>
          <div class="summary-grid">
            <div class="summary-stat"><strong>${(a.evidence || []).length}</strong><span class="small">evidence</span></div>
            <div class="summary-stat"><strong>${(a.sources || []).length}</strong><span class="small">sources</span></div>
            <div class="summary-stat"><strong>${(a.tool_calls || []).length}</strong><span class="small">tools</span></div>
          </div>
          <div class="small">${esc(evidencePreview(a.evidence))}</div>
        </summary>
        <div class="body">
          <pre>${esc(evidence || 'No raw evidence recorded.')}</pre>
          ${artifacts ? `<p class="small">Artifacts</p><pre class="diff">${esc(artifacts)}</pre>` : ''}
        </div>
      </details>`;
    }
    function toolCard(t) {
      const result = t.result || {};
      const status = result.status || 'done';
      const summary = result.error || result.summary || result.stdout || result.stderr || JSON.stringify(result);
      return `<details>
        <summary>
          <div class="quest-name"><span><span class="sigil">TL</span> ${esc(t.tool_name || 'tool')}</span><span class="pill">${esc(status)}</span></div>
          <div class="small">${esc(firstLine(summary, 150))}</div>
        </summary>
        <div class="body"><pre>${esc(JSON.stringify(result, null, 2))}</pre></div>
      </details>`;
    }
    function artifactCard(a) {
      return `<details open>
        <summary><div class="quest-name"><span><span class="sigil">DF</span> ${esc(a.path || 'artifact')}</span><span class="pill">${esc(a.artifact_type || 'artifact')}</span></div></summary>
        <div class="body"><pre class="diff">${esc(a.content || '')}</pre></div>
      </details>`;
    }
    function memoryCard(m) {
      return `<details class="journal">
        <summary><div class="quest-name"><span><span class="sigil">ME</span> ${esc(m.kind || 'memory')}</span><span class="pill">${Number(m.confidence || 0).toFixed(2)}</span></div><div class="small">${esc(m.memory_id || '')}</div></summary>
        <div class="body"><pre>${esc(m.content || JSON.stringify(m, null, 2))}</pre><div class="small">provenance: ${esc(m.source_event_id || '')}</div></div>
      </details>`;
    }
    function chainNode(e) {
      const label = e.label || e.type.replace('.', ' ');
      return `<div class="rune" title="parents: ${(e.parents || []).join(', ') || 'none'}\\n${e.audit_hash || ''}">
        <div class="rune-glyph">${esc(e.glyph || 'X')}</div>
        <div class="rune-type">${esc(label)}</div>
        <div class="rune-id">${esc(e.detail || short(e.event_id, 14))}</div>
      </div>`;
    }
    function phaseChain(trace) {
      const agents = trace.agents || [];
      const tools = trace.tools || [];
      const memories = trace.memory_writes || [];
      const chain = trace.causal_chain || [];
      return [
        {glyph:'I', label:'Invocation', detail:'user request', parents:[], audit_hash:(chain[0] || {}).audit_hash},
        {glyph:'A', label:'Agents', detail:`${agents.length} parallel`, parents:[], audit_hash:''},
        {glyph:'T', label:'Tools', detail:`${tools.length} calls`, parents:[], audit_hash:''},
        {glyph:'J', label:'Judgment', detail:`${selectedName(trace.arbiter || {})}`, parents:[], audit_hash:''},
        {glyph:'M', label:'Memory', detail:`${memories.length} writes`, parents:[], audit_hash:''},
        {glyph:'R', label:'Response', detail: trace.status || 'done', parents:[], audit_hash:(chain[chain.length - 1] || {}).audit_hash},
      ];
    }
    function renderTrace(trace) {
      const arb = trace.arbiter || {};
      const score = arb.coherence_score || {};
      document.getElementById('currentTitle').textContent = `${firstLine(trace.request || 'No request')} | ${formatTime(trace.timestamp)}`;
      const high = Number(score.overall || 0) >= .75 ? ' high' : '';
      const agents = (trace.agents || []).map(agentCard).join('') || '<div class="empty">No agents have completed.</div>';
      const tools = (trace.tools || []).map(toolCard).join('') || '<div class="empty">No tool calls recorded.</div>';
      const artifacts = (trace.artifacts || []).map(artifactCard).join('') || '<div class="empty">No patch artifacts for this trace.</div>';
      const memories = (trace.memory_writes || []).map(memoryCard).join('') || '<div class="empty">No memory writes recorded.</div>';
      const chain = phaseChain(trace).map(chainNode).join('');
      const audit = (trace.causal_chain || []).map(e => `${e.type} ${e.event_id}\\n  parents: ${(e.parents || []).join(', ') || '(none)'}\\n  ${e.audit_hash}`).join('\\n\\n');
      return `<div class="chapter fade-in">
        <section class="hero">
          <div>
            <p class="task-title">${esc(trace.request || 'Request unavailable')}</p>
            <div class="meta-row"><span class="pill">${esc(trace.status || 'unknown')}</span><span>${esc(trace.task_id)}</span><span>${esc(formatTime(trace.timestamp))}</span></div>
          </div>
          <div class="seal"><div class="small">Overall Coherence</div><div class="overall">${Number(score.overall || 0).toFixed(2)}</div><div class="small">${esc((score.notes || [])[0] || 'trace ready')}</div></div>
        </section>
        <section class="panel">
          <h2 class="panel-title"><span class="sigil">CS</span><span>Coherence Score</span></h2>
          <div class="stats">
            ${metric('Evidence coverage', score.evidence_coverage)}
            ${metric('Agent agreement', score.agent_agreement)}
            ${metric('Tool provenance', score.tool_provenance)}
            ${metric('Confidence spread', score.confidence_spread)}
            ${metric('Unresolved risk', score.unresolved_risk, true)}
          </div>
        </section>
        <section class="panel arbiter${high}">
          <h2 class="panel-title"><span class="sigil">AR</span><span>Arbiter Decision</span></h2>
          <div class="arb-grid">
            <div>
              <div class="callout">${esc(arb.final_answer || 'No final answer recorded.').split('\\n').slice(0, 8).join('\\n')}</div>
              <p><span class="pill">chosen: ${esc(selectedName(arb))}</span> <span class="pill">confidence: ${Number(arb.confidence || 0).toFixed(2)}</span></p>
              ${rejectedHtml(arb)}
            </div>
            <details>
              <summary><div class="quest-name"><span>Why this answer?</span><span class="pill">open</span></div><div class="small">Full arbiter rationale and rejected alternatives.</div></summary>
              <div class="body"><pre>${esc(arb.rationale || '')}\\n\\n${esc(JSON.stringify(arb.rejected_alternatives || [], null, 2))}</pre></div>
            </details>
          </div>
        </section>
        <section class="panel">
          <h2 class="panel-title"><span class="sigil">AG</span><span>Agent Execution Trace</span></h2>
          <div class="agent-grid">${agents}</div>
        </section>
        <section class="panel">
          <h2 class="panel-title"><span class="sigil">TA</span><span>Tool Calls & Artifacts</span></h2>
          <div class="tool-grid">${tools}${artifacts}</div>
        </section>
        <section class="panel">
          <h2 class="panel-title"><span class="sigil">CC</span><span>Causal Chain</span></h2>
          <div class="chain">${chain || '<div class="empty">No causal chain recorded.</div>'}</div>
          <details class="audit-ledger">
            <summary><div class="quest-name"><span>Audit ledger</span><span class="pill">${(trace.causal_chain || []).length} events</span></div><div class="small">Full causal parent and audit hash record.</div></summary>
            <div class="body"><pre>${esc(audit)}</pre></div>
          </details>
        </section>
        <section class="panel journal">
          <h2 class="panel-title"><span class="sigil">MI</span><span>Memory Impact</span></h2>
          <div class="memory-grid">${memories}</div>
        </section>
      </div>`;
    }
    function selectTrace(taskId) {
      const trace = traces.find(t => t.task_id === taskId) || traces[0];
      document.getElementById('app').innerHTML = trace ? renderTrace(trace) : '<div class="empty">No trace selected.</div>';
    }
    async function loadTraces() {
      const app = document.getElementById('app');
      const res = await fetch('/api/traces');
      traces = await res.json();
      traces.sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || '')));
      const select = document.getElementById('traceSelect');
      select.innerHTML = traces.map(t => `<option value="${esc(t.task_id)}">${esc(firstLine(t.request || t.task_id, 54))}</option>`).join('');
      app.innerHTML = traces.length ? renderTrace(traces[0]) : '<div class="empty">No task traces yet. POST to /chat or run the README demo.</div>';
    }
    async function submitRequest() {
      const input = document.getElementById('requestInput');
      const button = document.getElementById('runButton');
      const status = document.getElementById('composerStatus');
      const message = input.value.trim();
      if (!message) {
        status.textContent = 'Enter a request first.';
        return;
      }
      button.disabled = true;
      button.textContent = 'Working...';
      status.textContent = 'Agents are running. The arbiter will choose a trace when they finish.';
      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({message})
        });
        if (!res.ok) throw new Error(`Request failed: ${res.status}`);
        const result = await res.json();
        status.textContent = `Trace complete: ${result.task_id}`;
        await loadTraces();
        selectTrace(result.task_id);
        document.getElementById('traceSelect').value = result.task_id;
      } catch (err) {
        status.textContent = err.message || String(err);
      } finally {
        button.disabled = false;
        button.textContent = 'Run Trace';
      }
    }
    loadTraces();
  </script>
</body>
</html>
"""
