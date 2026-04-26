"""
Classify sections under the five income heads and other categories.

The Income Tax Act organises income under these heads (Sec 14):
  A. Salaries
  B. Income from house property
  C. Profits and gains of business or profession
  D. Capital gains
  E. Income from other sources

Classification is done by chapter/part membership AND by section number ranges
(as a fallback for unclassified sections).
"""

from __future__ import annotations
from .structure import Section, ParsedAct

# Income head constants
HEAD_SALARIES = "Salaries"
HEAD_HOUSE_PROPERTY = "House Property"
HEAD_BUSINESS = "Business or Profession"
HEAD_CAPITAL_GAINS = "Capital Gains"
HEAD_OTHER_SOURCES = "Other Sources"
HEAD_DEDUCTIONS = "Deductions (Chapter VI-A)"
HEAD_TDS_TCS = "TDS / TCS"
HEAD_ADVANCE_TAX = "Advance Tax"
HEAD_ASSESSMENT = "Assessment & Procedure"
HEAD_APPEALS = "Appeals & Revision"
HEAD_PENALTIES = "Penalties & Prosecution"
HEAD_GENERAL = "General / Definitions"

ALL_HEADS = [
    HEAD_SALARIES,
    HEAD_HOUSE_PROPERTY,
    HEAD_BUSINESS,
    HEAD_CAPITAL_GAINS,
    HEAD_OTHER_SOURCES,
    HEAD_DEDUCTIONS,
    HEAD_TDS_TCS,
    HEAD_ADVANCE_TAX,
    HEAD_ASSESSMENT,
    HEAD_APPEALS,
    HEAD_PENALTIES,
    HEAD_GENERAL,
]

# ---------------------------------------------------------------------------
# Section number ranges for 2025 Act
# (Based on the Act structure: Section 1 onwards)
# ---------------------------------------------------------------------------

# 2025 Act section ranges (approximate — refined after parsing)
_2025_RANGES: list[tuple[int, int, str]] = [
    (1, 4, HEAD_GENERAL),               # Preliminary
    (5, 14, HEAD_GENERAL),              # Scope of total income, residential status
    (15, 20, HEAD_SALARIES),            # Salaries head
    (21, 32, HEAD_HOUSE_PROPERTY),      # House property head
    (33, 63, HEAD_BUSINESS),            # Business/profession head
    (64, 69, HEAD_CAPITAL_GAINS),       # Capital gains preliminary
    (70, 97, HEAD_CAPITAL_GAINS),       # Capital gains detailed
    (98, 110, HEAD_OTHER_SOURCES),      # Other sources
    (111, 115, HEAD_GENERAL),           # Aggregation of income
    (116, 155, HEAD_DEDUCTIONS),        # Chapter VI-A deductions
    (156, 195, HEAD_GENERAL),           # Set off, carry forward
    (196, 300, HEAD_GENERAL),           # Assessment, returns
    (301, 360, HEAD_ASSESSMENT),        # Assessment procedure
    (361, 395, HEAD_APPEALS),           # Appeals
    (390, 430, HEAD_TDS_TCS),           # TDS/TCS (Chapter XIX)
    (431, 460, HEAD_ADVANCE_TAX),       # Advance tax
    (461, 500, HEAD_PENALTIES),         # Penalties
    (501, 600, HEAD_GENERAL),           # Miscellaneous
]

# 1961 Act section ranges (approximate)
_1961_RANGES: list[tuple[int, int, str]] = [
    (1, 4, HEAD_GENERAL),
    (5, 14, HEAD_GENERAL),
    (15, 17, HEAD_SALARIES),
    (22, 27, HEAD_HOUSE_PROPERTY),
    (28, 44, HEAD_BUSINESS),
    (45, 55, HEAD_CAPITAL_GAINS),
    (56, 59, HEAD_OTHER_SOURCES),
    (60, 80, HEAD_GENERAL),             # Set off, aggregation
    (80, 80, HEAD_DEDUCTIONS),          # Chapter VIA deductions start
    (81, 100, HEAD_DEDUCTIONS),
    (100, 139, HEAD_GENERAL),           # Returns, assessment
    (140, 158, HEAD_ASSESSMENT),
    (159, 180, HEAD_GENERAL),
    (180, 192, HEAD_ADVANCE_TAX),
    (192, 194, HEAD_TDS_TCS),           # TDS on salaries
    (194, 206, HEAD_TDS_TCS),           # TDS sections
    (206, 234, HEAD_TDS_TCS),           # TCS and other TDS
    (234, 245, HEAD_ADVANCE_TAX),
    (245, 263, HEAD_ASSESSMENT),
    (263, 298, HEAD_APPEALS),
    (271, 280, HEAD_PENALTIES),
    (298, 400, HEAD_GENERAL),
]

