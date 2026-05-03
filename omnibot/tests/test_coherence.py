from __future__ import annotations

from pathlib import Path

import pytest

from omnibot.core.coordination_kernel import CoordinationKernel


@pytest.mark.anyio
async def test_coherence_loop_records_agents_arbiter_and_memory(tmp_path: Path):
    (tmp_path / "test.py").write_text(
        "def add(a, b):\n"
        "    return a - b\n\n"
        "def test_add():\n"
        "    assert add(2, 2) == 4\n",
        encoding="utf-8",
    )
    db = tmp_path / "omnibot.db"
    kernel = CoordinationKernel(db_path=db, workspace=tmp_path)
    await kernel.init()

    result = await kernel.handle_request(
        "Look at the file test.py and tell me why the tests are failing, then propose a fix."
    )

    assert result["task_id"].startswith("task_")
    assert "What I did:" in result["response"]
    assert "Why this answer:" in result["response"]

    events = result["events"]
    event_types = [event["type"] for event in events]
    assert event_types.count("agent.completed") == 3
    assert "arbiter.decided" in event_types
    assert "artifact.created" in event_types
    assert "memory.written" in event_types
    assert "presence.responded" in event_types

    decision = result["decision"]
    assert "coder" in decision["selected_agents"]
    assert decision["confidence"] > 0
    assert decision["rationale"]
    assert decision["coherence_score"]["overall"] > 0

    artifact_events = [event for event in events if event["type"] == "artifact.created"]
    assert artifact_events
    assert "return a + b" in artifact_events[0]["payload"]["content"]

    tool_events = [event for event in events if event["type"] == "tool.completed"]
    test_runs = [
        event for event in tool_events
        if event["payload"].get("tool_name") == "run_command"
    ]
    assert test_runs
    assert test_runs[0]["payload"]["result"]["returncode"] == 1


@pytest.mark.anyio
async def test_event_audit_hashes_and_causal_parents_are_visible(tmp_path: Path):
    (tmp_path / "test.py").write_text(
        "def add(a, b):\n"
        "    return a - b\n\n"
        "def test_add():\n"
        "    assert add(2, 2) == 4\n",
        encoding="utf-8",
    )
    kernel = CoordinationKernel(db_path=tmp_path / "omnibot.db", workspace=tmp_path)
    await kernel.init()

    await kernel.handle_request(
        "Look at the file test.py and tell me why the tests are failing, then propose a fix."
    )

    events = await kernel.event_bus.recent(limit=200)
    by_id = {event.event_id: event for event in events}
    assert events

    for event in events:
        assert event.audit_hash == kernel.event_bus._hash_event(event)
        for parent_id in event.causal_parent_ids:
            assert parent_id in by_id
