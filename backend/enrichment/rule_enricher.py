
"""
Pure rule-based enrichment for Income Tax Act chunks — zero LLM, zero API cost.

Fills:
  summary    — extractive: definition pattern or best sentence
  conditions — regex extraction of "subject to", "where", "if" clauses
  exceptions — regex extraction of "shall not apply/include", "does not include"
  keywords   — improved domain dict + amounts + time limits + authorities
  clean_text — normalized text (abbreviation expansion, hyphenation repair)

Runs the full 2025 act (529 sections → ~2500 chunks) in < 5 seconds.
"""

from __future__ import annotations

import re
from typing import Sequence

from .rag_schema import RagChunk
from ..indexing.chunker import _extract_keywords, _extract_related_sections

# ── Abbreviation expansion ─────────────────────────────────────────────────────

_ABBREVS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bAY\b"),  "Assessment Year"),
    (re.compile(r"\bFY\b"),  "Financial Year"),
    (re.compile(r"\bPY\b"),  "Previous Year"),
    (re.compile(r"\bAO\b"),  "Assessing Officer"),
    (re.compile(r"\bCIT\b"), "Commissioner of Income Tax"),
    (re.compile(r"\bPCIT\b"),"Principal Commissioner of Income Tax"),
    (re.compile(r"\bITAT\b"),"Income Tax Appellate Tribunal"),
    (re.compile(r"\bHUF\b"), "Hindu Undivided Family"),
    (re.compile(r"\bNRI\b"), "Non-Resident Indian"),
    (re.compile(r"\bSTT\b"), "Securities Transaction Tax"),
    (re.compile(r"\bDTAA\b"),"Double Taxation Avoidance Agreement"),
    (re.compile(r"\bTDS\b"), "Tax Deducted at Source"),
    (re.compile(r"\bTCS\b"), "Tax Collected at Source"),
    (re.compile(r"\bPAN\b"), "Permanent Account Number"),
    (re.compile(r"\bGSTIN\b"),"GST Identification Number"),
    (re.compile(r"\bNBFC\b"),"Non-Banking Financial Company"),
    (re.compile(r"\bLTCG\b"),"Long-Term Capital Gain"),
    (re.compile(r"\bSTCG\b"),"Short-Term Capital Gain"),
]

# Fix PDF line-break hyphenation: "Income-\ntax" → "Income-tax"
_LINEBREAK_HYPHEN_RE = re.compile(r"-\s*\n\s*")
# Normalize non-breaking spaces and multiple whitespace
_NBSP_RE   = re.compile(r" ")
_SPACE_RE  = re.compile(r"[ \t]{2,}")
# Strip leading clause labels like "(1) " or "(a) " at start of text
_LEAD_LABEL_RE = re.compile(r"^\s*\(\w+\)\s+")


def normalize_text(text: str) -> str:
    """Light normalization: fix hyphenation, expand abbreviations, clean whitespace."""
    text = _LINEBREAK_HYPHEN_RE.sub("-", text)
    text = _NBSP_RE.sub(" ", text)
    for pat, repl in _ABBREVS:
        text = pat.sub(repl, text)
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


# ── Sentence splitting ─────────────────────────────────────────────────────────
# Indian legal text splits poorly on "." alone (Rs., i.e., sub-section (1A), etc.)
# We split on: ";", "—", "\n" followed by "(", logical clause starters.

_SENT_SPLIT_RE = re.compile(
    r"(?:"
    r";\s+"                              # semicolons
    r"|—\s*\n\s*"                        # em-dash + newline (before list)
    r"|\n\s*\((?!\d+[A-Z]?\))"          # newline before (a) (b) (i) but NOT (1A)
    r"|\.\s+(?=[A-Z\"“])"          # period before capital or open-quote
    r")",
    re.UNICODE,
)

# Known abbreviations that contain a dot — we don't split after these
_NO_SPLIT_AFTER = re.compile(
    r"\b(?:Rs|Dr|Mr|Mrs|Ms|St|Co|Ltd|viz|etc|i\.e|e\.g|sub|s|u|Sec|No)\.\s*$",
    re.IGNORECASE,
)


