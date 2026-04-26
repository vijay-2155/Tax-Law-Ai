#!/usr/bin/env python3
"""
PDF → chunks → Qwen3 embed → Qdrant.

Reads directly from the PDF (no intermediate parsed JSON).
Captures complete section text including all nested sub-clauses.

Pipeline:
  1. PyMuPDF bold-aware extraction → sections with titles
  2. Income head classification (chapter + section-range based)
  3. Two-level chunking: full-section + sub-section
  4. Qwen3 embedding via local Ollama
  5. Qdrant upsert with rich payload

Usage:
  python scripts/extract_and_index.py --act 2025
  python scripts/extract_and_index.py --act 1961
  python scripts/extract_and_index.py --act 2025 --dry-run     # extract only, no embed
  python scripts/extract_and_index.py --act 2025 --limit 50    # first 50 sections
"""

from __future__ import annotations

import sys
import re
import json
import time
import hashlib
import argparse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DATA_DIR, PDF_DIR, QDRANT_URL, QDRANT_API_KEY


# ── Income head classification ─────────────────────────────────────────────────

# 2025 Act: chapter → income head (broad)
_CHAPTER_HEAD_2025: dict[str, str] = {
    "I":     "General / Definitions",
    "II":    "Basis of Charge",
    "III":   "Exempt Income",
    "IV":    "Computation of Income",   # refined by section range below
    "V":     "Income of Other Persons",
    "VI":    "Aggregation of Income",
    "VII":   "Set-off and Carry Forward",
    "VIII":  "Deductions",
    "IX":    "Rebates and Reliefs",
    "X":     "Anti-Avoidance",
    "XI":    "General Anti-Avoidance Rule",
    "XII":   "Mode of Payment",
    "XIII":  "Special Tax Rates",
    "XIV":   "Tax Administration",
    "XV":    "Return of Income",
    "XVI":   "Assessment",
    "XVII":  "Special Provisions",
    "XVIII": "Appeals and Revisions",
    "XIX":   "Collection and Recovery",
    "XX":    "Refunds",
    "XXI":   "Penalties",
    "XXII":  "Offences and Prosecution",
    "XXIII": "Miscellaneous",
}

# Chapter IV, 2025 Act — section ranges → income head (Parts A-F)
# Determined from PDF analysis: Part boundaries at sections 13, 15, 20, 26, 67, 92
_CHAPTER_IV_RANGES_2025 = [
    (13,  14,  "Heads of Income"),
    (15,  19,  "Salaries"),
    (20,  25,  "House Property"),
    (26,  66,  "Business and Profession"),
    (67,  91,  "Capital Gains"),
    (92,  999, "Income from Other Sources"),
]

# 1961 Act: classic income head ranges
_CHAPTER_HEAD_1961: dict[str, str] = {
    "I":     "General / Definitions",
    "II":    "Basis of Charge",
    "III":   "Exempt Income",
    "IV":    "Computation of Income",
    "V":     "Income of Other Persons",
    "VI":    "Aggregation of Income",
    "VIA":   "Deductions",
    "VII":   "Set-off and Carry Forward",
    "VIII":  "Rebates and Reliefs",
    "IX":    "Tax Administration",
    "X":     "Special Tax Rates",
    "XI":    "Anti-Avoidance",
    "XII":   "Collection and Recovery",
    "XIIA":  "Collection and Recovery",
    "XIIB":  "TDS / TCS",
    "XIII":  "Tax Administration",
    "XIV":   "Return of Income",
    "XIV_B": "Assessment",
    "XV":    "Liability to Pay Tax",
    "XVI":   "Special Provisions",
    "XVII":  "TDS / TCS",
    "XVIII": "Penalties",
    "XIX":   "Collection and Recovery",
    "XX":    "Appeals and Revisions",
    "XXI":   "Offences and Prosecution",
    "XXII":  "Miscellaneous",
}

