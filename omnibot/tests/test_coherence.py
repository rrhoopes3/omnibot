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
    assert "memory.written" in event_types
    assert "presence.responded" in event_types

    decision = result["decision"]
    assert "coder" in decision["selected_agents"]
    assert decision["confidence"] > 0
    assert decision["rationale"]