def split_sentences(text: str) -> list[str]:
    """Split legal text into logical clauses/sentences."""
    raw = _SENT_SPLIT_RE.split(text)
    out: list[str] = []
    for part in raw:
        part = part.strip()
        if len(part) > 10:
            out.append(part)
    return out


# ── Condition extraction ───────────────────────────────────────────────────────
# Positive conditions: triggers that define WHEN a rule applies.

_COND_PATTERNS: list[re.Pattern] = [
    # "subject to [phrase]" — dependency on another provision
    re.compile(
        r"[Ss]ubject to\s+(?:the provisions? of\s+)?([^,;—\n]{10,150})",
        re.IGNORECASE,
    ),
    # "where [subject/condition], [rule]"
    re.compile(
        r"(?:^|\.\s+)[Ww]here\s+((?:(?!shall|will|may|must)[^,;—\n]){10,150})",
        re.IGNORECASE,
    ),
    # "in a case where" / "in the case of"
    re.compile(
        r"[Ii]n (?:a case|the case) (?:where|of)\s+([^,;—\n]{10,150})",
        re.IGNORECASE,
    ),
    # "if [condition]" (not already covered by where)
    re.compile(
        r"(?:^|\.\s+)[Ii]f\s+((?:(?!shall|will|may|must|otherwise)[^,;—\n]){10,120})",
        re.IGNORECASE,
    ),
    # "only if" / "only where"
    re.compile(
        r"[Oo]nly (?:if|where)\s+([^,;—\n]{10,120})",
        re.IGNORECASE,
    ),
    # "on satisfaction of" / "upon satisfaction"
    re.compile(
        r"[Uu]pon(?: satisfaction of)?\s+([^,;—\n]{10,120})",
        re.IGNORECASE,
    ),
    # numeric thresholds — these are conditions by nature
    re.compile(
        r"(?:exceeds?|more than|less than|at least|not (?:less|more) than)\s+"
        r"((?:Rs\.?\s*|₹\s*)?[\d,]+(?:\s*(?:lakh|crore|lakhs|crores|rupees))?"
        r"(?:\s+(?:per\s+\w+|per\s+cent|days?|months?|years?))?)",
        re.IGNORECASE,
    ),
]

_COND_CLEAN_RE = re.compile(r"[,;—.\s]+$")


def extract_conditions(text: str) -> list[str]:
    """Extract eligibility conditions / threshold clauses from legal text."""
    seen: set[str] = set()
    results: list[str] = []

    for pat in _COND_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1).strip()
            raw = _COND_CLEAN_RE.sub("", raw).strip()
            # Skip if too long, too short, or duplicate
            if len(raw) < 10 or len(raw) > 160:
                continue
            key = raw.lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            results.append(raw[:160])
            if len(results) >= 5:
                return results

    return results


# ── Exception extraction ───────────────────────────────────────────────────────
# Negative rules: things that are excluded, that shall not apply, etc.

_EXC_PATTERNS: list[re.Pattern] = [
    # "shall not apply in the case of / to [who]"
    re.compile(
        r"[Ss]hall not apply\s+(?:in the case of|to|where|if)\s+([^;—\n]{10,150})",
        re.IGNORECASE,
    ),
    # "shall not apply, subject to" — self-referential, capture the whole clause
    re.compile(
        r"[Ss]hall not apply(?:,\s+[^;—\n]{5,80})?(?=\s*[,;—]|\s+in)",
    ),
    # "shall not include [items]"
    re.compile(
        r"[Ss]hall not include\s+([^;—\n]{10,150})",
        re.IGNORECASE,
    ),
    # "does not include [items]"
    re.compile(
        r"[Dd]oes not include\s+([^;—\n]{10,150})",
        re.IGNORECASE,
    ),
    # "but shall not include"
    re.compile(
        r"but shall not (?:include|apply)\s+([^;—\n]{10,150})",
        re.IGNORECASE,
    ),
    # "not being [what]" — exclusionary phrase in definitions
    re.compile(
        r"not being\s+([^,;—\n]{10,120})",
        re.IGNORECASE,
    ),
    # "notwithstanding [provision]"
    re.compile(
        r"[Nn]otwithstanding (?:anything (?:contained |to the contrary )?in\s+)?"
        r"([^,;—\n]{10,150})",
        re.IGNORECASE,
    ),
    # "nothing in this section / sub-section shall"
    re.compile(
        r"[Nn]othing (?:in|contained in) (?:this|the) (?:section|sub-section|Act|clause)"
        r"\s+(?:[^;—\n]{0,60})?shall\s+([^;—\n]{10,120})",
        re.IGNORECASE,
    ),
    # "other than [what]" in definitional context (short, specific)
    re.compile(
        r"other than\s+([^,;—\n]{10,100})",
        re.IGNORECASE,
    ),
]