# Chapter title → head mapping (for more accurate classification)
_CHAPTER_TITLE_KEYWORDS: dict[str, str] = {
    "salaries": HEAD_SALARIES,
    "salary": HEAD_SALARIES,
    "house property": HEAD_HOUSE_PROPERTY,
    "profits and gains of business": HEAD_BUSINESS,
    "business or profession": HEAD_BUSINESS,
    "capital gains": HEAD_CAPITAL_GAINS,
    "other sources": HEAD_OTHER_SOURCES,
    "deductions": HEAD_DEDUCTIONS,
    "deduction": HEAD_DEDUCTIONS,
    "tax deducted at source": HEAD_TDS_TCS,
    "tax collected at source": HEAD_TDS_TCS,
    "collection and recovery": HEAD_TDS_TCS,
    "advance tax": HEAD_ADVANCE_TAX,
    "advance payment": HEAD_ADVANCE_TAX,
    "assessment": HEAD_ASSESSMENT,
    "appeals": HEAD_APPEALS,
    "revision": HEAD_APPEALS,
    "penalties": HEAD_PENALTIES,
    "prosecution": HEAD_PENALTIES,
}


def _classify_by_chapter(chapter_title: str) -> str | None:
    lower = chapter_title.lower()
    for keyword, head in _CHAPTER_TITLE_KEYWORDS.items():
        if keyword in lower:
            return head
    return None


def _classify_by_range(section_number: str, act_year: str) -> str | None:
    # Extract numeric part
    m_num = __import__("re").match(r"^(\d+)", section_number)
    if not m_num:
        return None
    num = int(m_num.group(1))

    ranges = _2025_RANGES if act_year == "2025" else _1961_RANGES
    for start, end, head in ranges:
        if start <= num <= end:
            return head
    return None


def _classify_by_title_keywords(title: str) -> str | None:
    lower = title.lower()
    keyword_map = {
        "salary": HEAD_SALARIES,
        "perquisite": HEAD_SALARIES,
        "house property": HEAD_HOUSE_PROPERTY,
        "annual value": HEAD_HOUSE_PROPERTY,
        "rent": HEAD_HOUSE_PROPERTY,
        "capital gain": HEAD_CAPITAL_GAINS,
        "capital asset": HEAD_CAPITAL_GAINS,
        "transfer": HEAD_CAPITAL_GAINS,
        "deduction at source": HEAD_TDS_TCS,
        "tds": HEAD_TDS_TCS,
        "tax deducted": HEAD_TDS_TCS,
        "tax collected": HEAD_TDS_TCS,
        "advance tax": HEAD_ADVANCE_TAX,
        "business": HEAD_BUSINESS,
        "profession": HEAD_BUSINESS,
        "depreciation": HEAD_BUSINESS,
        "deduction in respect of": HEAD_DEDUCTIONS,
        "deduction under": HEAD_DEDUCTIONS,
        "appeal": HEAD_APPEALS,
        "tribunal": HEAD_APPEALS,
        "penalty": HEAD_PENALTIES,
        "prosecution": HEAD_PENALTIES,
        "assessment": HEAD_ASSESSMENT,
        "return of income": HEAD_ASSESSMENT,
    }
    for keyword, head in keyword_map.items():
        if keyword in lower:
            return head
    return None


def classify_section(section: Section) -> str:
    """
    Classify a section into an income head using multiple signals.
    Priority: chapter title > section title keywords > section number range > General
    """
    # 1. Chapter title
    if section.chapter_title:
        head = _classify_by_chapter(section.chapter_title)
        if head:
            return head

    # 2. Section title keywords
    head = _classify_by_title_keywords(section.title)
    if head:
        return head

    # 3. Section number range
    head = _classify_by_range(section.number, section.act)
    if head:
        return head

    return HEAD_GENERAL


def classify_all_sections(parsed: ParsedAct) -> None:
    """In-place classify all sections in a ParsedAct."""
    for section in parsed.sections:
        if section.income_head is None:
            section.income_head = classify_section(section)
