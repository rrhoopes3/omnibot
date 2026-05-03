from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib import parse, request

from omnibot.core.event_bus import EventBus

ToolHandler = Callable[..., Awaitable[dict[str, Any]] | dict[str, Any]]

TOOL_CATEGORIES = {
    "filesystem": {"read_file", "list_directory", "find_files"},
    "shell": {"run_command"},
    "python": {"run_python"},
    "browser": {"web_search"},
}

CORE_TOOLS = {"read_file", "list_directory", "find_files", "run_command", "run_python"}

_TOOL_METADATA = {
    "read_file": {"category": "filesystem", "risk": "low", "sandbox": "workspace path scoped"},
    "list_directory": {"category": "filesystem", "risk": "low", "sandbox": "workspace path scoped"},
    "find_files": {"category": "filesystem", "risk": "low", "sandbox": "workspace path scoped"},
    "web_search": {"category": "browser", "risk": "low", "sandbox": "network request only"},
    "run_command": {"category": "shell", "risk": "high", "sandbox": "workspace cwd + guardrails"},
    "run_python": {"category": "python", "risk": "high", "sandbox": "workspace cwd + guardrails"},
}

_TASK_TOOL_HINTS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\b(test|pytest|python|stack trace|traceback|failing|bug)\b", re.I), ["filesystem", "shell", "python"]),
    (re.compile(r"\b(file|read|directory|folder|code)\b", re.I), ["filesystem"]),
    (re.compile(r"\b(search|web|docs|research|latest)\b", re.I), ["browser"]),
]

_DANGEROUS_COMMANDS = [
    r"\brm\s+-rf\s+/",
    r"\bRemove-Item\b.*\s-Recurse\b.*\s-Force\b",
    r"\bmkfs\b",
    r"\bcurl\b.*\|\s*\bbash\b",
    r"\bwget\b.*\|\s*\bbash\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bformat\b\s+[A-Z]:",
]

_SENSITIVE_PATHS = [
    r"\.ssh[/\\]id_",
    r"\.env\.prod",
    r"\.env\.production",
    r"\.aws[/\\]credentials",
    r"\.kube[/\\]config",
    r"private[_-]?key",
]


