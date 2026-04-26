#!/usr/bin/env python3
"""
One-shot PDF parsing script.
Parses both Income Tax Act PDFs and saves structured JSON.

Usage:
    python scripts/parse_pdfs.py
    python scripts/parse_pdfs.py --act 2025      # Only parse 2025 Act
    python scripts/parse_pdfs.py --validate      # Extra validation output
"""

import sys
import json
import time
import random
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.parsing.section_parser import parse_act
from backend.parsing.head_classifier import classify_all_sections

ROOT = Path(__file__).parent.parent
PDF_DIR = ROOT / "pdfs"
DATA_DIR = ROOT / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PDFS = {
    "2025": PDF_DIR / "income_tax_act_2025.pdf",
    "1961": PDF_DIR / "income_tax_act_1961.pdf",
}


def validate_parsed(parsed, act_year: str) -> None:
    print(f"\n{'='*60}")
    print(f"VALIDATION REPORT — {act_year} Act")
    print(f"{'='*60}")
    print(f"Total pages  : {parsed.total_pages}")
    print(f"Chapters     : {len(parsed.chapters)}")
    print(f"Sections     : {len(parsed.sections)}")

    if not parsed.sections:
        print("ERROR: No sections found! Check PDF parsing.")
        return

    # Section number stats
    nums = [s.number for s in parsed.sections]
    print(f"Section range: {nums[0]} → {nums[-1]}")

    # Head distribution
    from collections import Counter
    head_counts = Counter(s.income_head for s in parsed.sections)
    print("\nIncome head distribution:")
    for head, count in sorted(head_counts.items(), key=lambda x: -x[1]):
        print(f"  {head:<35} {count:>4} sections")

    # Spot-check 5 random sections
    print("\nRandom spot-check (5 sections):")
    samples = random.sample(parsed.sections, min(5, len(parsed.sections)))
    for s in samples:
        preview = s.full_text[:100].replace("\n", " ")
        print(f"  § {s.number:<10} [{s.income_head}] {s.title[:40]}")
        print(f"             Pages {s.page_start}–{s.page_end} | {len(s.subsections)} subsections")
        print(f"             Preview: {preview}...")

    # Sections with no subsections
    no_subs = [s for s in parsed.sections if not s.subsections]
    if no_subs:
        print(f"\nSections with no parsed subsections: {len(no_subs)}")
        for s in no_subs[:5]:
            print(f"  § {s.number} — {s.title[:50]}")

    # Empty sections
    empty = [s for s in parsed.sections if len(s.full_text.strip()) < 20]
    if empty:
        print(f"\nWARNING: {len(empty)} nearly-empty sections:")
        for s in empty[:5]:
            print(f"  § {s.number} — {s.title}")

    print()


def save_parsed(parsed, act_year: str) -> Path:
    out_path = DATA_DIR / f"parsed_{act_year}.json"
    data = parsed.model_dump()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Saved to {out_path} ({size_mb:.1f} MB)")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Parse Income Tax Act PDFs")
    parser.add_argument("--act", choices=["1961", "2025"], help="Parse only this act")
    parser.add_argument("--validate", action="store_true", help="Show detailed validation")
    args = parser.parse_args()

    acts_to_parse = ["2025", "1961"] if not args.act else [args.act]

    for act_year in acts_to_parse:
        pdf_path = PDFS[act_year]
        if not pdf_path.exists():
            print(f"ERROR: PDF not found: {pdf_path}")
            continue

        print(f"\n{'='*60}")
        print(f"Parsing {act_year} Act...")
        print(f"{'='*60}")
        t0 = time.time()

        parsed = parse_act(pdf_path, act_year=act_year, verbose=True)

        print("Classifying sections by income head...")
        classify_all_sections(parsed)

        elapsed = time.time() - t0
        print(f"Parsing took {elapsed:.1f}s")

        save_parsed(parsed, act_year)

        if args.validate or True:  # Always validate
            validate_parsed(parsed, act_year)

    print("\nParsing complete!")


if __name__ == "__main__":
    main()
