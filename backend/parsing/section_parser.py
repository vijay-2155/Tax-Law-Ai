"""
Section boundary detection and hierarchical parsing of Income Tax Act PDFs.

Key patterns observed (from actual PDF analysis):
- Section title: Bold standalone line  e.g. "Charge of Income-tax."
- Section body:  Bold "N. (1) body text..." on the NEXT line(s)
- Chapter:       Bold "CHAPTER XIX" followed by bold chapter title
- Subsections:   "(1)", "(2A)" at line start (non-bold)
- Clauses:       "(a)", "(b)" indented
- Sub-clauses:   "(i)", "(ii)" more indented
- Footer lines:  "Income Tax Department" / "Ministry of Finance, Government of India"
- Schedules:     "SCHEDULE I", "SCHEDULE II" — stop parsing sections here
"""

from __future__ import annotations
import re
from pathlib import Path

from .extractor import PageContent, TextLine, extract_pages, get_page_count
from .structure import Clause, Subsection, Section, Chapter, ParsedAct
from .table_parser import extract_all_tables

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_SEC_NUM_RE = re.compile(r"^(\d{1,3}[A-Z]{0,5})\.\s*(.*)", re.DOTALL)

_CHAPTER_RE = re.compile(r"^CHAPTER\s+([IVXLCDM]+)\s*$", re.IGNORECASE)

_SCHEDULE_RE = re.compile(r"^(THE\s+(\w+\s+)?)?SCHEDULE", re.IGNORECASE)

_SUBSEC_RE = re.compile(r"^\((\d+[A-Z]?)\)\s+(.*)", re.DOTALL)

_CLAUSE_RE = re.compile(r"^\(([a-z])\)\s+(.*)", re.DOTALL)

_SUBCLAUSE_RE = re.compile(r"^\(([ivxlcIVXLC]+)\)\s+(.*)", re.DOTALL)

_PROVISO_RE = re.compile(r"^Provided\s+(that|further\s+that)\s+(.*)", re.DOTALL | re.IGNORECASE)

_EXPL_RE = re.compile(
    r"^Explanation\s*(?:\d+)?[.\u2014\u2013\-]?\u2014?\s*(.*)",
    re.DOTALL | re.IGNORECASE,
)

# Lines that are page headers/footers to ignore
_IGNORE_LINES = {
    "income tax department",
    "ministry of finance, government of india",
    "ministry of finance",
}


def _should_ignore(text: str) -> bool:
    return text.lower().strip() in _IGNORE_LINES or len(text.strip()) == 0


def _is_chapter_line(line: TextLine) -> tuple[bool, str]:
    """Returns (is_chapter, chapter_number)."""
    text = line.text.strip()
    if line.is_bold:
        m = _CHAPTER_RE.match(text)
        if m:
            return True, m.group(1).upper()
    return False, ""


def _is_schedule_line(line: TextLine) -> bool:
    """Returns True if this line starts a Schedules section."""
    text = line.text.strip()
    return bool(line.is_bold and _SCHEDULE_RE.match(text))


def _is_section_number_line(line: TextLine) -> tuple[bool, str, str]:
    """
    Returns (is_section, section_number, body_start).
    Requires bold AND matches "N. body..." pattern.
    """
    text = line.text.strip()
    if not text or not line.is_bold:
        return False, "", ""

    m = _SEC_NUM_RE.match(text)
    if not m:
        return False, "", ""

    sec_num = m.group(1)
    body_start = m.group(2).strip()

    # Section numbers: digits with optional uppercase suffix (80C, 115BAC, 44AB etc.)
    if not re.match(r"^\d+[A-Z]{0,5}$", sec_num):
        return False, "", ""

    # Sanity: section number should be <= 600 (filter out schedule item numbers)
    try:
        base_num = int(re.match(r"^(\d+)", sec_num).group(1))
        if base_num > 600:
            return False, "", ""
    except (ValueError, AttributeError):
        return False, "", ""

    return True, sec_num, body_start


def _is_pending_title_line(line: TextLine) -> bool:
    """
    A bold standalone line that is NOT a chapter header, schedule header,
    section number, or ignored footer. These are section titles.
    """
    text = line.text.strip()
    if not text or not line.is_bold:
        return False
    if _should_ignore(text):
        return False
    if _CHAPTER_RE.match(text):
        return False
    if _SCHEDULE_RE.match(text):
        return False
    if _SEC_NUM_RE.match(text):
        return False
    # Must look like a title: doesn't start with ( or numbers, and is reasonably short
    if text.startswith("("):
        return False
    if len(text) > 200:
        return False
    return True


# ---------------------------------------------------------------------------
# Build section from accumulated lines
# ---------------------------------------------------------------------------

def _build_section(
    lines: list[str],
    number: str,
    title: str,
    act: str,
    chapter_number: str,
    chapter_title: str,
    page_start: int,
    page_end: int,
) -> Section:
    full_text = "\n".join(lines)

    section = Section(
        number=number,
        title=title,
        act=act,  # type: ignore
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        full_text=full_text,
        page_start=page_start,
        page_end=page_end,
    )

    # Parse subsections
    current_sub_num: str | None = None
    current_sub_lines: list[str] = []

    def flush_sub():
        if current_sub_num is None:
            return
        sub_text = " ".join(current_sub_lines)
        sub = Subsection(number=current_sub_num, text=sub_text.strip())
        _parse_clauses(sub, current_sub_lines)
        section.subsections.append(sub)

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip table markers
        if line.startswith("[TABLE]") or line.startswith("[/TABLE]"):
            continue

        m = _SUBSEC_RE.match(line)
        if m:
            flush_sub()
            current_sub_num = m.group(1)
            current_sub_lines = [m.group(2)]
        elif current_sub_num is not None:
            current_sub_lines.append(line)

    flush_sub()
    return section


