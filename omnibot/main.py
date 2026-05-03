from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from omnibot.core.coordination_kernel import CoordinationKernel
from omnibot.ui.chat import chat_router, launch_gradio
from omnibot.ui.dashboard import dashboard_router


async def run_cli(args: argparse.Namespace) -> None:
    kernel = CoordinationKernel(db_path=args.db, workspace=args.workspace)
    await kernel.init()
    result = await kernel.handle_request(args.message)
    print(result["response"])
    print(f"\nTask: {result['task_id']}")
    print("Dashboard events: run `python -m omnibot.main web` and open /api/events")


async def build_app(db_path: str, workspace: str) -> FastAPI:
    kernel = CoordinationKernel(db_path=db_path, workspace=workspace)
    await kernel.init()
    app = FastAPI(title="OmniBot v0.1 Hello Coherence")
    app.include_router(chat_router(kernel))
    app.include_router(dashboard_router(kernel))
    return app


def create_app(db_path: str = "omnibot.db", workspace: str = ".") -> FastAPI:
    return asyncio.run(build_app(db_path, workspace))


def main() -> None:
    parser = argparse.ArgumentParser(description="OmniBot v0.1 Hello Coherence")
    parser.add_argument("--db", default="omnibot.db")
    parser.add_argument("--workspace", default=str(Path.cwd()))
    sub = parser.add_subparsers(dest="command")

    chat = sub.add_parser("ask", help="Run one CLI request")
    chat.add_argument("message")

    web = sub.add_parser("web", help="Run FastAPI chat + dashboard")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", default=8000, type=int)

    sub.add_parser("gradio", help="Run optional Gradio chat surface")

    args = parser.parse_args()
    if args.command == "ask":
        asyncio.run(run_cli(args))
    elif args.command == "gradio":
        kernel = CoordinationKernel(db_path=args.db, workspace=args.workspace)
        asyncio.run(kernel.init())
        launch_gradio(kernel)
    else:
        uvicorn.run(
            "omnibot.main:create_app",
            factory=True,
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8000),
        )


if __name__ == "__main__":
    main()