_CHAPTER_IV_RANGES_1961 = [
    (14,  14,  "Heads of Income"),
    (15,  17,  "Salaries"),
    (22,  27,  "House Property"),
    (28,  44,  "Business and Profession"),
    (45,  55,  "Capital Gains"),
    (56,  59,  "Income from Other Sources"),
]


def classify_income_head(chapter: str, section_num: str, act_year: str) -> str:
    """Map (chapter, section_number) → income head string."""
    try:
        sec_int = int(re.match(r"\d+", section_num).group())
    except (AttributeError, ValueError):
        sec_int = 0

    if act_year == "2025":
        head_map = _CHAPTER_HEAD_2025
        iv_ranges = _CHAPTER_IV_RANGES_2025
    else:
        head_map = _CHAPTER_HEAD_1961
        iv_ranges = _CHAPTER_IV_RANGES_1961

    base = head_map.get(chapter.upper(), "General / Definitions")

    if chapter.upper() == "IV" and sec_int > 0:
        for lo, hi, head in iv_ranges:
            if lo <= sec_int <= hi:
                return head

    return base


# ── PDF text extraction ────────────────────────────────────────────────────────

_FOOTER_RE = re.compile(
    r"(?:Income Tax Department|Ministry of Finance,?\s*Government of India)\s*",
    re.IGNORECASE,
)
_CHAPTER_RE  = re.compile(r"^CHAPTER\s+([IVXLCDM]+)\s*$", re.IGNORECASE)
_PART_RE     = re.compile(r"^([A-F])\.\s*[—\-]?\s*(.+)$")
_SECTION_RE  = re.compile(r"^(\d{1,3}[A-Z]{0,5})\.\s+(.+)", re.DOTALL)
# Must be a standalone short header line, not body text that starts with "Schedule X, ..."
_SCHEDULE_RE = re.compile(r"^(?:THE\s+)?(?:\w+\s+)?SCHEDULE(?:\s+[IVXLCDM]+)?\s*$", re.IGNORECASE)


def _get_bold_lines(page: fitz.Page) -> set[str]:
    """
    Return a set of line texts that are bold on this page.
    Called ONCE per page — not per line.
    """
    bold: set[str] = set()
    try:
        blocks = page.get_text("dict", flags=0).get("blocks", [])
        for block in blocks:
            for ln in block.get("lines", []):
                spans = ln.get("spans", [])
                line_text = "".join(s["text"] for s in spans).strip()
                if not line_text:
                    continue
                # A line is "bold" if the majority of its chars come from bold spans
                bold_chars = sum(len(s["text"]) for s in spans if s.get("flags", 0) & 2**4)
                total_chars = sum(len(s["text"]) for s in spans)
                if total_chars > 0 and bold_chars / total_chars > 0.5:
                    bold.add(line_text)
    except Exception:
        pass
    return bold


@dataclass
class RawSection:
    number: str
    title: str
    chapter: str
    chapter_title: str
    part: str          # "A", "B", etc. (Chapter IV only)
    income_head: str
    full_text: str
    page_start: int
    page_end: int
    act_year: str


