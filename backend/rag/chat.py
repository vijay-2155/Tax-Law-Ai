"""
ChatPipeline: thin wrapper around the LangGraph RAG pipeline.

For FastAPI SSE endpoints — use stream().
For simple non-streaming calls — use ask().
"""

from __future__ import annotations
from typing import AsyncIterator, Any

from ..indexing.qdrant_store import QdrantStore
from .llm_provider import LLMConfig
from .graph import stream_rag_response, build_async_rag_graph


class ChatPipeline:
    def __init__(self, store: QdrantStore, config: LLMConfig):
        self.store = store
        self.config = config

    async def stream(
        self,
        query: str,
        act_year: str = "2025",
        history: list[dict[str, str]] | None = None,
        top_k: int = 8,
        cross_act: bool = False,
    ) -> AsyncIterator[str]:
        """
        Stream the RAG response via LangGraph.

        Yields text tokens, followed by a final JSON:
          {"done": true, "sources": [...], "rewritten_question": "..." | null}
        """
        effective_act = "both" if cross_act else act_year
        async for token in stream_rag_response(
            question=query,
            store=self.store,
            config=self.config,
            act_year=effective_act,
            chat_history=history,
            top_k=top_k,
        ):
            yield token

    async def ask(
        self,
        query: str,
        act_year: str = "2025",
        history: list[dict[str, str]] | None = None,
        top_k: int = 8,
        cross_act: bool = False,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Non-streaming: returns (answer, sources)."""
        effective_act = "both" if cross_act else act_year

        graph = build_async_rag_graph(self.store, self.config)
        result = await graph.ainvoke({
            "question": query,
            "act_year": effective_act,
            "chat_history": history or [],
            "retries": 0,
            "chunks": [],
            "search_strategy": "",
            "generation": "",
            "sources": [],
        })

        return result["generation"], result["sources"]