def _parse_clauses(sub: Subsection, lines: list[str]) -> None:
    for line in lines:
        line = line.strip()
        m_prov = _PROVISO_RE.match(line)
        m_expl = _EXPL_RE.match(line)
        m_clause = _CLAUSE_RE.match(line)
        if m_prov:
            sub.provisos.append(m_prov.group(2).strip())
        elif m_expl:
            sub.explanations.append(m_expl.group(1).strip())
        elif m_clause:
            clause = Clause(identifier=m_clause.group(1), text=m_clause.group(2).strip())
            sub.clauses.append(clause)


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_act(
    pdf_path: str | Path,
    act_year: str,
    batch_size: int = 50,
    verbose: bool = True,
) -> ParsedAct:
    pdf_path = Path(pdf_path)
    total_pages = get_page_count(pdf_path)

    if verbose:
        print(f"Parsing {act_year} Act: {total_pages} pages from {pdf_path.name}")
        print("  Scanning for tables...")

    page_tables = extract_all_tables(pdf_path)
    if verbose:
        print(f"  Found tables on {len(page_tables)} pages")

    parsed = ParsedAct(act_year=act_year, total_pages=total_pages)  # type: ignore

    current_chapter_num = ""
    current_chapter_title = ""
    current_chapter_obj: Chapter | None = None
    pending_chapter_title = False  # Next bold line after CHAPTER is the title

    pending_section_title: str | None = None  # Title seen before section number line

    current_section_num: str | None = None
    current_section_title = ""
    current_section_lines: list[str] = []
    current_section_page_start = 0

    stop_parsing = False  # Set True when we hit Schedules

    def flush_section(page_end: int):
        nonlocal current_section_num, current_section_lines, current_section_title
        if current_section_num is None:
            return
        # Ensure page_end >= page_start (two sections on same page gives pn-1 < page_start)
        actual_page_end = max(page_end, current_section_page_start)
        sec = _build_section(
            lines=current_section_lines,
            number=current_section_num,
            title=current_section_title,
            act=act_year,
            chapter_number=current_chapter_num,
            chapter_title=current_chapter_title,
            page_start=current_section_page_start,
            page_end=actual_page_end,
        )
        parsed.sections.append(sec)
        if current_chapter_obj is not None:
            current_chapter_obj.sections.append(sec)
        current_section_num = None
        current_section_lines = []
        current_section_title = ""

    for batch_start in range(0, total_pages, batch_size):
        if stop_parsing:
            break
        batch_end = min(batch_start + batch_size, total_pages)
        if verbose:
            print(f"  Pages {batch_start + 1}–{batch_end}...", end="\r")

        pages = extract_pages(pdf_path, batch_start, batch_end)

        for page in pages:
            if stop_parsing:
                break
            pn = page.page_num

            for line in page.lines:
                text = line.text.strip()

                # Skip headers/footers
                if _should_ignore(text):
                    continue

                # Stop at Schedules
                if _is_schedule_line(line):
                    flush_section(pn)
                    stop_parsing = True
                    break

                # Chapter header
                is_chap, chap_num = _is_chapter_line(line)
                if is_chap:
                    flush_section(pn)
                    pending_section_title = None
                    current_chapter_num = chap_num
                    current_chapter_title = ""
                    pending_chapter_title = True
                    current_chapter_obj = Chapter(
                        number=chap_num,
                        title="",
                        act=act_year,  # type: ignore
                        page_start=pn,
                    )
                    parsed.chapters.append(current_chapter_obj)
                    continue

                # Chapter title (line right after CHAPTER header)
                if pending_chapter_title:
                    if line.is_bold and not _should_ignore(text):
                        current_chapter_title = text
                        if current_chapter_obj:
                            current_chapter_obj.title = text
                        pending_chapter_title = False
                    continue

                # Section number line (bold, starts with "N.")
                is_sec, sec_num, body_start = _is_section_number_line(line)
                if is_sec:
                    flush_section(pn - 1)
                    current_section_num = sec_num
                    # Use pending_section_title if we have one, else fall back to body start
                    current_section_title = (
                        pending_section_title
                        if pending_section_title
                        else (body_start[:120] if body_start else sec_num)
                    )
                    current_section_page_start = pn
                    current_section_lines = [f"{sec_num}. {body_start}"]
                    pending_section_title = None
                    continue

                # Potential section title (bold standalone line before section number)
                if _is_pending_title_line(line):
                    # If we're in a section already, this might be the next section's title
                    # Store it as pending — it will be consumed by the next section number line
                    pending_section_title = text
                    continue

                # Non-bold, non-special — accumulate as section body
                pending_section_title = None  # Reset if we hit non-bold body between title and number
                if current_section_num is not None:
                    current_section_lines.append(text)

            # Inject tables for this page
            if not stop_parsing:
                for tmd in page_tables.get(pn, []):
                    if current_section_num is not None:
                        current_section_lines.append("\n[TABLE]\n" + tmd + "\n[/TABLE]\n")

    flush_section(total_pages)

    if verbose:
        print(f"\n  Done. Found {len(parsed.sections)} sections, {len(parsed.chapters)} chapters.")

    return parsed