def extract_sections_from_pdf(pdf_path: Path, act_year: str, verbose: bool = True) -> list[RawSection]:
    """
    Extract sections directly from PDF using bold-aware line detection.

    For each section captures:
    - Complete raw text (all nested sub-clauses preserved)
    - Section title (bold line preceding the section number)
    - Chapter + Part → income head
    """
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    if verbose:
        print(f"  PDF: {pdf_path.name} ({total_pages} pages)")

    sections: list[RawSection] = []

    current_chapter      = ""
    current_chapter_title = ""
    current_part         = ""

    pending_title: str | None = None   # bold line seen before section number

    current_sec_num:   str | None = None
    current_sec_title: str = ""
    current_lines:     list[str] = []
    current_page_start = 0

    stop = False

    def flush(page_end: int) -> None:
        nonlocal current_sec_num, current_sec_title, current_lines, current_page_start
        if current_sec_num is None:
            return
        text = "\n".join(current_lines).strip()
        text = _FOOTER_RE.sub("", text).strip()
        if not text:
            return
        head = classify_income_head(current_chapter, current_sec_num, act_year)
        sections.append(RawSection(
            number        = current_sec_num,
            title         = current_sec_title,
            chapter       = current_chapter,
            chapter_title = current_chapter_title,
            part          = current_part,
            income_head   = head,
            full_text     = text,
            page_start    = current_page_start,
            page_end      = max(page_end, current_page_start),
            act_year      = act_year,
        ))
        current_sec_num   = None
        current_sec_title = ""
        current_lines     = []

    for page_num in range(total_pages):
        if stop:
            break

        page = doc[page_num]
        raw_text = page.get_text()
        pn = page_num + 1  # 1-indexed

        # Pre-compute bold lines once per page
        bold_lines = _get_bold_lines(page)

        if verbose and page_num % 50 == 0:
            print(f"  Page {pn}/{total_pages}...", end="\r", flush=True)

        for line in raw_text.splitlines():
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Skip known footers
            if _FOOTER_RE.match(line_stripped):
                continue

            # Stop at schedules
            if _SCHEDULE_RE.match(line_stripped):
                flush(pn)
                stop = True
                break

            is_bold = line_stripped in bold_lines

            # Chapter header (bold, matches CHAPTER Roman-numeral)
            m_ch = _CHAPTER_RE.match(line_stripped)
            if m_ch and is_bold:
                flush(pn)
                current_chapter       = m_ch.group(1).upper()
                current_chapter_title = ""
                current_part          = ""
                pending_title         = None
                continue

            # Chapter title (bold line right after CHAPTER header)
            if current_chapter and not current_chapter_title and is_bold and len(line_stripped) < 120:
                current_chapter_title = line_stripped
                continue

            # Part header inside Chapter IV (e.g. "B.-Salaries")
            m_pt = _PART_RE.match(line_stripped)
            if m_pt and current_chapter == "IV":
                current_part = m_pt.group(1)
                continue

            # Section number line ("N. body..." — may or may not be bold)
            m_sec = _SECTION_RE.match(line_stripped)
            if m_sec:
                sec_num = m_sec.group(1)
                body    = m_sec.group(2).strip()
                # Filter out schedule item numbers (> 600)
                try:
                    if int(re.match(r"\d+", sec_num).group()) > 600:
                        if current_sec_num:
                            current_lines.append(line_stripped)
                        continue
                except (AttributeError, ValueError):
                    pass

                flush(pn - 1)
                current_sec_num    = sec_num
                current_sec_title  = pending_title or body[:100]
                current_page_start = pn
                current_lines      = [line_stripped]
                pending_title      = None
                continue

            # Bold short non-section line → candidate section title
            if (
                is_bold
                and not line_stripped.startswith("(")
                and not (line_stripped[0].isdigit() if line_stripped else False)
                and len(line_stripped) < 120
                and not _CHAPTER_RE.match(line_stripped)
                and not _SCHEDULE_RE.match(line_stripped)
            ):
                pending_title = line_stripped
                continue

            # Regular body text — accumulate
            pending_title = None
            if current_sec_num is not None:
                current_lines.append(line_stripped)

    flush(total_pages)
    doc.close()

    if verbose:
        print(f"\n  Extracted {len(sections)} sections.")

    return sections


# ── Chunking ───────────────────────────────────────────────────────────────────

# Split subsections at: "(1)", "(2A)", etc. at line start
_SUBSEC_SPLIT_RE = re.compile(r"\n(?=\(\d+[A-Z]?\)\s)")
# Clean up spacing artifacts from PDF
_SPACE_FIX_RE   = re.compile(r"\(\s+([a-zA-Z0-9]+)\s+\)")
_MULTI_NL_RE    = re.compile(r"\n{3,}")

_MAX_CHUNK_CHARS = 1500   # target max chars per sub-section chunk
_MIN_CHUNK_CHARS = 100    # sub-chunks shorter than this get merged with next


