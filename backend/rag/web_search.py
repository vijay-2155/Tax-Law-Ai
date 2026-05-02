"""
DDG-based web search for Indian Income Tax law.
Always runs as a supplement to vector retrieval for recency and circulars.
"""
from __future__ import annotations

import asyncio
from typing import Any


def _sync_search(query: str, max_results: int) -> list[dict[str, Any]]:
    from ddgs import DDGS
    search_query = f"{query} Indian income tax"
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(search_query, max_results=max_results, region="in-en"))
    except Exception:
        return []


async def web_search_tax(query: str, max_results: int = 4) -> list[dict[str, Any]]:
    """Async DDG search returning list of {title, href, body} dicts."""
    return await asyncio.to_thread(_sync_search, query, max_results)


def web_results_to_chunks(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert DDG results into pseudo-chunks compatible with build_context_prompt."""
    chunks = []
    for r in results:
        if not r.get("body"):
            continue
        chunks.append({
            "section": None,
            "section_title": r.get("title", "Web Result"),
            "act_year": "web",
            "chapter_title": "",
            "income_head": "",
            "chunk_type": "web",
            "text": r.get("body", ""),
            "url": r.get("href", ""),
            "score": 0.0,
        })
    return chunks
