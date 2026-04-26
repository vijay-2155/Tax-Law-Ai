"""
Hybrid retriever: leverages Qdrant Cloud payload indices for fast pre-filtering.

Payload indices available (server-side, applied BEFORE vector scoring):
  - section     (keyword) → exact section lookup
  - income_head (keyword) → filter by income head
  - type        (keyword) → filter by definition/rule/exception/explanation/condition
  - chapter     (keyword) → filter by chapter number
  - section_title (text)  → full-text match

Search strategies:
  1. exact_section   → payload scroll by section number (no vector needed)
  2. filtered_vector → vector search + payload filter (income_head, type, chapter)
  3. semantic        → pure vector search (fallback)
  4. cross_act       → search both collections
"""

from __future__ import annotations
import re
from typing import Any

from ..indexing.embedder import embed_query
from ..indexing.qdrant_store import QdrantStore

# ── Slab / rate / regime topic detection ─────────────────────────────────────
# When a query touches tax rates or regimes, Section 202 (2025 Act) must
# always be in the retrieved context so the model uses the correct FY 2025-26
# slabs instead of fabricating old FY 2024-25 slabs from training data.
_SLAB_RATE_RE = re.compile(
    r"\b(slab|tax\s*rate|new\s*regime|old\s*regime|115BAC|section\s*202|"
    r"maximum\s*marginal\s*rate|income\s*tax\s*rate|tax\s*bracket|"
    r"rate\s*of\s*tax|tax\s*slab|rebate|87A|surcharge|cess)\b",
    re.IGNORECASE,
)

# ── Section number detection ─────────────────────────────────────────────────
_SECTION_QUERY_RE = re.compile(
    r"\b(?:section|sec\.?|u/s|§)\s*(\d{1,3}[A-Z]{0,5})\b",
    re.IGNORECASE,
)

# ── Income head inference from query ─────────────────────────────────────────
_HEAD_KEYWORDS: list[tuple[str, str]] = [
    ("salary",               "Salaries"),
    ("perquisite",           "Salaries"),
    ("wages",                "Salaries"),
    ("house property",       "House Property"),
    ("rent",                 "House Property"),
    ("annual value",         "House Property"),
    ("capital gain",         "Capital Gains"),
    ("capital asset",        "Capital Gains"),
    ("transfer of asset",    "Capital Gains"),
    ("ltcg",                 "Capital Gains"),
    ("stcg",                 "Capital Gains"),
    ("business income",      "Business and Profession"),
    ("profession",           "Business and Profession"),
    ("depreciation",         "Business and Profession"),
    ("pgbp",                 "Business and Profession"),
    ("other sources",        "Income from Other Sources"),
    ("dividend",             "Income from Other Sources"),
    ("80c",                  "Deductions"),
    ("80d",                  "Deductions"),
    ("deduction",            "Deductions"),
    ("chapter vi",           "Deductions"),
    ("tds",                  "TDS / TCS"),
    ("tax deducted",         "TDS / TCS"),
    ("tcs",                  "TDS / TCS"),
    ("tax collected",        "TDS / TCS"),
    ("withholding",          "TDS / TCS"),
    ("advance tax",          "Collection and Recovery"),
    ("self assessment",      "Collection and Recovery"),
    ("appeal",               "Appeals and Revisions"),
    ("tribunal",             "Appeals and Revisions"),
    ("itat",                 "Appeals and Revisions"),
    ("penalty",              "Penalties"),
    ("prosecution",          "Offences and Prosecution"),
    ("assessment",           "Assessment"),
    ("return of income",     "Return of Income"),
    ("itr",                  "Return of Income"),
]

# ── Chunk type inference from query ──────────────────────────────────────────
_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("definition",   "definition"),
    ("means",        "definition"),
    ("define",       "definition"),
    ("what is",      "definition"),
    ("exception",    "exception"),
    ("exempt",       "exception"),
    ("provided that","exception"),
    ("not apply",    "exception"),
    ("explanation",  "explanation"),
    ("condition",    "condition"),
    ("eligibility",  "condition"),
    ("who can",      "condition"),
]

# ── Cross-act trigger detection ───────────────────────────────────────────────
_CROSS_ACT_RE = re.compile(
    r"\b(compare|difference|1961\s*(vs\.?|versus|and)\s*2025|"
    r"2025\s*(vs\.?|versus|and)\s*1961|both acts?|old act|new act|"
    r"equivalent|corresponding section)\b",
    re.IGNORECASE,
)


def _extract_section_number(query: str) -> str | None:
    m = _SECTION_QUERY_RE.search(query)
    return m.group(1).upper() if m else None


def _infer_income_head(query: str) -> str | None:
    lower = query.lower()
    for keyword, head in _HEAD_KEYWORDS:
        if keyword in lower:
            return head
    return None