@dataclass
class Chunk:
    chunk_id:       str
    act_year:       str
    section:        str
    section_title:  str
    chapter:        str
    chapter_title:  str
    part:           str
    income_head:    str
    chunk_index:    int   # 0 = full section overview, 1+ = sub-section chunks
    chunk_type:     str   # "section" | "subsection"
    text:           str   # text sent for embedding
    page_start:     int
    page_end:       int

    def to_payload(self) -> dict:
        return asdict(self)


def _clean_text(text: str) -> str:
    """Fix spacing artifacts from PDF extraction."""
    text = _SPACE_FIX_RE.sub(r"(\1)", text)   # "( a )" → "(a)"
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def _chunk_id(act_year: str, section: str, index: int) -> str:
    base = f"IT{act_year}_S{section}_{index}"
    return base


def chunk_section(sec: RawSection) -> list[Chunk]:
    """
    Produce chunks for one section.

    Chunk 0: Full section (title + first 600 chars of body) — broad context.
    Chunks 1+: Each subsection split at (1), (2), etc. boundaries ≤ 1500 chars.
    """
    full = _clean_text(sec.full_text)
    title_prefix = f"{sec.title}\n"

    common = dict(
        act_year      = sec.act_year,
        section       = sec.number,
        section_title = sec.title,
        chapter       = sec.chapter,
        chapter_title = sec.chapter_title,
        part          = sec.part,
        income_head   = sec.income_head,
        page_start    = sec.page_start,
        page_end      = sec.page_end,
    )

    chunks: list[Chunk] = []

    # Chunk 0 — section overview (title + truncated body for broad retrieval)
    overview_text = title_prefix + full[:800]
    chunks.append(Chunk(
        **common,
        chunk_id    = _chunk_id(sec.act_year, sec.number, 0),
        chunk_index = 0,
        chunk_type  = "section",
        text        = overview_text,
    ))

    # Sub-section chunks
    parts = _SUBSEC_SPLIT_RE.split(full)
    if len(parts) <= 1:
        # No subsection splits found — try splitting on (a), (b) at line start
        parts = re.split(r"\n(?=\([a-z]\)\s)", full)

    # Merge very short parts with the next one
    merged: list[str] = []
    buf = ""
    for p in parts:
        if buf and len(buf) + len(p) < _MIN_CHUNK_CHARS:
            buf += "\n" + p
        else:
            if buf:
                merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)

    # Split any part that's still too long
    final_parts: list[str] = []
    for p in merged:
        if len(p) <= _MAX_CHUNK_CHARS:
            final_parts.append(p)
        else:
            # Hard split at sentence boundaries
            while len(p) > _MAX_CHUNK_CHARS:
                split_at = p.rfind("\n", 0, _MAX_CHUNK_CHARS)
                if split_at < 200:
                    split_at = _MAX_CHUNK_CHARS
                final_parts.append(p[:split_at])
                p = p[split_at:].lstrip()
            if p:
                final_parts.append(p)

    for idx, part_text in enumerate(final_parts, 1):
        part_text = part_text.strip()
        if not part_text:
            continue
        embed_text = title_prefix + part_text
        chunks.append(Chunk(
            **common,
            chunk_id    = _chunk_id(sec.act_year, sec.number, idx),
            chunk_index = idx,
            chunk_type  = "subsection",
            text        = embed_text,
        ))

    return chunks


# ── Embedding ──────────────────────────────────────────────────────────────────

