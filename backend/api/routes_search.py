"""
Search API routes.

GET /api/sections/search?q=...&act=2025&top_k=10
GET /api/sections/autocomplete?q=...&act=2025
"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/sections/search")
async def search_sections(
    request: Request,
    q: str = Query(..., min_length=1),
    act: str = Query("2025", pattern="^(1961|2025|both)$"),
    top_k: int = Query(10, ge=1, le=50),
    income_head: str | None = Query(None),
    chunk_type: str | None = Query(None),
) -> dict[str, Any]:
    """
    Full-text + vector search across sections.
    Returns chunks ranked by relevance score.
    """
    retriever = request.app.state.retriever
    cross_act = act == "both"
    act_year = None if cross_act else act

    results = retriever.retrieve(
        query=q,
        act_year=act_year,
        top_k=top_k,
        cross_act=cross_act,
        income_head=income_head,
        chunk_type=chunk_type,
    )

    # Group by section for cleaner display
    sections: dict[str, dict[str, Any]] = {}
    for chunk in results:
        key = f"{chunk.get('act_year')}_{chunk.get('section')}"
        if key not in sections:
            sections[key] = {
                "section": chunk.get("section"),
                "section_title": chunk.get("section_title"),
                "act_year": chunk.get("act_year"),
                "chapter": chunk.get("chapter"),
                "chapter_title": chunk.get("chapter_title"),
                "income_head": chunk.get("income_head"),
                "score": round(chunk.get("score", 0), 3),
                "preview": chunk.get("text", "")[:300],
                "page_start": chunk.get("page_start"),
            }
        else:
            # Keep highest score
            if chunk.get("score", 0) > sections[key]["score"]:
                sections[key]["score"] = round(chunk.get("score", 0), 3)

    return {
        "query": q,
        "act": act,
        "total": len(sections),
        "results": list(sections.values()),
    }


@router.get("/sections/autocomplete")
async def autocomplete(
    request: Request,
    q: str = Query(..., min_length=2),
    act: str = Query("2025", pattern="^(1961|2025|both)$"),
) -> dict[str, Any]:
    """
    Fast autocomplete using Qdrant scroll — returns section numbers + titles matching query.
    """
    store = request.app.state.store
    acts = ["2025", "1961"] if act == "both" else [act]

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for act_year in acts:
        # Try exact section number first
        import re
        m = re.match(r"^\d+[A-Z]*$", q.strip().upper())
        if m:
            chunks = store.search_by_section(q.strip().upper(), act_year)
            for c in chunks[:3]:
                key = f"{act_year}_{c.get('section')}"
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "section": c.get("section"),
                        "section_title": c.get("section_title"),
                        "act_year": act_year,
                        "income_head": c.get("income_head"),
                        "match_type": "section_number",
                    })
        else:
            # Vector search for title matching
            from ..indexing.embedder import embed_query
            qv = embed_query(q)
            chunks = store.search(qv, act_year=act_year, top_k=5)
            for c in chunks:
                key = f"{act_year}_{c.get('section')}"
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "section": c.get("section"),
                        "section_title": c.get("section_title"),
                        "act_year": act_year,
                        "income_head": c.get("income_head"),
                        "match_type": "semantic",
                    })

    return {"suggestions": results[:10]}
