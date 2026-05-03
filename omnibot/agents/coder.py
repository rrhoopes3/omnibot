from __future__ import annotations

import difflib
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
        artifacts: list[dict] = []
        file_contents: dict[str, str] = {}

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
                file_contents[path] = content
                evidence.append(f"{path}:\n{content[:2000]}")
            else:
                evidence.append(f"{path}: {read.get('error')}")

        should_run_tests = bool(re.search(r"\b(test|pytest|failing|fail)\b", ctx.request, re.I))
        if should_run_tests:
            test_targets = [path for path in paths if "test" in path.lower()]
            test_command = "python -m pytest -q"
            if test_targets:
                test_command = "python -m pytest -q " + " ".join(test_targets[:3])
            result = await ctx.tools.execute(
                "run_command",
                {"command": test_command},
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
            sources.append(f"tool:{test_command}")

        if should_run_tests and file_contents:
            for path, content in file_contents.items():
                patch = self._propose_patch(path, content)
                if patch:
                    artifact_event = await ctx.event_bus.emit(
                        "artifact.created",
                        actor=self.name,
                        source="coder",
                        task_id=ctx.task_id,
                        causal_parent_ids=[ctx.parent_event_id],
                        payload={
                            "artifact_type": "unified_diff",
                            "path": path,
                            "content": patch,
                            "applied": False,
                        },
                    )
                    artifacts.append(
                        {
                            "type": "unified_diff",
                            "path": path,
                            "content": patch,
                            "event_id": artifact_event.event_id,
                            "applied": False,
                        }
                    )
                    evidence.append(f"proposed patch for {path}:\n{patch}")
                    sources.append(f"artifact:{artifact_event.event_id}")

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
            artifacts=artifacts,
        )

    def _propose_patch(self, path: str, content: str) -> str:
        """Return a conservative unified diff artifact for obvious demo failures."""
        replacements = [
            ("return a - b", "return a + b"),
            ("return x - y", "return x + y"),
            ("return left - right", "return left + right"),
        ]
        updated = content
        for before, after in replacements:
            if before in updated:
                updated = updated.replace(before, after, 1)
                break
        if updated == content:
            return ""
        return "".join(
            difflib.unified_diff(
                content.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=path,
                tofile=f"{path} (proposed)",
            )
        )
