#!/usr/bin/env python3
"""
VL extraction of Income Tax Act 2025 using Qwen3-VL via Ollama (local) or OpenRouter (cloud).

Pipeline:
  1. Render each PDF page to a JPEG image at 150 DPI (PyMuPDF)
  2. Call Qwen3-VL — extracts raw_text + structured subsections per page
  3. Cache each page result in backend/data/vl_cache_2025/page_NNNN.json
  4. Merge all page outputs into a single ParsedAct-compatible JSON
  5. Apply income head classification
  6. Save to backend/data/parsed_2025_vl.json

Usage:
    python scripts/vl_extract_2025.py                        # Ollama local, all pages
    python scripts/vl_extract_2025.py --pages 1-10           # Only pages 1-10
    python scripts/vl_extract_2025.py --merge-only           # Only merge cached pages
    python scripts/vl_extract_2025.py --provider openrouter  # Use OpenRouter cloud
    python scripts/vl_extract_2025.py --cost-estimate        # Cost estimate (OpenRouter only)

Providers:
    ollama      (default) Uses http://localhost:11434  model: qwen3-vl:latest  — FREE
    openrouter  Uses OpenRouter API  —  requires OPENROUTER_API_KEY in .env
"""

from __future__ import annotations

import sys
import os
import json
import time
import base64
import argparse
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=False)

from backend.parsing.structure import Clause, Subsection, Section, Chapter, ParsedAct
from backend.parsing.head_classifier import classify_all_sections

# ── Paths ──────────────────────────────────────────────────────────────────────

PDF_PATH    = ROOT / "pdfs" / "income_tax_act_2025.pdf"
CACHE_DIR   = ROOT / "backend" / "data" / "vl_cache_2025"
OUTPUT_PATH = ROOT / "backend" / "data" / "parsed_2025_vl.json"

# ── Provider configs ───────────────────────────────────────────────────────────

PROVIDERS = {
    "ollama": {
        "base_url"  : os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1",
        "api_key"   : "ollama",
        "model"     : "qwen3-vl:latest",
        "max_tokens": 4096,
        "headers"   : {},
    },
    "openrouter": {
        "base_url"  : "https://openrouter.ai/api/v1",
        "api_key"   : os.environ.get("OPENROUTER_API_KEY", ""),
        "model"     : "qwen/qwen3-vl-235b-a22b-instruct",
        "max_tokens": 8192,
        "headers"   : {
            "HTTP-Referer": "https://incometaxvalidator.local",
            "X-Title"     : "Income Tax Act 2025 VL Parser",
        },
    },
}

DPI          = 150
JPEG_QUALITY = 85
MAX_RETRIES  = 3
RETRY_DELAYS = [5, 15, 30]

# OpenRouter cost constants
COST_INPUT_PER_M  = 0.20
COST_OUTPUT_PER_M = 0.88
EST_IMAGE_TOKENS  = 1500
EST_PROMPT_TOKENS = 700
EST_OUTPUT_TOKENS = 2000


# ── OpenAI client factory ──────────────────────────────────────────────────────

def make_client(provider: str):
    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: openai package missing.  pip install openai")
        sys.exit(1)

    cfg = PROVIDERS[provider]

    if provider == "openrouter" and not cfg["api_key"]:
        print("ERROR: OPENROUTER_API_KEY not set in .env")
        sys.exit(1)

    if provider == "ollama":
        # Quick reachability check
        import urllib.request, urllib.error
        try:
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        except Exception:
            print("ERROR: Ollama not reachable at http://localhost:11434 — is it running?")
            sys.exit(1)

    return OpenAI(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        default_headers=cfg["headers"],
    )


# ── Page rendering ─────────────────────────────────────────────────────────────

def render_page_jpeg_b64(doc: fitz.Document, page_idx: int) -> str:
    """Render PDF page (0-indexed) → base64 JPEG string."""
    page = doc[page_idx]
    mat  = fitz.Matrix(DPI / 72, DPI / 72)
    pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
    jpeg = pix.tobytes(output="jpeg", jpg_quality=JPEG_QUALITY)
    return base64.b64encode(jpeg).decode("ascii")


# ── Prompt ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert legal document parser specialising in Indian Income Tax legislation.

Extract the COMPLETE structured content from this page of the Income Tax Act, 2025 and
return a single valid JSON object — no markdown fences, no commentary.

