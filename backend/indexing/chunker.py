"""
Atomic clause-level chunker for RAG.

Breaks Income Tax Act sections into the smallest meaningful legal units:
  Section body → Subsection → Clause → Sub-clause → Explanation/Proviso

Chunk ID format:  IT{act_year}_S{section}_{clause_path}
  e.g.  IT1961_S2_1A(a)(i)
        IT2025_S80C_1
        IT1961_S2_PROV1

Chunk types: definition | rule | exception | explanation | condition
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..parsing.structure import Clause, Subsection, Section, ParsedAct


# ---------------------------------------------------------------------------
# Chunk dataclass — matches the output schema exactly
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    id: str
    act_year: str
    chapter: str
    chapter_title: str
    section: str
    section_title: str
    income_head: str
    clause_path: str            # e.g. "1A(a)(i)" or "" for bare section body
    type: str                   # definition | rule | exception | explanation | condition
    text: str                   # clean, embeddable text
    keywords: list[str]         # 3-8 legal keywords
    entities: list[str]         # named legal entities extracted
    related_sections: list[str] # cross-referenced sections from text
    mapped_to: str | None       # e.g. "2025_S80C" if mapped
    source: dict[str, int]      # {"page_start": N, "page_end": M}

    def to_payload(self) -> dict[str, Any]:
        """Convert to Qdrant payload dict."""
        return {
            "id": self.id,
            "act_year": self.act_year,
            "chapter": self.chapter,
            "chapter_title": self.chapter_title,
            "section": self.section,
            "section_title": self.section_title,
            "income_head": self.income_head,
            "clause_path": self.clause_path,
            "type": self.type,
            "text": self.text,
            "keywords": self.keywords,
            "entities": self.entities,
            "related_sections": self.related_sections,
            "mapped_to": self.mapped_to,
            "page_start": self.source["page_start"],
            "page_end": self.source["page_end"],
        }


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_ASTERISK_RE = re.compile(r"[\*\†\‡\§]+")
_TABLE_MARKER_RE = re.compile(r"\[/?TABLE\]")
_FOOTNOTE_RE = re.compile(r"\d+\s*See\s+footnote", re.IGNORECASE)


def _clean(text: str) -> str:
    """Normalize whitespace, remove noise characters."""
    text = _ASTERISK_RE.sub("", text)
    text = _TABLE_MARKER_RE.sub("", text)
    text = _FOOTNOTE_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Type classification
# ---------------------------------------------------------------------------

_DEFINITION_PATS = re.compile(
    r"\b(means?|includes?|shall mean|is defined|denotes?|refers? to)\b",
    re.IGNORECASE,
)
_EXCEPTION_PATS = re.compile(
    r"\b(provided that|notwithstanding|shall not apply|nothing (in|contained in)|"
    r"except|exempted?|not include|shall not be|does not include)\b",
    re.IGNORECASE,
)
_CONDITION_PATS = re.compile(
    r"\b(subject to|where|if|unless|on condition|provided|only if|"
    r"in case|when|upon|upon satisfaction)\b",
    re.IGNORECASE,
)
_EXPLANATION_PATS = re.compile(
    r"^explanation\b",
    re.IGNORECASE,
)


def _classify_type(text: str, is_proviso: bool = False, is_explanation: bool = False) -> str:
    if is_explanation:
        return "explanation"
    if is_proviso or _EXCEPTION_PATS.search(text):
        return "exception"
    if _DEFINITION_PATS.search(text):
        return "definition"
    if _CONDITION_PATS.search(text):
        return "condition"
    return "rule"


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------

# High-value domain terms
_DOMAIN_TERMS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bagricultural income\b", re.I), "agricultural income"),
    (re.compile(r"\bassessee\b", re.I), "assessee"),
    (re.compile(r"\bassessment year\b", re.I), "assessment year"),
    (re.compile(r"\bprevious year\b", re.I), "previous year"),
    (re.compile(r"\btax year\b", re.I), "tax year"),
    (re.compile(r"\btotal income\b", re.I), "total income"),
    (re.compile(r"\bgross total income\b", re.I), "gross total income"),
    (re.compile(r"\bperquisite\b", re.I), "perquisite"),
    (re.compile(r"\ballowance\b", re.I), "allowance"),
    (re.compile(r"\bdeduction\b", re.I), "deduction"),
    (re.compile(r"\bexemption\b", re.I), "exemption"),
    (re.compile(r"\bcapital gain\b", re.I), "capital gain"),
    (re.compile(r"\blong.term\b", re.I), "long-term"),
    (re.compile(r"\bshort.term\b", re.I), "short-term"),
    (re.compile(r"\btransfer\b", re.I), "transfer"),
    (re.compile(r"\bcost of acquisition\b", re.I), "cost of acquisition"),
    (re.compile(r"\bindexation\b", re.I), "indexation"),
    (re.compile(r"\bbusiness income\b", re.I), "business income"),
    (re.compile(r"\bprofession\b", re.I), "profession"),
    (re.compile(r"\bdepreciation\b", re.I), "depreciation"),
    (re.compile(r"\bhouse property\b", re.I), "house property"),
    (re.compile(r"\bannual value\b", re.I), "annual value"),
    (re.compile(r"\bsalary\b", re.I), "salary"),
    (re.compile(r"\bwages?\b", re.I), "wages"),
    (re.compile(r"\btds\b", re.I), "TDS"),
    (re.compile(r"\btax deducted at source\b", re.I), "tax deducted at source"),
    (re.compile(r"\btax collected at source\b", re.I), "tax collected at source"),
    (re.compile(r"\badvance tax\b", re.I), "advance tax"),
    (re.compile(r"\bself.assessment\b", re.I), "self-assessment"),
    (re.compile(r"\breturn of income\b", re.I), "return of income"),
    (re.compile(r"\bpenalty\b", re.I), "penalty"),
    (re.compile(r"\bappeal\b", re.I), "appeal"),
    (re.compile(r"\bsearch and seizure\b", re.I), "search and seizure"),
    (re.compile(r"\bresident\b", re.I), "resident"),
    (re.compile(r"\bnon.resident\b", re.I), "non-resident"),
    (re.compile(r"\bHUF\b"), "HUF"),
    (re.compile(r"\bfirm\b", re.I), "firm"),
    (re.compile(r"\bpartnership\b", re.I), "partnership"),
    (re.compile(r"\bcompany\b", re.I), "company"),
    (re.compile(r"\bcorporate\b", re.I), "corporate"),
    (re.compile(r"\bforeign\b", re.I), "foreign"),
    (re.compile(r"\bdividend\b", re.I), "dividend"),
    (re.compile(r"\binterest\b", re.I), "interest"),
    (re.compile(r"\broyalt(y|ies)\b", re.I), "royalty"),
    (re.compile(r"\bfees? for technical services\b", re.I), "fees for technical services"),
    (re.compile(r"\bwitholding tax\b", re.I), "withholding tax"),
    (re.compile(r"\btrust\b", re.I), "trust"),
    (re.compile(r"\bcharitable\b", re.I), "charitable"),
    (re.compile(r"\bnotional rent\b", re.I), "notional rent"),
    (re.compile(r"\bset.off\b", re.I), "set-off"),
    (re.compile(r"\bcarry forward\b", re.I), "carry forward"),
    (re.compile(r"\bprovision\b", re.I), "provision"),
    (re.compile(r"\bspecified\b", re.I), "specified"),
    (re.compile(r"\bprescribed\b", re.I), "prescribed"),
    (re.compile(r"\bnotified\b", re.I), "notified"),
]

# Section reference pattern: "section 80C", "sections 194A and 194B"
_SEC_REF_RE = re.compile(r"\bsections?\s+(\d{1,3}[A-Z]{0,5}(?:[,\s]+and\s+\d{1,3}[A-Z]{0,5})*)", re.IGNORECASE)

# Monetary amounts: "Rs. 1,50,000", "₹ 50 lakh"
_MONEY_RE = re.compile(r"(?:Rs\.?\s*|₹\s*)[\d,]+(?:\s*(?:lakh|crore|lakhs|crores))?", re.IGNORECASE)

# Percentage: "20%", "30 per cent"
_PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|per\s*cent)", re.IGNORECASE)

# Time periods: "within 30 days", "before 31st March"
_TIME_RE = re.compile(r"\b\d+\s+(?:days?|months?|years?)\b", re.IGNORECASE)


def _extract_keywords(text: str, section_title: str = "") -> list[str]:
    """Extract 3–8 meaningful legal keywords."""
    found: list[str] = []

    # Domain terms
    for pattern, term in _DOMAIN_TERMS:
        if pattern.search(text) and term not in found:
            found.append(term)
        if len(found) >= 6:
            break

    # Monetary amounts (max 2)
    for m in _MONEY_RE.finditer(text):
        kw = m.group(0).strip()
        if kw not in found:
            found.append(kw)
        if sum(1 for f in found if _MONEY_RE.match(f)) >= 2:
            break

    # Percentages (max 1)
    m_pct = _PERCENT_RE.search(text)
    if m_pct:
        kw = m_pct.group(0).strip()
        if kw not in found:
            found.append(kw)

    # Add section title words if not already covered
    if section_title:
        title_words = [
            w.lower() for w in re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", section_title)
            if len(w) > 4 and w.lower() not in {
                "section", "under", "respect", "manner", "other", "certain",
                "where", "which", "their",
            }
        ]
        for w in title_words[:2]:
            if w not in found:
                found.append(w)

    return found[:8] if found else [section_title.lower().strip()[:40]]


def _extract_entities(text: str) -> list[str]:
    """Extract named legal entities."""
    entities: list[str] = []

    # Section references
    for m in _SEC_REF_RE.finditer(text):
        ref = f"Section {m.group(1).strip()}"
        if ref not in entities:
            entities.append(ref)

    return entities[:6]


def _extract_related_sections(text: str) -> list[str]:
    """Extract all section numbers referenced in text."""
    refs: list[str] = []
    for m in _SEC_REF_RE.finditer(text):
        raw = m.group(1)
        # Handle "194A and 194B" patterns
        nums = re.findall(r"\d{1,3}[A-Z]{0,5}", raw, re.IGNORECASE)
        for n in nums:
            if n.upper() not in refs:
                refs.append(n.upper())
    return refs[:10]


# ---------------------------------------------------------------------------
# Clause path builder
# ---------------------------------------------------------------------------

def _build_path(*parts: str) -> str:
    """Build clause path from parts, e.g. ("1A", "a", "i") → "1A(a)(i)"."""
    if not parts or not parts[0]:
        return ""
    result = parts[0]
    for p in parts[1:]:
        if p:
            result += f"({p})"
    return result


# ---------------------------------------------------------------------------
# Chunk ID builder
# ---------------------------------------------------------------------------

def _make_id(act_year: str, section: str, clause_path: str) -> str:
    clean_path = re.sub(r"[^\w().]", "_", clause_path)
    if clean_path:
        return f"IT{act_year}_S{section}_{clean_path}"
    return f"IT{act_year}_S{section}"


# ---------------------------------------------------------------------------
# Core chunking logic
# ---------------------------------------------------------------------------

def _make_chunk(
    *,
    act_year: str,
    chapter: str,
    chapter_title: str,
    section: str,
    section_title: str,
    income_head: str,
    clause_path: str,
    text: str,
    chunk_type: str,
    mapped_to: str | None,
    page_start: int,
    page_end: int,
) -> Chunk:
    clean_text = _clean(text)
    return Chunk(
        id=_make_id(act_year, section, clause_path),
        act_year=act_year,
        chapter=chapter,
        chapter_title=chapter_title,
        section=section,
        section_title=section_title,
        income_head=income_head,
        clause_path=clause_path,
        type=chunk_type,
        text=clean_text,
        keywords=_extract_keywords(clean_text, section_title),
        entities=_extract_entities(clean_text),
        related_sections=_extract_related_sections(clean_text),
        mapped_to=mapped_to,
        source={"page_start": page_start, "page_end": page_end},
    )


def chunk_clause(
    clause: Clause,
    *,
    act_year: str,
    chapter: str,
    chapter_title: str,
    section: str,
    section_title: str,
    income_head: str,
    sub_num: str,
    mapped_to: str | None,
    page_start: int,
    page_end: int,
) -> list[Chunk]:
    """Produce chunk(s) for one Clause and all its sub-clauses."""
    chunks: list[Chunk] = []
    path = _build_path(sub_num, clause.identifier)

    # Clause body chunk
    chunks.append(_make_chunk(
        act_year=act_year,
        chapter=chapter,
        chapter_title=chapter_title,
        section=section,
        section_title=section_title,
        income_head=income_head,
        clause_path=path,
        text=f"Section {section}({sub_num})({clause.identifier}): {clause.text}",
        chunk_type=_classify_type(clause.text),
        mapped_to=mapped_to,
        page_start=page_start,
        page_end=page_end,
    ))

    # Sub-clauses (if parsed)
    for sc in clause.sub_clauses:
        sc_path = _build_path(sub_num, clause.identifier, sc.identifier)
        chunks.append(_make_chunk(
            act_year=act_year,
            chapter=chapter,
            chapter_title=chapter_title,
            section=section,
            section_title=section_title,
            income_head=income_head,
            clause_path=sc_path,
            text=f"Section {section}({sub_num})({clause.identifier})({sc.identifier}): {sc.text}",
            chunk_type=_classify_type(sc.text),
            mapped_to=mapped_to,
            page_start=page_start,
            page_end=page_end,
        ))

    return chunks


def chunk_subsection(
    sub: Subsection,
    *,
    act_year: str,
    chapter: str,
    chapter_title: str,
    section: str,
    section_title: str,
    income_head: str,
    mapped_to: str | None,
    page_start: int,
    page_end: int,
) -> list[Chunk]:
    """Produce chunks for one Subsection: body + each clause + provisos + explanations."""
    chunks: list[Chunk] = []
    path = _build_path(sub.number)

    # Subsection body (leading text before any clause)
    body = _clean(sub.text)
    if body:
        chunks.append(_make_chunk(
            act_year=act_year,
            chapter=chapter,
            chapter_title=chapter_title,
            section=section,
            section_title=section_title,
            income_head=income_head,
            clause_path=path,
            text=f"Section {section}({sub.number}): {body}",
            chunk_type=_classify_type(body),
            mapped_to=mapped_to,
            page_start=page_start,
            page_end=page_end,
        ))

    # Clauses
    for clause in sub.clauses:
        chunks.extend(chunk_clause(
            clause,
            act_year=act_year,
            chapter=chapter,
            chapter_title=chapter_title,
            section=section,
            section_title=section_title,
            income_head=income_head,
            sub_num=sub.number,
            mapped_to=mapped_to,
            page_start=page_start,
            page_end=page_end,
        ))

    # Provisos — each is an "exception" chunk
    for idx, proviso in enumerate(sub.provisos, 1):
        prov_path = f"{path}_PROV{idx}"
        chunks.append(_make_chunk(
            act_year=act_year,
            chapter=chapter,
            chapter_title=chapter_title,
            section=section,
            section_title=section_title,
            income_head=income_head,
            clause_path=prov_path,
            text=f"Section {section}({sub.number}) Proviso {idx}: Provided that {proviso}",
            chunk_type="exception",
            mapped_to=mapped_to,
            page_start=page_start,
            page_end=page_end,
        ))

    # Explanations
    for idx, expl in enumerate(sub.explanations, 1):
        expl_path = f"{path}_EXPL{idx}"
        chunks.append(_make_chunk(
            act_year=act_year,
            chapter=chapter,
            chapter_title=chapter_title,
            section=section,
            section_title=section_title,
            income_head=income_head,
            clause_path=expl_path,
            text=f"Section {section}({sub.number}) Explanation {idx}: {expl}",
            chunk_type="explanation",
            mapped_to=mapped_to,
            page_start=page_start,
            page_end=page_end,
        ))

    return chunks


def chunk_section(section: Section) -> list[Chunk]:
    """
    Convert one Section into atomic Chunks at clause/sub-clause/proviso/explanation level.

    If a section has no parsed subsections, one chunk is produced for the entire section body.
    """
    chunks: list[Chunk] = []

    mapped_to: str | None = None
    if section.mapped_section:
        other_year = "2025" if section.act == "1961" else "1961"
        mapped_to = f"{other_year}_S{section.mapped_section}"

    common = dict(
        act_year=section.act,
        chapter=section.chapter_number,
        chapter_title=section.chapter_title,
        section=section.number,
        section_title=section.title,
        income_head=section.income_head or "General / Definitions",
        mapped_to=mapped_to,
        page_start=section.page_start,
        page_end=section.page_end,
    )

    if section.subsections:
        for sub in section.subsections:
            chunks.extend(chunk_subsection(sub, **common))
    else:
        # No parsed subsections: one chunk for the whole section
        body = _clean(section.full_text) or f"Section {section.number}. {section.title}"
        chunks.append(_make_chunk(
            **common,
            clause_path="",
            text=f"Section {section.number}: {section.title}. {body}",
            chunk_type=_classify_type(body),
        ))

    return chunks


def chunk_parsed_act(parsed: ParsedAct) -> list[Chunk]:
    """Chunk all sections in a ParsedAct into atomic clause-level chunks."""
    all_chunks: list[Chunk] = []
    for section in parsed.sections:
        all_chunks.extend(chunk_section(section))
    return all_chunks