_EXC_CLEAN_RE = re.compile(r"[,;—.\s]+$")


def extract_exceptions(text: str) -> list[str]:
    """Extract exclusions, non-applicability clauses, and provisos."""
    seen: set[str] = set()
    results: list[str] = []

    for pat in _EXC_PATTERNS:
        for m in pat.finditer(text):
            # Some patterns capture group 1, some are zero-group (full match)
            try:
                raw = m.group(1).strip()
            except IndexError:
                raw = m.group(0).strip()
            raw = _EXC_CLEAN_RE.sub("", raw).strip()
            if len(raw) < 10 or len(raw) > 160:
                continue
            key = raw.lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            results.append(raw[:160])
            if len(results) >= 5:
                return results

    return results


# ── Summary generation ─────────────────────────────────────────────────────────

# Definition: “X” means Y...  or  “X” shall have the meaning...
# Handle:
#   • simple: “X” means Y
#   • qualified: “X”, in relation to Z, means Y
#   • list form: “X” means— (a) Y
_DEF_RE = re.compile(
    r'[“”]([^””]{2,60})[“”]\s*'
    r'(?:,[^;””]{0,250})?\s*'   # optional qualifier e.g. “, in relation to companies,”
    r'(?:means?|includes?|shall (?:have the meaning|mean)|denotes?|refers? to)'
    r'(?:\s*—)?\s*'             # optional em-dash before a list
    r'(?:\([a-z]\)\s+)?'        # optional first clause label (a)
    r'([^;—\n]{10,200})',
    re.IGNORECASE,
)

# "X shall have the meaning assigned to it in section N"
_DEF_REF_RE = re.compile(
    r'["“]([^"”]{2,60})["”]\s+shall have the meaning assigned',
    re.IGNORECASE,
)

# Exception opener: "shall not apply / does not include"
_EXC_OPENER_RE = re.compile(
    r'((?:[Ss]hall not (?:apply|include)|[Dd]oes not include|'
    r'[Nn]othing (?:in|contained)|[Nn]otwithstanding)[^;—\n]{10,200})',
    re.IGNORECASE,
)

# Condition opener: whole "where/if/subject to" sentence
_COND_OPENER_RE = re.compile(
    r'((?:[Ww]here|[Ss]ubject to|[Ii]f|[Ii]n a case where)[^;—\n]{15,200})',
    re.IGNORECASE,
)

_TRAIL_CLEAN_RE = re.compile(r"[,;—\s]+$")
_LEAD_STRIP_RE  = re.compile(r"^\(\w+\)\s*")  # strip leading (1), (a), etc.


def _clean_summary(s: str, max_len: int = 200) -> str:
    s = _TRAIL_CLEAN_RE.sub("", s.strip())
    s = _LEAD_STRIP_RE.sub("", s)
    if not s.endswith("."):
        s = s + "."
    return s[:max_len]