class ToolBus:
    """Provider-neutral tool registry with scoped execution and event logging.

    Cherry-picked + adapted from Grok-Party-Pack: forge/tools/registry.py,
    forge/tools/filesystem.py, forge/tools/shell.py, forge/tools/python_repl.py,
    and forge/guardrails.py.
    """

    def __init__(self, event_bus: EventBus, workspace: str | Path):
        self.event_bus = event_bus
        self.workspace = Path(workspace).resolve()
        self.enable_shell = _env_flag("OMNIBOT_ENABLE_SHELL", default=True)
        self.enable_python = _env_flag("OMNIBOT_ENABLE_PYTHON", default=True)
        self._handlers: dict[str, ToolHandler] = {}
        self._schemas: dict[str, dict[str, Any]] = {}
        self._register_builtin_tools()

    def register(self, name: str, description: str, parameters: dict[str, Any], handler: ToolHandler) -> None:
        self._handlers[name] = handler
        self._schemas[name] = {"name": name, "description": description, "parameters": parameters}

    def infer_tools_for_task(self, task: str) -> set[str]:
        categories: list[str] = []
        for pattern, hints in _TASK_TOOL_HINTS:
            if pattern.search(task):
                categories.extend(hints)
        tools = set(CORE_TOOLS)
        for category in categories:
            tools.update(TOOL_CATEGORIES.get(category, set()))
        return tools

    def schemas(self, only: set[str] | None = None) -> list[dict[str, Any]]:
        if only is None:
            return list(self._schemas.values())
        return [schema for name, schema in self._schemas.items() if name in only]

    def manifest(self) -> dict[str, Any]:
        tools = []
        for name, schema in sorted(self._schemas.items()):
            meta = _TOOL_METADATA.get(name, {})
            tools.append(
                {
                    "name": name,
                    "description": schema["description"],
                    "category": meta.get("category", "other"),
                    "risk": meta.get("risk", "medium"),
                    "sandbox": meta.get("sandbox", "event logged"),
                    "enabled": self._tool_enabled(name),
                }
            )
        return {
            "workspace": str(self.workspace),
            "sandbox": {
                "type": "workspace-scoped subprocess guardrails",
                "hard_container": False,
                "path_scope": "filesystem tools are restricted to workspace",
                "shell_scope": "shell/python run with cwd set to workspace when enabled",
                "guardrails": {
                    "dangerous_command_patterns": len(_DANGEROUS_COMMANDS),
                    "sensitive_path_patterns": len(_SENSITIVE_PATHS),
                },
            },
            "toggles": {
                "OMNIBOT_ENABLE_SHELL": self.enable_shell,
                "OMNIBOT_ENABLE_PYTHON": self.enable_python,
            },
            "tools": tools,
        }

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        task_id: str,
        causal_parent_ids: list[str] | None = None,
        actor: str = "tool_bus",
    ) -> dict[str, Any]:
        arguments = arguments or {}
        start = await self.event_bus.emit(
            "tool.called",
            actor=actor,
            source="tool_bus",
            task_id=task_id,
            causal_parent_ids=causal_parent_ids or [],
            payload={"tool_name": name, "arguments": self._safe_args(arguments)},
        )

        blocked = self._guardrail_block(name, arguments)
        if blocked:
            result = {"status": "blocked", "error": blocked}
            await self.event_bus.emit(
                "tool.completed",
                actor=actor,
                source="tool_bus",
                task_id=task_id,
                causal_parent_ids=[start.event_id],
                payload={"tool_name": name, "result": result},
            )
            return result

        handler = self._handlers.get(name)
        if handler is None:
            result = {"status": "failed", "error": f"Unknown tool: {name}"}
        else:
            try:
                maybe = handler(**arguments)
                result = await maybe if asyncio.iscoroutine(maybe) else maybe
            except Exception as exc:
                result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

        await self.event_bus.emit(
            "tool.completed",
            actor=actor,
            source="tool_bus",
            task_id=task_id,
            causal_parent_ids=[start.event_id],
            payload={"tool_name": name, "result": result},
        )
        return result

    def _register_builtin_tools(self) -> None:
        self.register(
            "read_file",
            "Read a UTF-8 text file inside the workspace.",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            self.read_file,
        )
        self.register(
            "list_directory",
            "List files and directories inside the workspace.",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            self.list_directory,
        )
        self.register(
            "find_files",
            "Find files by glob pattern inside the workspace.",
            {
                "type": "object",
                "properties": {"directory": {"type": "string"}, "pattern": {"type": "string"}},
                "required": ["directory", "pattern"],
            },
            self.find_files,
        )
        self.register(
            "run_command",
            "Run a shell command in the workspace with timeout and truncation.",
            {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
            self.run_command,
        )
        self.register(
            "run_python",
            "Run a short Python snippet in the workspace.",
            {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            self.run_python,
        )
        self.register(
            "web_search",
            "Search the web through Tavily, Brave, or DuckDuckGo Instant Answer fallback.",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            self.web_search,
        )

    async def read_file(self, path: str) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.exists():
            return {"status": "failed", "error": f"File not found: {path}"}
        if not target.is_file():
            return {"status": "failed", "error": f"Not a file: {path}"}
        text = target.read_text(encoding="utf-8", errors="replace")
        return {"status": "ok", "path": str(target), "content": text[:12000], "truncated": len(text) > 12000}

    async def list_directory(self, path: str = ".") -> dict[str, Any]:
        target = self._resolve(path)
        entries = [
            {"name": item.name, "type": "dir" if item.is_dir() else "file", "size": item.stat().st_size if item.is_file() else None}
            for item in sorted(target.iterdir())
        ]
        return {"status": "ok", "path": str(target), "entries": entries}

    async def find_files(self, directory: str = ".", pattern: str = "*") -> dict[str, Any]:
        root = self._resolve(directory)
        matches = [str(path) for path in root.rglob(pattern) if path.is_file()]
        return {"status": "ok", "matches": matches[:200], "truncated": len(matches) > 200}

    async def run_command(self, command: str) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            return {"status": "failed", "error": "Command timed out after 30s", "command": command}
        return {
            "status": "ok",
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace")[:8000],
            "stderr": stderr.decode("utf-8", errors="replace")[:4000],
        }

    async def run_python(self, code: str) -> dict[str, Any]:
        escaped = json.dumps(code)
        return await self.run_command(f"python -c {escaped}")

    async def web_search(self, query: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._web_search_sync, query)

    def _web_search_sync(self, query: str) -> dict[str, Any]:
        providers = (self._search_tavily, self._search_brave, self._search_duckduckgo)
        errors = []
        for provider in providers:
            try:
                result = provider(query)
                if result.get("status") == "ok":
                    return result
                if result.get("error"):
                    errors.append(result["error"])
            except Exception as exc:
                errors.append(f"{provider.__name__}: {type(exc).__name__}: {exc}")
        return {
            "status": "failed",
            "query": query,
            "summary": "No web search provider returned usable results.",
            "errors": errors,
        }

    def _search_tavily(self, query: str) -> dict[str, Any]:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return {"status": "skipped", "error": "TAVILY_API_KEY not set"}
        payload = json.dumps(
            {"api_key": api_key, "query": query, "search_depth": "basic", "max_results": 5}
        ).encode("utf-8")
        req = request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", "")[:600],
            }
            for item in data.get("results", [])
        ]
        return {
            "status": "ok",
            "provider": "tavily",
            "query": query,
            "summary": data.get("answer") or self._summarize_results(results),
            "results": results,
        }

    def _search_brave(self, query: str) -> dict[str, Any]:
        api_key = os.getenv("BRAVE_SEARCH_API_KEY")
        if not api_key:
            return {"status": "skipped", "error": "BRAVE_SEARCH_API_KEY not set"}
        url = "https://api.search.brave.com/res/v1/web/search?" + parse.urlencode({"q": query, "count": 5})
        req = request.Request(
            url,
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            method="GET",
        )
        with request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("description", "")[:600],
            }
            for item in data.get("web", {}).get("results", [])
        ]
        return {
            "status": "ok",
            "provider": "brave",
            "query": query,
            "summary": self._summarize_results(results),
            "results": results,
        }

    def _search_duckduckgo(self, query: str) -> dict[str, Any]:
        url = "https://api.duckduckgo.com/?" + parse.urlencode(
            {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        )
        req = request.Request(url, headers={"User-Agent": "OmniBot/0.1.1"}, method="GET")
        with request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        related = data.get("RelatedTopics", [])
        results = []
        for item in related:
            if "Topics" in item:
                item = item["Topics"][0] if item["Topics"] else {}
            if item.get("FirstURL") or item.get("Text"):
                results.append(
                    {
                        "title": item.get("Text", "")[:90],
                        "url": item.get("FirstURL", ""),
                        "content": item.get("Text", "")[:600],
                    }
                )
            if len(results) >= 5:
                break
        abstract = data.get("AbstractText", "")
        return {
            "status": "ok" if abstract or results else "failed",
            "provider": "duckduckgo",
            "query": query,
            "summary": abstract or self._summarize_results(results),
            "results": results,
            "error": "" if abstract or results else "DuckDuckGo returned no abstract/results",
        }

    def _summarize_results(self, results: list[dict[str, str]]) -> str:
        if not results:
            return ""
        return " | ".join(
            f"{item.get('title', 'Untitled')}: {item.get('content', '')[:180]}"
            for item in results[:3]
        )

    def _resolve(self, path: str) -> Path:
        target = (self.workspace / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        target.relative_to(self.workspace)
        return target

    def _guardrail_block(self, name: str, arguments: dict[str, Any]) -> str | None:
        if not self._tool_enabled(name):
            return f"Tool disabled by configuration: {name}"

        if name == "run_command":
            command = str(arguments.get("command", ""))
            for pattern in _DANGEROUS_COMMANDS:
                if re.search(pattern, command, re.IGNORECASE):
                    return f"Blocked dangerous command pattern: {pattern}"

        for key in ("path", "directory"):
            if key in arguments:
                path = str(arguments[key])
                for pattern in _SENSITIVE_PATHS:
                    if re.search(pattern, path, re.IGNORECASE):
                        return f"Blocked sensitive path: {path}"
                try:
                    self._resolve(path)
                except Exception:
                    return f"Blocked path outside workspace: {path}"
        return None

    def _tool_enabled(self, name: str) -> bool:
        if name == "run_command":
            return self.enable_shell
        if name == "run_python":
            return self.enable_python
        return True

    def _safe_args(self, arguments: dict[str, Any]) -> dict[str, Any]:
        safe = dict(arguments)
        for key, value in list(safe.items()):
            if isinstance(value, str) and len(value) > 400:
                safe[key] = value[:400] + "... [truncated]"
        return safe


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
