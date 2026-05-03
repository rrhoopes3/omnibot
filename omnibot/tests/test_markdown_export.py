from __future__ import annotations

from omnibot.ui.dashboard import _export_filename, _trace_to_markdown


def test_trace_markdown_export_has_intelligent_name_and_debug_sections():
    trace = {
        "task_id": "task_1234567890abcdef",
        "request": "Look at the file test.py and tell me why the tests are failing, then propose a fix.",
        "timestamp": "2026-05-03T20:00:00Z",
        "status": "done",
        "arbiter": {
            "final_answer": "The test fails because add subtracts instead of adding.",
            "selected_agents": ["coder"],
            "confidence": 0.8,
            "rationale": "Coder had direct file and test evidence.",
            "coherence_score": {
                "overall": 0.72,
                "evidence_coverage": 0.67,
                "agent_agreement": 0.45,
                "tool_provenance": 1.0,
                "confidence_spread": 0.6,
                "unresolved_risk": 0.15,
            },
        },
        "agents": [],
        "tools": [],
        "artifacts": [
            {
                "path": "test.py",
                "content": "--- test.py\n+++ test.py\n-return a - b\n+return a + b\n",
            }
        ],
        "memory_writes": [],
        "causal_chain": [],
    }

    filename = _export_filename(trace)
    markdown = _trace_to_markdown(trace)

    assert filename == "2026-05-03-omnibot-file-test-py-tests-failing-propose-fix-90abcdef.md"
    assert "# OmniBot Debug Report" in markdown
    assert "## Patch Artifacts" in markdown
    assert "return a + b" in markdown
    assert "## Audit Ledger" in markdown
