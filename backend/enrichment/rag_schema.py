"""
RAG-ready JSON schema for enriched Income Tax Act chunks.

Matches the exact output format requested:
{
    "chapter", "chapter_title", "section", "section_title",
    "subsection", "clause", "content", "clean_text", "summary",
    "conditions", "exceptions", "keywords", "references"
}

Extended with provenance fields (act_year, chunk_id, income_head, page_*) that
are essential for Qdrant filtering but not part of the core spec.
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class RagChunk(BaseModel):
    # ── Core spec fields ──────────────────────────────────────────────────────
    chapter: str = ""
    chapter_title: str = ""
    section: str = ""
    section_title: str = ""
    subsection: str = ""        # e.g. "(1)", "(2A)" or "" for whole-section chunks
    clause: str = ""            # e.g. "(a)", "(i)" or ""

    # LLM-generated text fields
    content: str = ""           # original text, lightly cleaned
    clean_text: str = ""        # plain-English rewrite (LLM output)
    summary: str = ""           # 2–3 line CA-intern explanation (LLM output)
    conditions: list[str] = Field(default_factory=list)   # eligibility rules / thresholds
    exceptions: list[str] = Field(default_factory=list)   # provisos / "shall not include"
    keywords: list[str] = Field(default_factory=list)     # 5–10 legal terms
    references: list[str] = Field(default_factory=list)   # e.g. ["section 10", "section 45"]

    # ── Provenance / indexing fields (not in spec but needed for Qdrant) ──────
    act_year: str = ""          # "1961" | "2025"
    chunk_id: str = ""          # IT{year}_S{section}_{path}
    income_head: str = ""       # e.g. "Salaries", "Capital Gains"
    clause_path: str = ""       # e.g. "1A(a)(i)" — for ordering
    chunk_type: str = ""        # definition | rule | exception | explanation | condition
    mapped_to: str | None = None  # cross-act section reference
    page_start: int = 0
    page_end: int = 0

    def to_qdrant_payload(self) -> dict[str, Any]:
        """Payload dict for Qdrant upsert — mirrors to_payload() on old Chunk."""
        return {
            # Filterable keyword indices
            "act_year":      self.act_year,
            "section":       self.section,
            "chapter":       self.chapter,
            "income_head":   self.income_head,
            "type":          self.chunk_type,
            # Spec fields
            "chunk_id":      self.chunk_id,
            "chapter_title": self.chapter_title,
            "section_title": self.section_title,
            "subsection":    self.subsection,
            "clause":        self.clause,
            "clause_path":   self.clause_path,
            "content":       self.content,
            "clean_text":    self.clean_text,
            "summary":       self.summary,
            "conditions":    self.conditions,
            "exceptions":    self.exceptions,
            "keywords":      self.keywords,
            "references":    self.references,
            # Provenance
            "mapped_to":     self.mapped_to,
            "page_start":    self.page_start,
            "page_end":      self.page_end,
            # Legacy compat — RAG retriever reads "text" and "id"
            "text":          self.clean_text or self.content,
            "id":            self.chunk_id,
        }