def embed_chunks(
    chunks: list[Chunk],
    batch_size: int = 16,
    verbose: bool = True,
) -> list[list[float]]:
    """Embed chunks using qwen3-embedding via local Ollama."""
    import httpx
    from backend.config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL

    texts = [c.text for c in chunks]
    vectors: list[list[float]] = []
    total_batches = (len(texts) + batch_size - 1) // batch_size

    for b_start in range(0, len(texts), batch_size):
        batch = texts[b_start: b_start + batch_size]
        b_num = b_start // batch_size + 1
        if verbose:
            print(f"  Embedding batch {b_num}/{total_batches} "
                  f"({b_start+1}–{b_start+len(batch)}/{len(texts)})",
                  end="\r", flush=True)

        for attempt in range(4):
            try:
                with httpx.Client(timeout=180.0) as client:
                    resp = client.post(
                        f"{OLLAMA_BASE_URL}/api/embed",
                        json={"model": OLLAMA_EMBED_MODEL, "input": batch},
                    )
                    resp.raise_for_status()
                    embeddings = resp.json().get("embeddings", [])
                    if len(embeddings) != len(batch):
                        raise ValueError(f"Expected {len(batch)}, got {len(embeddings)}")
                    vectors.extend(embeddings)
                    break
            except Exception as e:
                if attempt < 3:
                    wait = 2 ** attempt
                    if verbose:
                        print(f"\n  Retry {attempt+1} (error: {e}), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"Embedding failed: {e}") from e

    if verbose:
        print(f"\n  Embedded {len(vectors)} chunks.")
    return vectors


# ── Qdrant indexing ────────────────────────────────────────────────────────────

_COLLECTION = "tax_{act_year}"


def index_chunks(
    chunks: list[Chunk],
    vectors: list[list[float]],
    act_year: str,
    embed_dim: int,
    verbose: bool = True,
) -> None:
    """Create/recreate Qdrant collection and upsert all chunks."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, PointStruct,
        PayloadSchemaType, TextIndexParams, TokenizerType,
    )

    col_name = _COLLECTION.format(act_year=act_year)
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=120)

    # Recreate collection
    existing = [c.name for c in client.get_collections().collections]
    if col_name in existing:
        client.delete_collection(col_name)
        if verbose:
            print(f"  Deleted old collection '{col_name}'")

    client.create_collection(
        collection_name = col_name,
        vectors_config  = VectorParams(size=embed_dim, distance=Distance.COSINE),
    )

    # Payload indices for fast filtering
    for kw_field in ("section", "income_head", "act_year", "chapter", "chunk_type", "part"):
        client.create_payload_index(
            collection_name = col_name,
            field_name      = kw_field,
            field_schema    = PayloadSchemaType.KEYWORD,
        )
    for ft_field in ("text", "section_title"):
        client.create_payload_index(
            collection_name = col_name,
            field_name      = ft_field,
            field_schema    = TextIndexParams(
                type="text",
                tokenizer=TokenizerType.WORD,
                lowercase=True,
            ),
        )

    if verbose:
        print(f"  Created collection '{col_name}' (dim={embed_dim}, cosine)")

    # Upsert in batches
    batch_size = 32
    total_batches = (len(chunks) + batch_size - 1) // batch_size
    for b_start in range(0, len(chunks), batch_size):
        bc = chunks[b_start: b_start + batch_size]
        bv = vectors[b_start: b_start + batch_size]

        points = [
            PointStruct(
                id      = abs(int(hashlib.md5(c.chunk_id.encode()).hexdigest(), 16)) % (2**63),
                vector  = v,
                payload = c.to_payload(),
            )
            for c, v in zip(bc, bv)
        ]

        for attempt in range(3):
            try:
                client.upsert(collection_name=col_name, points=points)
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    raise

        b_num = b_start // batch_size + 1
        if verbose:
            done = min(b_start + batch_size, len(chunks))
            print(f"  Indexed batch {b_num}/{total_batches} ({done}/{len(chunks)})", end="\r")

    if verbose:
        count = client.get_collection(col_name).points_count
        print(f"\n  Done: {count} points in '{col_name}' (Qdrant)")

    client.close()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Extract PDF → chunk → embed (qwen3) → index (Qdrant)"
    )
    ap.add_argument("--act", choices=["1961", "2025"], required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Extract and chunk only — skip embedding and indexing")
    ap.add_argument("--limit", type=int, default=0,
                    help="Process only first N sections (smoke test)")
    ap.add_argument("--save-chunks", action="store_true",
                    help="Save chunks to data/chunks_{act}.json for inspection")
    args = ap.parse_args()

    pdf_map = {"2025": "income_tax_act_2025.pdf", "1961": "income_tax_act_1961.pdf"}
    pdf_path = PDF_DIR / pdf_map[args.act]

    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    print("=" * 60)
    print(f"PDF → Qdrant Pipeline  |  Act: {args.act}")
    print("=" * 60)

    # 1. Extract sections
    print("\n[1/4] Extracting sections from PDF...")
    t0 = time.time()
    sections = extract_sections_from_pdf(pdf_path, args.act, verbose=True)

    if args.limit:
        sections = sections[: args.limit]
        print(f"  [limit] Using first {args.limit} sections")

    print(f"  Sections extracted: {len(sections)}  ({time.time()-t0:.1f}s)")

    # Print income head distribution
    from collections import Counter
    head_counts = Counter(s.income_head for s in sections)
    print("\n  Income head distribution:")
    for head, cnt in sorted(head_counts.items(), key=lambda x: -x[1]):
        print(f"    {head:<35} {cnt:>4}")

    # 2. Chunk
    print("\n[2/4] Chunking sections...")
    t1 = time.time()
    all_chunks: list[Chunk] = []
    for sec in sections:
        all_chunks.extend(chunk_section(sec))
    print(f"  Total chunks: {len(all_chunks)}  ({time.time()-t1:.2f}s)")

    # Section vs subsection distribution
    by_type = Counter(c.chunk_type for c in all_chunks)
    print(f"  section chunks:    {by_type.get('section', 0)}")
    print(f"  subsection chunks: {by_type.get('subsection', 0)}")

    # Save chunks for inspection
    if args.save_chunks or args.dry_run:
        out_path = DATA_DIR / f"chunks_{args.act}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([c.to_payload() for c in all_chunks], f, ensure_ascii=False, indent=2)
        print(f"\n  Chunks saved → {out_path.name} ({out_path.stat().st_size/1024/1024:.1f} MB)")

    if args.dry_run:
        print("\n[dry-run] Skipping embedding and indexing.")
        # Show a few sample chunks
        print("\n  Sample chunks:")
        for c in all_chunks[:3]:
            print(f"\n  [{c.chunk_id}] {c.income_head} | {c.chunk_type}")
            print(f"  text: {c.text[:250]}")
        return

    # 3. Embed
    print("\n[3/4] Embedding with qwen3...")
    from backend.indexing.embedder import EMBED_DIM, check_ollama_available
    from backend.config import OLLAMA_EMBED_MODEL

    if not check_ollama_available():
        print(f"ERROR: Ollama not available or model '{OLLAMA_EMBED_MODEL}' not pulled.")
        print("  Start: ollama serve")
        print(f"  Pull:  ollama pull {OLLAMA_EMBED_MODEL}")
        sys.exit(1)

    t2 = time.time()
    vectors = embed_chunks(all_chunks, verbose=True)
    print(f"  Embedding done ({time.time()-t2:.1f}s)")

    # Cache vectors
    import numpy as np
    vec_path = DATA_DIR / f"vectors_new_{args.act}.npy"
    np.save(str(vec_path), np.array(vectors, dtype="float32"))
    print(f"  Vectors cached → {vec_path.name}")

    # 4. Index
    print("\n[4/4] Indexing into Qdrant...")
    if not QDRANT_URL or not QDRANT_API_KEY:
        print("ERROR: QDRANT_URL / QDRANT_API_KEY not set in .env")
        sys.exit(1)

    t3 = time.time()
    index_chunks(all_chunks, vectors, args.act, EMBED_DIM, verbose=True)
    print(f"  Indexing done ({time.time()-t3:.1f}s)")

    total = time.time() - t0
    print(f"\n✓ Done: {len(sections)} sections → {len(all_chunks)} chunks "
          f"→ Qdrant  [{total:.0f}s total]")


if __name__ == "__main__":
    main()
