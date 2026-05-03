from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from omnibot.core.coordination_kernel import CoordinationKernel


class ChatRequest(BaseModel):
    message: str


def chat_router(kernel: CoordinationKernel) -> APIRouter:
    router = APIRouter()

    @router.post("/chat")
    async def chat(payload: ChatRequest):
        return await kernel.handle_request(payload.message)

    return router


def launch_gradio(kernel: CoordinationKernel):
    """Optional Gradio surface for quick local demos."""
    try:
        import gradio as gr
    except Exception as exc:
        raise RuntimeError("Install gradio to use --gradio") from exc

    async def respond(message: str):
        result = await kernel.handle_request(message)
        return result["response"]

    demo = gr.Interface(fn=respond, inputs="text", outputs="text", title="OmniBot v0.1")
    demo.launch()
