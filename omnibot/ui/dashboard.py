from __future__ import annotations

from fastapi import APIRouter

from omnibot.core.coordination_kernel import CoordinationKernel


def dashboard_router(kernel: CoordinationKernel) -> APIRouter:
    router = APIRouter()

    @router.get("/api/events")
    async def events(limit: int = 80):
        return [event.model_dump() for event in await kernel.event_bus.recent(limit=limit)]

    @router.get("/api/events/{task_id}")
    async def task_events(task_id: str):
        return [event.model_dump() for event in await kernel.event_bus.replay(task_id=task_id)]

    @router.get("/api/memory")
    async def memory(limit: int = 30):
        return [item.model_dump(exclude={"embedding"}) for item in await kernel.memory.recent(limit=limit)]

    @router.get("/")
    async def index():
        return {
            "name": "OmniBot v0.1 Hello Coherence",
            "surfaces": {
                "chat": "/chat",
                "events": "/api/events",
                "memory": "/api/memory",
            },
        }

    return router