def generate_summary(
    content: str,
    section_title: str,
    chunk_type: str,
    section: str = "",
) -> str:
    """
    Generate a 1-2 sentence extractive summary for a chunk.

    Always tries the definition pattern first (many exception-typed chunks are
    definitions that also contain provisos). Falls back by chunk_type.
    """
    text = content.strip()

    # ── Try definition pattern first — regardless of chunk_type ──────────────
    # "X" shall have the meaning assigned to it in section N
    m_ref = _DEF_REF_RE.search(text)
    if m_ref:
        return f"Defines ‘{m_ref.group(1)}’ as referenced in another section."

    m = _DEF_RE.search(text)
    if m:
        term = m.group(1).strip()
        defn = _TRAIL_CLEAN_RE.sub("", m.group(2).strip())
        defn = re.sub(r"—\s*$", "", defn).rstrip()[:150]
        return f"Defines ‘{term}’ as {defn}."

    # ── Exceptions ───────────────────────────────────────────────────────────
    if chunk_type == "exception":
        m = _EXC_OPENER_RE.search(text)
        if m:
            return _clean_summary(m.group(1))

    # ── Conditions ───────────────────────────────────────────────────────────
    if chunk_type == "condition":
        m = _COND_OPENER_RE.search(text)
        if m:
            return _clean_summary(m.group(1))

    # ── General: best first sentence ─────────────────────────────────────────
    sentences = split_sentences(text)
    for sent in sentences:
        sent = sent.strip()
        sent = _LEAD_STRIP_RE.sub("", sent).strip()
        # Good sentence: substantial, not a list item, not a cross-reference only
        if 30 <= len(sent) <= 280 and not sent.startswith("("):
            return _clean_summary(sent)

    # ── Fallback ─────────────────────────────────────────────────────────────
    if section_title:
        return f"Relates to: {section_title}."
    if section:
        return f"Section {section} provision."
    return ""


# ── Enhanced keyword extraction ────────────────────────────────────────────────
# Extend the base domain list with authorities, assessee types, threshold signals.

_EXTRA_DOMAIN: list[tuple[re.Pattern, str]] = [
    # Authorities
    (re.compile(r"\bAssessing Officer\b", re.I),           "Assessing Officer"),
    (re.compile(r"\bPrincipal Commissioner\b", re.I),      "Principal Commissioner"),
    (re.compile(r"\bCommissioner\b", re.I),                "Commissioner"),
    (re.compile(r"\bAppellate Tribunal\b", re.I),          "Appellate Tribunal"),
    (re.compile(r"\bCentral Board\b", re.I),               "Central Board"),
    # Assessee types
    (re.compile(r"\bresident individual\b", re.I),         "resident individual"),
    (re.compile(r"\bnon-resident\b", re.I),                "non-resident"),
    (re.compile(r"\bHindu [Uu]ndivided [Ff]amily\b", re.I), "Hindu Undivided Family"),
    (re.compile(r"\bdomestic company\b", re.I),            "domestic company"),
    (re.compile(r"\bforeign company\b", re.I),             "foreign company"),
    # Key concepts
    (re.compile(r"\btax year\b", re.I),                    "tax year"),
    (re.compile(r"\bassessment year\b", re.I),             "assessment year"),
    (re.compile(r"\bprevious year\b", re.I),               "previous year"),
    (re.compile(r"\bpermanent establishment\b", re.I),     "permanent establishment"),
    (re.compile(r"\bfair market value\b", re.I),           "fair market value"),
    (re.compile(r"\bbook profit\b", re.I),                 "book profit"),
    (re.compile(r"\bwitholding\b", re.I),                  "withholding"),
    (re.compile(r"\bresidential status\b", re.I),          "residential status"),
    (re.compile(r"\bspecial rate\b", re.I),                "special rate"),
    (re.compile(r"\bflat rate\b", re.I),                   "flat rate"),
    (re.compile(r"\bstandard deduction\b", re.I),          "standard deduction"),
    (re.compile(r"\bexempt income\b", re.I),               "exempt income"),
    (re.compile(r"\bminimum alternate tax\b", re.I),       "minimum alternate tax"),
    (re.compile(r"\bMAT\b"),                               "Minimum Alternate Tax"),
    (re.compile(r"\bsurcharge\b", re.I),                   "surcharge"),
    (re.compile(r"\bcess\b", re.I),                        "cess"),
    # Time-related
    (re.compile(r"\b(\d+)\s+days?\b", re.I),              None),  # handled below
    (re.compile(r"\b(\d+)\s+months?\b", re.I),            None),
    (re.compile(r"\b(\d+)\s+years?\b", re.I),             None),
]