def _infer_chunk_type(query: str) -> str | None:
    lower = query.lower()
    for keyword, ctype in _TYPE_KEYWORDS:
        if keyword in lower:
            return ctype
    return None


class Retriever:
    """
    Retriever that uses Qdrant Cloud payload indices for pre-filtering.

    Payload filter is applied SERVER-SIDE before vector scoring, so
    filtering by income_head or chunk type costs nearly nothing.
    """

    def __init__(self, store: QdrantStore):
        self.store = store

    def _inject_sec202_if_needed(
        self, query: str, chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        If the query is about tax rates / slabs / regime, ensure Section 202
        (2025 Act new regime slabs) is present in the retrieved chunks.
        This prevents the model from falling back to stale FY 2024-25 slabs
        from its training data.
        """
        if not _SLAB_RATE_RE.search(query):
            return chunks

        # Check if Section 202 (2025) is already present
        already_present = any(
            str(c.get("section")) == "202" and str(c.get("act_year")) == "2025"
            for c in chunks
        )
        if already_present:
            return chunks

        # Force-fetch Section 202 from the 2025 Act
        sec202_chunks = self.store.search_by_section("202", "2025")
        if sec202_chunks:
            # Prepend so it's the first chunk the model sees
            for c in sec202_chunks:
                c.setdefault("score", 1.0)
                c["_force_injected"] = True
            return sec202_chunks[:3] + chunks

        return chunks

    def retrieve(
        self,
        query: str,
        act_year: str | None = "2025",
        top_k: int = 8,
        cross_act: bool = False,
        # Explicit overrides (from API callers)
        income_head: str | None = None,
        chunk_type: str | None = None,
        chapter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Smart retrieval with full payload filter exploitation.

        - Exact section query   → payload scroll (zero vector ops)
        - Filtered query        → vector search with server-side payload filter
        - No filter inferrable  → pure vector search
        - Cross-act query       → both collections merged
        """

        # ── 1. Exact section lookup (fastest path) ───────────────────────────
        sec_num = _extract_section_number(query)
        if sec_num:
            if cross_act or act_year is None:
                results: list[dict] = []
                for yr in ["2025", "1961"]:
                    chunks = self.store.search_by_section(sec_num, yr)
                    results.extend(chunks)
            else:
                results = self.store.search_by_section(sec_num, act_year)

            if results:
                for r in results:
                    r.setdefault("score", 1.0)
                return results[:top_k * 2]  # return all chunks for this section

        # ── 2. Infer payload filters from query ──────────────────────────────
        effective_head  = income_head  or _infer_income_head(query)
        effective_type  = chunk_type   or _infer_chunk_type(query)

        query_vector = embed_query(query)

        # ── 3. Cross-act search ───────────────────────────────────────────────
        if cross_act or act_year is None:
            results = self.store.search_both_acts(
                query_vector,
                top_k=top_k,
                income_head=effective_head,
            )
            # Fallback: relax head filter if too few results
            if len(results) < 3 and effective_head:
                results = self.store.search_both_acts(query_vector, top_k=top_k)
            return results

        # ── 4. Single act: filtered vector search ────────────────────────────
        results = self.store.search(
            query_vector,
            act_year=act_year,
            top_k=top_k,
            income_head=effective_head,
            chunk_type=effective_type,
            chapter=chapter,
        )

        # Relax type filter first if not enough results
        if len(results) < 3 and effective_type:
            results = self.store.search(
                query_vector,
                act_year=act_year,
                top_k=top_k,
                income_head=effective_head,
                chapter=chapter,
            )

        # Relax head filter if still not enough
        if len(results) < 3 and effective_head:
            results = self.store.search(
                query_vector,
                act_year=act_year,
                top_k=top_k,
                chapter=chapter,
            )

        return self._inject_sec202_if_needed(query, results)

    def retrieve_section(
        self,
        section_number: str,
        act_year: str,
    ) -> list[dict[str, Any]]:
        """Direct section retrieval — all chunks sorted by clause path."""
        return self.store.search_by_section(section_number, act_year)

    def retrieve_by_head(
        self,
        income_head: str,
        act_year: str,
        query: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve top sections under a specific income head."""
        qv = embed_query(query)
        return self.store.search(
            qv,
            act_year=act_year,
            top_k=top_k,
            income_head=income_head,
        )

    def retrieve_definitions(
        self,
        query: str,
        act_year: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve definition-relevant chunks via semantic search."""
        qv = embed_query(f"definition meaning of {query}")
        return self.store.search(qv, act_year=act_year, top_k=top_k)

    def retrieve_exceptions(
        self,
        query: str,
        act_year: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve exception/exclusion-relevant chunks via semantic search."""
        qv = embed_query(f"exception exclusion does not apply {query}")
        return self.store.search(qv, act_year=act_year, top_k=top_k)