STRICT RULES:
1. Copy ALL text VERBATIM — do NOT paraphrase, summarise, or omit anything.
2. Section numbers look like  "80C."  "392."  "2."  (bold, at line-start).
3. Subsections: "(1)"  "(2)"  "(2A)"  at paragraph start.
4. Clauses: lowercase  "(a)" "(b)" "(c)".
5. Sub-clauses: Roman numerals  "(i)" "(ii)" "(iii)".
6. Sub-sub-clauses: uppercase  "(A)" "(B)" "(C)".
7. Provisos start with  "Provided that"  or  "Provided further that".
8. Explanations start with  "Explanation"  followed by a dash, period, or number.
9. Chapter headers: "CHAPTER I", "CHAPTER VIII" — bold uppercase.
10. Tables: include all cell values in the relevant subsection raw_text.
11. If a section STARTED on the previous page → set  continues_from_prev: true.
12. If a section ENDS on the next page → set  continues_to_next: true.
13. If you see "SCHEDULE" headers → set  schedule_start: true  and stop.
14. Ignore page headers/footers: "Income Tax Department", "Ministry of Finance".
15. Return ONLY valid JSON — nothing else.

REQUIRED JSON SCHEMA:
{
  "page": <integer>,
  "chapter_header": null | {"number": "<Roman e.g. VIII>", "title": "<string>"},
  "schedule_start": false,
  "content_blocks": [
    {
      "type": "section",
      "number": "<e.g. 80C>",
      "title": "<section title>",
      "continues_from_prev": false,
      "continues_to_next": false,
      "raw_text": "<verbatim full text of this section as it appears on this page>",
      "subsections": [
        {
          "number": "<e.g. 1 or 2A>",
          "text": "<verbatim subsection intro text>",
          "clauses": [
            {
              "identifier": "<e.g. a>",
              "text": "<verbatim clause text>",
              "sub_clauses": [
                {
                  "identifier": "<e.g. i>",
                  "text": "<verbatim text>",
                  "sub_clauses": [
                    {"identifier": "<e.g. A>", "text": "<verbatim text>", "sub_clauses": []}
                  ]
                }
              ]
            }
          ],
          "provisos": ["<verbatim text after Provided that>"],
          "explanations": ["<verbatim text after Explanation.—>"]
        }
      ]
    }
  ]
}"""


def build_user_message(page_num: int, prev_context: str, no_think: bool = False) -> str:
    ctx = ""
    if prev_context:
        ctx = (
            f"\n\nCONTINUATION HINT — this section was incomplete on the previous page. "
            f"If it continues here mark continues_from_prev=true:\n{prev_context}\n"
        )
    prefix = "/no_think " if no_think else ""
    return (
        f"{prefix}Extract all content from page {page_num} of the Income Tax Act, 2025.{ctx}\n"
        f"Set \"page\" to {page_num}. Be thorough — legal completeness is critical."
    )


# ── API call with retry ────────────────────────────────────────────────────────

def call_api(client, provider: str, page_num: int, image_b64: str, prev_context: str) -> dict:
    cfg      = PROVIDERS[provider]
    no_think = (provider == "ollama")  # Qwen3-VL on Ollama defaults to thinking mode

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=cfg["model"],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=cfg["max_tokens"],
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}",
                                    "detail": "high",
                                },
                            },
                            {
                                "type": "text",
                                "text": build_user_message(page_num, prev_context, no_think=no_think),
                            },
                        ],
                    },
                ],
            )
            raw = (response.choices[0].message.content or "").strip()

            # Strip accidental markdown fences
            if raw.startswith("```"):
                raw = raw.split("```", 2)[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.rsplit("```", 1)[0].strip()

            return json.loads(raw)

        except json.JSONDecodeError as exc:
            raw_preview = locals().get("raw", "")[:200]
            print(f"\n  [p{page_num}] JSON error attempt {attempt+1}: {exc}")
            print(f"  Preview: {raw_preview}")
        except Exception as exc:
            print(f"\n  [p{page_num}] API error attempt {attempt+1}: {exc}")

        if attempt + 1 < MAX_RETRIES:
            d = RETRY_DELAYS[attempt]
            print(f"  Retrying in {d}s...")
            time.sleep(d)

    raise RuntimeError(f"Page {page_num}: failed after {MAX_RETRIES} attempts")


# ── Cache helpers ──────────────────────────────────────────────────────────────

def cache_path(page_num: int) -> Path:
    return CACHE_DIR / f"page_{page_num:04d}.json"

def load_cached(page_num: int) -> Optional[dict]:
    p = cache_path(page_num)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def save_cached(page_num: int, data: dict) -> None:
    cache_path(page_num).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def tail_context(page_data: dict) -> str:
    """Brief context string about the last partial section on this page."""
    for block in reversed(page_data.get("content_blocks", [])):
        if block.get("type") == "section" and block.get("continues_to_next"):
            subs = block.get("subsections", [])
            return json.dumps({
                "section_number": block.get("number"),
                "section_title" : block.get("title"),
                "last_sub_number": subs[-1]["number"] if subs else None,
                "last_sub_tail"  : (subs[-1].get("text", "")[-150:] if subs else ""),
            }, ensure_ascii=False)
    return ""


# ── Phase 1: Extraction ────────────────────────────────────────────────────────

def run_extraction(page_range: range, provider: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    todo = [p for p in page_range if load_cached(p) is None]
    cached_count = len(page_range) - len(todo)
    model = PROVIDERS[provider]["model"]
    print(f"Provider : {provider}  ({model})")
    print(f"Pages    : {len(page_range)}  |  cached: {cached_count}  |  to extract: {len(todo)}")

    if not todo:
        print("All pages cached. Use --merge-only to build final JSON.")
        return

    client = make_client(provider)
    doc    = fitz.open(str(PDF_PATH))

    # Seed prev_context from the page just before this range
    prev_ctx = ""
    if page_range.start > 1:
        c = load_cached(page_range.start - 1)
        if c:
            prev_ctx = tail_context(c)

    try:
        from tqdm import tqdm
        pbar = tqdm(total=len(page_range), unit="pg", desc="Extracting")
    except ImportError:
        pbar = None

    schedule_hit = False
    for page_num in page_range:
        if schedule_hit:
            break

        # --- Already cached ---
        cached = load_cached(page_num)
        if cached is not None:
            prev_ctx = tail_context(cached)
            if pbar:
                pbar.update(1)
                pbar.set_postfix(page=page_num, status="cached")
            else:
                print(f"  p{page_num:4d} [cached]")
            if cached.get("schedule_start"):
                schedule_hit = True
            continue

        # --- Render + call ---
        img_b64 = render_page_jpeg_b64(doc, page_num - 1)
        t0      = time.time()
        result  = call_api(client, provider, page_num, img_b64, prev_ctx)
        elapsed = time.time() - t0

        save_cached(page_num, result)
        prev_ctx = tail_context(result)

        blocks = len(result.get("content_blocks", []))
        note   = f"{blocks}blk {elapsed:.0f}s"
        if result.get("schedule_start"):
            schedule_hit = True
            note += " [SCHEDULE→stop]"

        if pbar:
            pbar.update(1)
            pbar.set_postfix(page=page_num, status=note)
        else:
            print(f"  p{page_num:4d}  {note}")

    if pbar:
        pbar.close()
    doc.close()

    if schedule_hit:
        print("Schedule section reached — extraction complete.")


# ── Phase 2: Merge ─────────────────────────────────────────────────────────────

def _build_clause(c: dict) -> Clause:
    clause = Clause(identifier=str(c.get("identifier", "")), text=c.get("text", ""))
    for sc in c.get("sub_clauses", []):
        clause.sub_clauses.append(_build_clause(sc))
    return clause

def _build_subsection(s: dict) -> Subsection:
    sub = Subsection(
        number      = str(s.get("number", "")),
        text        = s.get("text", ""),
        provisos    = s.get("provisos", []),
        explanations= s.get("explanations", []),
    )
    for c in s.get("clauses", []):
        sub.clauses.append(_build_clause(c))
    return sub

def run_merge() -> ParsedAct:
    cache_files = sorted(CACHE_DIR.glob("page_*.json"))
    if not cache_files:
        print("ERROR: No cached pages found. Run extraction first.")
        sys.exit(1)

    print(f"Merging {len(cache_files)} cached pages...")
    total_pages   = int(cache_files[-1].stem.split("_")[1])
    parsed        = ParsedAct(act_year="2025", total_pages=total_pages)
    current_ch    : Optional[Chapter] = None
    open_sections : dict[str, Section] = {}   # number → Section (for cross-page merge)

    for cf in cache_files:
        page_num = int(cf.stem.split("_")[1])
        try:
            data = json.loads(cf.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  WARNING: cannot load {cf.name}: {exc}")
            continue

        if data.get("schedule_start"):
            print(f"  Schedule boundary at page {page_num} — stopping merge.")
            break

        # Chapter header
        ch_hdr = data.get("chapter_header")
        if ch_hdr and ch_hdr.get("number"):
            ch = Chapter(
                number    = ch_hdr["number"].strip(),
                title     = ch_hdr.get("title", "").strip(),
                act       = "2025",
                page_start= page_num,
            )
            parsed.chapters.append(ch)
            current_ch = ch

        # Content blocks
        for block in data.get("content_blocks", []):
            if block.get("type") != "section":
                continue

            sec_num  = str(block.get("number", "")).strip()
            if not sec_num:
                continue

            is_cont  = block.get("continues_from_prev", False)
            goes_on  = block.get("continues_to_next", False)

            # Merge continuation into existing section
            if is_cont and sec_num in open_sections:
                existing = open_sections[sec_num]
                raw_app  = block.get("raw_text", "")
                if raw_app:
                    existing.full_text = (existing.full_text + "\n" + raw_app).strip()
                for sd in block.get("subsections", []):
                    existing.subsections.append(_build_subsection(sd))
                existing.page_end = page_num
                if not goes_on:
                    open_sections.pop(sec_num, None)
                continue

            # New section
            section = Section(
                number       = sec_num,
                title        = block.get("title", "").strip(),
                act          = "2025",
                chapter_number = current_ch.number if current_ch else "",
                chapter_title  = current_ch.title  if current_ch else "",
                full_text    = block.get("raw_text", "").strip(),
                page_start   = page_num,
                page_end     = page_num,
            )
            for sd in block.get("subsections", []):
                section.subsections.append(_build_subsection(sd))

            parsed.sections.append(section)
            if current_ch is not None:
                current_ch.sections.append(section)

            if goes_on:
                open_sections[sec_num] = section
            else:
                open_sections.pop(sec_num, None)

    print(
        f"Merged → {len(parsed.chapters)} chapters, "
        f"{len(parsed.sections)} sections, "
        f"{sum(len(s.subsections) for s in parsed.sections)} subsections, "
        f"{sum(len(sub.provisos) for s in parsed.sections for sub in s.subsections)} provisos"
    )
    return parsed


# ── Cost estimate (OpenRouter only) ───────────────────────────────────────────

def print_cost_estimate(total_pages: int) -> None:
    inp  = total_pages * (EST_IMAGE_TOKENS + EST_PROMPT_TOKENS)
    out  = total_pages * EST_OUTPUT_TOKENS
    ci   = inp / 1_000_000 * COST_INPUT_PER_M
    co   = out / 1_000_000 * COST_OUTPUT_PER_M
    print(f"\nCost estimate ({total_pages} pages, OpenRouter):")
    print(f"  Input  ~{inp:,} tokens  →  ${ci:.2f}")
    print(f"  Output ~{out:,} tokens  →  ${co:.2f}")
    print(f"  Total  ~${ci+co:.2f}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_page_range(arg: str, total: int) -> range:
    arg = arg.strip()
    if not arg:
        return range(1, total + 1)
    if "-" in arg:
        a, b = arg.split("-", 1)
        return range(int(a), int(b) + 1)
    p = int(arg)
    return range(p, p + 1)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="VL extraction of Income Tax Act 2025 (Ollama local or OpenRouter cloud)"
    )
    ap.add_argument("--provider", choices=["ollama", "openrouter"], default="ollama",
                    help="Which provider to use (default: ollama)")
    ap.add_argument("--pages", default="",
                    help="Page range e.g. '1-50' or '42'. Default: all pages.")
    ap.add_argument("--merge-only", action="store_true",
                    help="Skip extraction; only merge cached pages into final JSON.")
    ap.add_argument("--cost-estimate", action="store_true",
                    help="Print OpenRouter cost estimate and exit.")
    args = ap.parse_args()

    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found: {PDF_PATH}")
        sys.exit(1)

    with fitz.open(str(PDF_PATH)) as _d:
        total_pages = len(_d)

    print(f"PDF : {PDF_PATH.name}  ({total_pages} pages)")

    if args.cost_estimate:
        print_cost_estimate(total_pages)
        return

    if not args.merge_only:
        page_range = parse_page_range(args.pages, total_pages)
        print(f"Range: pages {page_range.start} – {page_range.stop - 1}")
        if args.provider == "openrouter":
            print_cost_estimate(len(page_range))
        run_extraction(page_range, args.provider)

    # Merge
    parsed = run_merge()

    # Classify
    print("Classifying income heads...")
    classify_all_sections(parsed)
    head_counts: dict[str, int] = {}
    for sec in parsed.sections:
        h = sec.income_head or "Unknown"
        head_counts[h] = head_counts.get(h, 0) + 1
    for head, cnt in sorted(head_counts.items(), key=lambda x: -x[1]):
        print(f"  {head:<40} {cnt:>4}")

    # Save
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    size_mb = OUTPUT_PATH.stat().st_size / 1024 / 1024
    print(f"\nSaved → {OUTPUT_PATH}  ({size_mb:.1f} MB)")
    print(
        f"Done: {len(parsed.chapters)} chapters, "
        f"{len(parsed.sections)} sections, "
        f"{sum(len(s.subsections) for s in parsed.sections)} subsections, "
        f"{sum(len(sub.provisos) for s in parsed.sections for sub in s.subsections)} provisos"
    )


if __name__ == "__main__":
    main()
