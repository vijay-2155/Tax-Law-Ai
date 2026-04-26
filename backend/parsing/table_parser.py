"""
Table extraction from PDF pages using PyMuPDF's find_tables().
Used for TDS/TCS rate tables, tax slabs, and schedules.
"""

from __future__ import annotations
import fitz
from pathlib import Path


def _table_to_markdown(table: fitz.table.Table) -> str:
    """Convert a PyMuPDF Table to a markdown table string."""
    rows = table.extract()
    if not rows:
        return ""

    # Clean cell text: replace None with empty, strip whitespace, remove newlines
    cleaned = []
    for row in rows:
        cleaned_row = []
        for cell in row:
            if cell is None:
                cleaned_row.append("")
            else:
                cleaned_row.append(str(cell).replace("\n", " ").strip())
        cleaned.append(cleaned_row)

    if not cleaned:
        return ""

    col_count = max(len(row) for row in cleaned)

    # Pad rows to equal column count
    padded = [row + [""] * (col_count - len(row)) for row in cleaned]

    # Calculate column widths
    widths = [max(len(str(r[i])) for r in padded) for i in range(col_count)]
    widths = [max(w, 3) for w in widths]

    lines = []
    for i, row in enumerate(padded):
        cells = [str(row[j]).ljust(widths[j]) for j in range(col_count)]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("|" + "|".join(["-" * (w + 2) for w in widths]) + "|")

    return "\n".join(lines)


def extract_tables_from_page(pdf_path: str | Path, page_num: int) -> list[str]:
    """
    Extract all tables from a page as markdown strings.
    page_num is 1-based.
    Returns list of markdown table strings.
    """
    pdf_path = Path(pdf_path)
    results: list[str] = []

    with fitz.open(str(pdf_path)) as doc:
        if page_num < 1 or page_num > len(doc):
            return []

        page = doc[page_num - 1]
        try:
            tables = page.find_tables()
            for table in tables:
                md = _table_to_markdown(table)
                if md:
                    results.append(md)
        except Exception:
            pass  # find_tables() may fail on some page layouts

    return results


def extract_all_tables(pdf_path: str | Path) -> dict[int, list[str]]:
    """
    Scan all pages for tables. Returns {page_num: [markdown_table, ...]}
    """
    pdf_path = Path(pdf_path)
    result: dict[int, list[str]] = {}

    with fitz.open(str(pdf_path)) as doc:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            try:
                tables = page.find_tables()
                page_tables = []
                for table in tables:
                    md = _table_to_markdown(table)
                    if md:
                        page_tables.append(md)
                if page_tables:
                    result[page_idx + 1] = page_tables
            except Exception:
                pass

    return result