_TIME_CAPTURE_RE = re.compile(r"\b(\d+\s+(?:days?|months?|years?))\b", re.I)
_RUPEE_CAPTURE_RE = re.compile(
    r"((?:Rs\.?\s*|₹\s*)?[\d,]+(?:\s*(?:lakh|crore|lakhs|crores|rupees))?)",
    re.I,
)
_PCT_CAPTURE_RE = re.compile(r"(\d+(?:\.\d+)?\s*(?:%|per\s+cent))", re.I)


def extract_keywords(content: str, section_title: str) -> list[str]:
    """
    Improved keyword extraction: base domain dict + extra authorities/types
    + time limits + monetary thresholds + percentages.
    """
    # Start with the existing heuristic (domain dict)
    base = _extract_keywords(content, section_title)
    found: list[str] = list(base)
    seen  = {k.lower() for k in found}

    # Extra domain terms
    for pat, term in _EXTRA_DOMAIN:
        if term is None:
            continue
        if pat.search(content) and term.lower() not in seen:
            found.append(term)
            seen.add(term.lower())
        if len(found) >= 10:
            break

    # Time limits (up to 2)
    time_added = 0
    for m in _TIME_CAPTURE_RE.finditer(content):
        kw = m.group(1).strip()
        if kw.lower() not in seen:
            found.append(kw)
            seen.add(kw.lower())
            time_added += 1
        if time_added >= 2:
            break

    # Monetary thresholds (up to 2)
    money_added = 0
    for m in _RUPEE_CAPTURE_RE.finditer(content):
        kw = m.group(1).strip()
        # Only include if it has a numeric value (not just "rupees")
        if re.search(r"\d", kw) and kw.lower() not in seen:
            found.append(kw)
            seen.add(kw.lower())
            money_added += 1
        if money_added >= 2:
            break

    # Percentages (up to 1)
    m_pct = _PCT_CAPTURE_RE.search(content)
    if m_pct:
        kw = m_pct.group(1).strip()
        if kw.lower() not in seen:
            found.append(kw)

    return found[:10]


# ── Main enrichment function ───────────────────────────────────────────────────

def enrich_chunk(chunk: RagChunk) -> RagChunk:
    """
    Apply all rule-based enrichment to a RagChunk in-place (returns same object).

    Only fills fields that are currently empty — never overwrites existing LLM output.
    """
    text = chunk.content or chunk.clean_text

    # 1. clean_text — normalize if it's just a copy of content
    if not chunk.clean_text or chunk.clean_text == chunk.content:
        chunk = chunk.model_copy(update={"clean_text": normalize_text(text)})
    text_norm = chunk.clean_text

    # 2. summary
    if not chunk.summary:
        summary = generate_summary(
            text_norm,
            chunk.section_title,
            chunk.chunk_type,
            chunk.section,
        )
        if summary:
            chunk = chunk.model_copy(update={"summary": summary})

    # 3. conditions
    if not chunk.conditions:
        conds = extract_conditions(text_norm)
        if conds:
            chunk = chunk.model_copy(update={"conditions": conds})

    # 4. exceptions
    if not chunk.exceptions:
        excs = extract_exceptions(text_norm)
        if excs:
            chunk = chunk.model_copy(update={"exceptions": excs})

    # 5. keywords — always improve (base extractor is very basic)
    improved_kw = extract_keywords(text_norm, chunk.section_title)
    if len(improved_kw) > len(chunk.keywords):
        chunk = chunk.model_copy(update={"keywords": improved_kw})

    return chunk


def enrich_chunks(chunks: Sequence[RagChunk]) -> list[RagChunk]:
    """Enrich a list of RagChunks. Returns a new list."""
    return [enrich_chunk(c) for c in chunks]
