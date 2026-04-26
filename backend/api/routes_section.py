"""
Section detail routes.

GET /api/sections/{act}/{number}          → full section with all chunks
GET /api/sections/{act}/{number}/mapping  → equivalent section in other Act
GET /api/sections/{act}/{number}/summary  → LLM-generated summary (cached)
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

from ..config import DATA_DIR

_SUMMARIES_DIR = DATA_DIR / "summaries"
_EXAMPLES_DIR  = DATA_DIR / "examples"
# section_map lives in the bundle (read-only), not in user data
_SECTION_MAP_PATH = Path(__file__).parent.parent / "data" / "section_map.json"


def _load_section_map() -> dict[str, Any]:
    if _SECTION_MAP_PATH.exists():
        with open(_SECTION_MAP_PATH) as f:
            return json.load(f)
    return {}


@router.get("/sections/{act}/{number}")
async def get_section(
    request: Request,
    act: str,
    number: str,
) -> dict[str, Any]:
    """Return all chunks for a section, sorted by clause path."""
    if act not in ("1961", "2025"):
        raise HTTPException(400, "act must be 1961 or 2025")

    store = request.app.state.store
    chunks = store.search_by_section(number.upper(), act)

    if not chunks:
        raise HTTPException(404, f"Section {number} not found in {act} Act")

    # Build structured response
    first = chunks[0]
    section_data = {
        "section": first.get("section"),
        "section_title": first.get("section_title"),
        "act_year": act,
        "chapter": first.get("chapter"),
        "chapter_title": first.get("chapter_title"),
        "income_head": first.get("income_head"),
        "page_start": first.get("page_start"),
        "page_end": chunks[-1].get("page_end"),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }

    # Attach summary if available
    summary_path = _SUMMARIES_DIR / f"{act}_{number.upper()}.txt"
    if summary_path.exists():
        section_data["summary"] = summary_path.read_text(encoding="utf-8")

    # Attach examples if available
    examples_path = _EXAMPLES_DIR / f"{act}_{number.upper()}.txt"
    if examples_path.exists():
        section_data["examples"] = examples_path.read_text(encoding="utf-8")

    return section_data


@router.get("/sections/{act}/{number}/mapping")
async def get_section_mapping(
    act: str,
    number: str,
) -> dict[str, Any]:
    """Return the equivalent section in the other Act."""
    if act not in ("1961", "2025"):
        raise HTTPException(400, "act must be 1961 or 2025")

    section_map = _load_section_map()
    key = f"{act}_{number.upper()}"
    mapping = section_map.get(key)

    if not mapping:
        return {
            "source": {"act_year": act, "section": number.upper()},
            "mapped": None,
            "confidence": 0.0,
            "note": "No mapping found",
        }

    return {
        "source": {"act_year": act, "section": number.upper()},
        "mapped": mapping,
    }


@router.get("/sections/{act}/{number}/equivalent")
async def get_section_equivalent(
    request: Request,
    act: str,
    number: str,
) -> dict[str, Any]:
    """
    Semantically find the corresponding section in the other Act,
    then use the LLM to generate a structured comparison of key changes.
    """
    if act not in ("1961", "2025"):
        raise HTTPException(400, "act must be 1961 or 2025")

    other_act = "1961" if act == "2025" else "2025"
    store = request.app.state.store

    # 1. Source section
    source_chunks = store.search_by_section(number.upper(), act)
    if not source_chunks:
        raise HTTPException(404, f"Section {number} not found in {act} Act")

    source_text = "\n\n".join(c.get("text", "") for c in source_chunks[:10])
    first = source_chunks[0]
    source_meta = {
        "section": first.get("section"),
        "section_title": first.get("section_title"),
        "act_year": act,
        "income_head": first.get("income_head"),
        "chapter_title": first.get("chapter_title"),
    }

    # 2. Check static map first
    section_map = _load_section_map()
    static_key = f"{act}_{number.upper()}"
    static_hit = section_map.get(static_key)
    mapped_section_num: str | None = None
    if static_hit:
        mapped_section_num = static_hit.get("section") if isinstance(static_hit, dict) else str(static_hit)

    # 3. Semantic search in the other act for best matching section
    from ..indexing.embedder import embed_query

    query_text = f"{first.get('section_title', '')} {source_text[:600]}"
    qv = embed_query(query_text)
    candidates = store.search(qv, act_year=other_act, top_k=30)

    # Group candidates by section, accumulate scores
    section_scores: dict[str, dict] = {}
    for c in candidates:
        sec = c.get("section", "")
        if not sec:
            continue
        if sec not in section_scores:
            section_scores[sec] = {
                "section": sec,
                "section_title": c.get("section_title"),
                "act_year": other_act,
                "income_head": c.get("income_head"),
                "scores": [],
            }
        section_scores[sec]["scores"].append(c.get("score", 0))

    # Pick best by average score (prefer static map hit if present)
    best = None
    if mapped_section_num and mapped_section_num in section_scores:
        best = section_scores[mapped_section_num]
    elif section_scores:
        best = max(section_scores.values(), key=lambda x: sum(x["scores"]) / len(x["scores"]))

    if not best:
        return {
            "source": source_meta,
            "equivalent": None,
            "analysis": None,
        }

    # 4. Fetch full equivalent section text
    equiv_chunks = store.search_by_section(best["section"], other_act)
    if not equiv_chunks:
        return {"source": source_meta, "equivalent": None, "analysis": None}

    equiv_text = "\n\n".join(c.get("text", "") for c in equiv_chunks[:10])
    efirst = equiv_chunks[0]
    confidence = round(sum(best["scores"]) / len(best["scores"]), 3)

    equivalent_meta = {
        "section": efirst.get("section"),
        "section_title": efirst.get("section_title"),
        "act_year": other_act,
        "income_head": efirst.get("income_head"),
        "chapter_title": efirst.get("chapter_title"),
        "confidence": confidence,
        "preview": equiv_text[:500],
    }

    # 5. LLM comparison
    from ..rag.prompt_builder import build_comparison_prompt
    from ..rag.llm_provider import get_provider

    system, messages = build_comparison_prompt(
        source_section=first.get("section", number.upper()),
        source_act=act,
        source_title=first.get("section_title", ""),
        source_text=source_text,
        equiv_section=efirst.get("section", ""),
        equiv_act=other_act,
        equiv_title=efirst.get("section_title", ""),
        equiv_text=equiv_text,
    )

    llm_config = request.app.state.llm_config
    provider = get_provider(llm_config)
    analysis = await provider.chat(system, messages)

    return {
        "source": source_meta,
        "equivalent": equivalent_meta,
        "analysis": analysis,
    }


@router.get("/sections/{act}/{number}/summary")
async def get_section_summary(
    request: Request,
    act: str,
    number: str,
    force: bool = False,
) -> dict[str, Any]:
    """
    Return LLM-generated summary for a section.
    Generates on-the-fly if not cached. Pass ?force=true to regenerate.
    """
    if act not in ("1961", "2025"):
        raise HTTPException(400, "act must be 1961 or 2025")

    summary_path = _SUMMARIES_DIR / f"{act}_{number.upper()}.txt"
    if summary_path.exists() and not force:
        return {"summary": summary_path.read_text(encoding="utf-8"), "cached": True}

    # Generate on-the-fly
    store = request.app.state.store
    chunks = store.search_by_section(number.upper(), act)
    if not chunks:
        raise HTTPException(404, f"Section {number} not found in {act} Act")

    section_text = "\n\n".join(c.get("text", "") for c in chunks[:10])
    section_ref = f"Section {number} of the Income Tax Act {act}"

    from ..rag.prompt_builder import build_section_summary_prompt
    from ..rag.llm_provider import get_provider
    system, messages = build_section_summary_prompt(section_text, section_ref)

    llm_config = request.app.state.llm_config
    provider = get_provider(llm_config)
    summary = await provider.chat(system, messages)

    # Cache it
    _SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary, encoding="utf-8")

    return {"summary": summary, "cached": False}
