from __future__ import annotations

import re

from omnibot.core.agent_runtime import AgentContext, BaseAgent, referenced_paths
from omnibot.schemas.events import AgentResult


class CoderAgent(BaseAgent):
    name = "coder"
    role = "code_diagnosis"

    async def _run(self, ctx: AgentContext) -> AgentResult:
        paths = referenced_paths(ctx.request)
        evidence: list[str] = []
        sources: list[str] = []
        tool_calls: list[str] = []

        for path in paths[:3]:
            read = await ctx.tools.execute(
                "read_file",
                {"path": path},
                task_id=ctx.task_id,
                causal_parent_ids=[ctx.parent_event_id],
                actor=self.name,
            )
            tool_calls.append("read_file")
            if read.get("status") == "ok":
                sources.append(str(read.get("path", path)))
                content = str(read.get("content", ""))
                evidence.append(f"{path}:\n{content[:2000]}")
            else:
                evidence.append(f"{path}: {read.get('error')}")

        should_run_tests = bool(re.search(r"\b(test|pytest|failing|fail)\b", ctx.request, re.I))
        if should_run_tests:
            result = await ctx.tools.execute(
                "run_command",
                {"command": "python -m pytest -q"},
                task_id=ctx.task_id,
                causal_parent_ids=[ctx.parent_event_id],
                actor=self.name,
            )
            tool_calls.append("run_command")
            evidence.append(
                "pytest result:\n"
                f"returncode={result.get('returncode')}\n"
                f"stdout={result.get('stdout', '')[:3000]}\n"
                f"stderr={result.get('stderr', '')[:1500]}"
            )
            sources.append("tool:python -m pytest -q")

        if not paths:
            listing = await ctx.tools.execute(
                "list_directory",
                {"path": "."},
                task_id=ctx.task_id,
                causal_parent_ids=[ctx.parent_event_id],
                actor=self.name,
            )
            tool_calls.append("list_directory")
            evidence.append(f"workspace listing: {listing}")
            sources.append("workspace listing")

        summary = "Read referenced files and ran tests when requested."
        if should_run_tests:
            summary += " Test output is included for arbitration."
        return AgentResult(
            agent_name=self.name,
            role=self.role,
            summary=summary,
            confidence=0.82 if evidence else 0.45,
            sources=sources,
            evidence=evidence,
            tool_calls=tool_calls,
        )
