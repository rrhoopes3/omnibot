from __future__ import annotations

from pathlib import Path

import pytest

from omnibot.core.event_bus import EventBus
from omnibot.core.tool_bus import ToolBus


@pytest.mark.anyio
async def test_tool_manifest_and_shell_toggle(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OMNIBOT_ENABLE_SHELL", "false")
    monkeypatch.setenv("OMNIBOT_ENABLE_PYTHON", "false")
    bus_events = EventBus(tmp_path / "tools.db")
    await bus_events.init()
    tools = ToolBus(bus_events, tmp_path)

    manifest = tools.manifest()
    by_name = {tool["name"]: tool for tool in manifest["tools"]}

    assert manifest["workspace"] == str(tmp_path.resolve())
    assert manifest["sandbox"]["hard_container"] is False
    assert by_name["run_command"]["enabled"] is False
    assert by_name["run_python"]["enabled"] is False
    assert by_name["read_file"]["enabled"] is True

    result = await tools.execute(
        "run_command",
        {"command": "echo hello"},
        task_id="task_test",
    )

    assert result["status"] == "blocked"
    assert "disabled" in result["error"]
