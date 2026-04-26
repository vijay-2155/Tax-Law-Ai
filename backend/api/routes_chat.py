"""
Chat routes — SSE streaming.

POST /api/chat
Body: { "question": "...", "act_year": "2025", "chat_history": [...] }

Streams: plain text tokens, then final JSON {"done":true,"sources":[...],"rewritten_question":"..."}
"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    act_year: str = "both"          # "1961" | "2025" | "both"
    chat_history: list[dict[str, str]] = []
    top_k: int | None = None


@router.post("/chat")
async def chat(
    request: Request,
    body: ChatRequest,
) -> StreamingResponse:
    """Stream RAG response via SSE-style chunked text."""
    store = request.app.state.store
    llm_config = request.app.state.llm_config

    from ..rag.graph import stream_rag_response

    async def event_stream():
        import json as _json
        try:
            async for chunk in stream_rag_response(
                question=body.question,
                store=store,
                config=llm_config,
                act_year=body.act_year,
                chat_history=body.chat_history or None,
                top_k=body.top_k or llm_config.default_top_k,
            ):
                yield chunk
        except Exception as exc:
            # Yield a terminal error packet so the frontend can display it cleanly
            yield "\n\n" + _json.dumps({"done": True, "error": str(exc), "sources": []})

    return StreamingResponse(
        event_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/sync")
async def chat_sync(
    request: Request,
    body: ChatRequest,
) -> dict[str, Any]:
    """Non-streaming chat — returns full answer + sources in one response."""
    store = request.app.state.store
    llm_config = request.app.state.llm_config

    from ..rag.graph import build_async_rag_graph

    graph = build_async_rag_graph(store, llm_config)
    result = await graph.ainvoke({
        "question": body.question,
        "act_year": body.act_year,
        "chat_history": body.chat_history,
        "retries": 0,
        "chunks": [],
        "search_strategy": "",
        "generation": "",
        "sources": [],
    })

    return {
        "answer": result["generation"],
        "sources": result["sources"],
        "act_year": body.act_year,
    }
