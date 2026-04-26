"""
Income Head routes.

GET /api/heads                              → list all income heads with section counts
GET /api/heads/{head_name}/sections         → sections under a head (paginated)
GET /api/heads/{head_name}/search?q=...    → vector search within a head
"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Query, Request, HTTPException

router = APIRouter()

# Canonical income heads — must match income_head values in Qdrant payloads
INCOME_HEADS = [
    # The 5 heads of income (Chapter IV)
    "Salaries",
    "House Property",
    "Business and Profession",
    "Capital Gains",
    "Income from Other Sources",
    # Deductions & reliefs
    "Deductions",
    "Rebates and Reliefs",
    # Procedural / administrative
    "TDS / TCS",
    "Collection and Recovery",
    "Return of Income",
    "Assessment",
    "Appeals and Revisions",
    # Penal / offences
    "Penalties",
    "Offences and Prosecution",
    # Other
    "Exempt Income",
    "Aggregation of Income",
    "Set-off and Carry Forward",
    "Anti-Avoidance",
    "General Anti-Avoidance Rule",
    "Special Tax Rates",
    "Special Provisions",
    "Tax Administration",
    "General / Definitions",
    "Basis of Charge",
    "Miscellaneous",
]


@router.get("/heads")
async def list_heads(
    request: Request,
    act: str = Query("2025", pattern="^(1961|2025|both)$"),
) -> dict[str, Any]:
    """List all income heads with section counts."""
    store = request.app.state.store
    acts = ["2025", "1961"] if act == "both" else [act]

    heads_data = []
    for head in INCOME_HEADS:
        total = 0
        for act_year in acts:
            chunks = store.scroll_by_payload(act_year, {"income_head": head}, limit=500)
            # Count unique sections
            seen = set()
            for c in chunks:
                sec_key = f"{act_year}_{c.get('section')}"
                seen.add(sec_key)
            total += len(seen)

        if total > 0:
            heads_data.append({
                "name": head,
                "section_count": total,
                "slug": head.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "").replace("-", "_"),
            })

    return {"act": act, "heads": heads_data}


@router.get("/heads/{head_name}/sections")
async def sections_by_head(
    request: Request,
    head_name: str,
    act: str = Query("2025", pattern="^(1961|2025|both)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Return sections under a given income head."""
    store = request.app.state.store

    # Decode head name from slug
    canonical_head = _slug_to_head(head_name)
    if not canonical_head:
        raise HTTPException(404, f"Unknown income head: {head_name}")

    acts = ["2025", "1961"] if act == "both" else [act]

    # Collect unique sections
    sections: dict[str, dict[str, Any]] = {}
    for act_year in acts:
        chunks = store.scroll_by_payload(act_year, {"income_head": canonical_head}, limit=500)
        for c in chunks:
            key = f"{act_year}_{c.get('section')}"
            if key not in sections:
                sections[key] = {
                    "section": c.get("section"),
                    "section_title": c.get("section_title"),
                    "act_year": act_year,
                    "chapter": c.get("chapter"),
                    "chapter_title": c.get("chapter_title"),
                    "income_head": c.get("income_head"),
                    "page_start": c.get("page_start"),
                }

    all_sections = sorted(
        sections.values(),
        key=lambda s: (s["act_year"], _section_sort_key(s["section"])),
    )

    total = len(all_sections)
    paged = all_sections[offset: offset + limit]

    return {
        "head": canonical_head,
        "act": act,
        "total": total,
        "offset": offset,
        "limit": limit,
        "sections": paged,
    }


@router.get("/heads/{head_name}/search")
async def search_within_head(
    request: Request,
    head_name: str,
    q: str = Query(..., min_length=1),
    act: str = Query("2025", pattern="^(1961|2025|both)$"),
    top_k: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """Vector search filtered to a specific income head."""
    canonical_head = _slug_to_head(head_name)
    if not canonical_head:
        raise HTTPException(404, f"Unknown income head: {head_name}")

    retriever = request.app.state.retriever
    cross_act = act == "both"
    act_year = None if cross_act else act

    results = retriever.retrieve(
        query=q,
        act_year=act_year,
        top_k=top_k,
        cross_act=cross_act,
        income_head=canonical_head,
    )

    return {
        "head": canonical_head,
        "query": q,
        "act": act,
        "total": len(results),
        "results": results,
    }


def _slug_to_head(slug: str) -> str | None:
    """Convert URL slug back to canonical head name."""
    # Direct match first
    for head in INCOME_HEADS:
        if head.lower() == slug.lower():
            return head
    # Slug match
    for head in INCOME_HEADS:
        head_slug = (
            head.lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("(", "")
            .replace(")", "")
            .replace("-", "_")
        )
        if head_slug == slug.lower():
            return head
    return None


def _section_sort_key(section: str | None) -> tuple[int, str]:
    """Sort sections numerically where possible."""
    import re
    if not section:
        return (9999, "")
    m = re.match(r"^(\d+)(.*)", section)
    if m:
        return (int(m.group(1)), m.group(2))
    return (9999, section)
