"""
PyMuPDF-based text extraction with font metadata.
Detects bold text (section headers) using font flags.
"""

from __future__ import annotations
import fitz  # PyMuPDF
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TextSpan:
    text: str
    font_name: str
    font_size: float
    is_bold: bool
    is_italic: bool
    bbox: tuple[float, float, float, float]


@dataclass
class TextLine:
    spans: list[TextSpan] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def is_bold(self) -> bool:
        # Line is bold if its first non-whitespace span is bold
        for span in self.spans:
            if span.text.strip():
                return span.is_bold
        return False

    @property
    def is_all_bold(self) -> bool:
        non_empty = [s for s in self.spans if s.text.strip()]
        return bool(non_empty) and all(s.is_bold for s in non_empty)

    @property
    def dominant_font_size(self) -> float:
        if not self.spans:
            return 0.0
        return max(s.font_size for s in self.spans)


@dataclass
class PageContent:
    page_num: int          # 1-based
    lines: list[TextLine] = field(default_factory=list)
    raw_text: str = ""

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def _is_bold(flags: int) -> bool:
    """Check PyMuPDF font flags for bold (bit 4 = 2**4 = 16)."""
    return bool(flags & (2 ** 4))


def _is_italic(flags: int) -> bool:
    """Check PyMuPDF font flags for italic (bit 1 = 2)."""
    return bool(flags & 2)


def extract_pages(pdf_path: str | Path, start_page: int = 0, end_page: int | None = None) -> list[PageContent]:
    """
    Extract text with font metadata from PDF pages.
    Pages are 0-indexed internally, returned as 1-indexed in PageContent.
    Memory-efficient: processes page-by-page.
    """
    pdf_path = Path(pdf_path)
    pages: list[PageContent] = []

    with fitz.open(str(pdf_path)) as doc:
        total = len(doc)
        ep = end_page if end_page is not None else total

        for page_idx in range(start_page, min(ep, total)):
            page = doc[page_idx]
            page_content = PageContent(page_num=page_idx + 1)
            page_content.raw_text = page.get_text("text")

            # Extract structured text with font info
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

            for block in blocks:
                if block.get("type") != 0:  # type 0 = text, 1 = image
                    continue
                for para in block.get("lines", []):
                    line = TextLine()
                    for span in para.get("spans", []):
                        text = span.get("text", "")
                        if not text:
                            continue
                        flags = span.get("flags", 0)
                        ts = TextSpan(
                            text=text,
                            font_name=span.get("font", ""),
                            font_size=round(span.get("size", 0), 1),
                            is_bold=_is_bold(flags),
                            is_italic=_is_italic(flags),
                            bbox=tuple(span.get("bbox", (0, 0, 0, 0))),
                        )
                        line.spans.append(ts)
                    if line.spans:
                        page_content.lines.append(line)

            pages.append(page_content)

    return pages


def get_page_count(pdf_path: str | Path) -> int:
    """Return total number of pages in PDF without loading it fully."""
    with fitz.open(str(pdf_path)) as doc:
        return len(doc)
