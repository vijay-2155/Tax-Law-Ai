#!/usr/bin/env python3
"""
Rule-based enrichment pipeline: parsed_{act}.json → enriched_{act}.json

No LLM. No API key. Runs in seconds.

Fills:
  summary     — extractive (definition pattern or first meaningful sentence)
  conditions  — regex-extracted "subject to", "where", "if" clauses
  exceptions  — regex-extracted "shall not apply/include", "does not include"
  keywords    — improved domain + authorities + monetary thresholds + time limits
  clean_text  — abbreviation expansion + hyphenation repair

Usage
-----
  python scripts/rule_enrich.py --act 2025
  python scripts/rule_enrich.py --act 1961
  python scripts/rule_enrich.py --act 2025 --index   # enrich + push to Qdrant
  python scripts/rule_enrich.py --act 2025 --stats   # show quality stats only
"""

import sys
import json
import time
import argparse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DATA_DIR
from backend.parsing.structure import ParsedAct
from backend.indexing.chunker import (
    _clean,
    _classify_type,
    _extract_keywords,
    _extract_related_sections,
    _make_id,
    _build_path,
)
from backend.enrichment.rag_schema import RagChunk
from backend.enrichment.rule_enricher import enrich_chunk


# ── Build RagChunks from parsed JSON (heuristic base) ─────────────────────────

def _make_rag_chunk(
    act_year: str,
    section_number: str,
    section_title: str,
    chapter: str,
    chapter_title: str,
    income_head: str,
    mapped_to: str | None,
    page_start: int,
    page_end: int,
    subsection: str,
    clause: str,
    clause_path: str,
    content: str,
) -> RagChunk:
    clean = _clean(content)
    refs  = _extract_related_sections(clean)
    kws   = _extract_keywords(clean, section_title)
    ctype = _classify_type(clean)
    return RagChunk(
        act_year      = act_year,
        chunk_id      = _make_id(act_year, section_number, clause_path),
        chapter       = chapter,
        chapter_title = chapter_title,
        section       = section_number,
        section_title = section_title,
        subsection    = subsection,
        clause        = clause,
        content       = clean,
        clean_text    = clean,
        summary       = "",
        conditions    = [],
        exceptions    = [],
        keywords      = kws,
        references    = [f"section {r}" for r in refs],
        income_head   = income_head or "General / Definitions",
        clause_path   = clause_path,
        chunk_type    = ctype,
        mapped_to     = mapped_to,
        page_start    = page_start,
        page_end      = page_end,
    )


def build_chunks_from_parsed(parsed: ParsedAct) -> list[RagChunk]:
    """Convert ParsedAct → flat list of RagChunks (pre-enrichment)."""
    chunks: list[RagChunk] = []
    act_year = parsed.act_year

    for sec in parsed.sections:
        mapped_to: str | None = None
        if sec.mapped_section:
            other = "2025" if act_year == "1961" else "1961"
            mapped_to = f"{other}_S{sec.mapped_section}"

        common = dict(
            act_year      = act_year,
            section_number= sec.number,
            section_title = sec.title,
            chapter       = sec.chapter_number,
            chapter_title = sec.chapter_title,
            income_head   = sec.income_head or "General / Definitions",
            mapped_to     = mapped_to,
            page_start    = sec.page_start,
            page_end      = sec.page_end,
        )

        if not sec.subsections:
            # Whole-section chunk
            body = _clean(sec.full_text) or sec.title
            chunks.append(_make_rag_chunk(
                **common,
                subsection  = "",
                clause      = "",
                clause_path = "",
                content     = f"Section {sec.number}: {sec.title}. {body}",
            ))
            continue

        for sub in sec.subsections:
            sub_path = _build_path(sub.number)
            sub_label = f"({sub.number})"

            # Subsection body (may include clauses inline if not parsed separately)
            if sub.text.strip():
                body = _clean(sub.text)
                chunks.append(_make_rag_chunk(
                    **common,
                    subsection  = sub_label,
                    clause      = "",
                    clause_path = sub_path,
                    content     = f"Section {sec.number}{sub_label}: {body}",
                ))

            # Parsed clauses
            for cl in sub.clauses:
                cl_path = _build_path(sub.number, cl.identifier)
                cl_label = f"({cl.identifier})"
                cl_text  = _clean(cl.text)
                chunks.append(_make_rag_chunk(
                    **common,
                    subsection  = sub_label,
                    clause      = cl_label,
                    clause_path = cl_path,
                    content     = f"Section {sec.number}{sub_label}{cl_label}: {cl_text}",
                ))

                # Sub-clauses
                for sc in cl.sub_clauses:
                    sc_path  = _build_path(sub.number, cl.identifier, sc.identifier)
                    sc_label = f"({sc.identifier})"
                    sc_text  = _clean(sc.text)
                    chunks.append(_make_rag_chunk(
                        **common,
                        subsection  = sub_label,
                        clause      = sc_label,
                        clause_path = sc_path,
                        content     = f"Section {sec.number}{sub_label}{cl_label}{sc_label}: {sc_text}",
                    ))

            # Provisos → exception chunks
            for idx, proviso in enumerate(sub.provisos, 1):
                prov_path = f"{sub_path}_PROV{idx}"
                prov_text = _clean(proviso)
                chunk = _make_rag_chunk(
                    **common,
                    subsection  = sub_label,
                    clause      = "",
                    clause_path = prov_path,
                    content     = f"Section {sec.number}{sub_label} Proviso {idx}: Provided that {prov_text}",
                )
                # Force chunk_type to exception for provisos
                chunks.append(chunk.model_copy(update={"chunk_type": "exception"}))

            # Explanations
            for idx, expl in enumerate(sub.explanations, 1):
                expl_path = f"{sub_path}_EXPL{idx}"
                expl_text = _clean(expl)
                chunk = _make_rag_chunk(
                    **common,
                    subsection  = sub_label,
                    clause      = "",
                    clause_path = expl_path,
                    content     = f"Section {sec.number}{sub_label} Explanation {idx}: {expl_text}",
                )
                chunks.append(chunk.model_copy(update={"chunk_type": "explanation"}))

    return chunks


# ── Stats ──────────────────────────────────────────────────────────────────────

def print_stats(chunks: list[RagChunk], act_year: str) -> None:
    total = len(chunks)
    if not total:
        print("No chunks to report.")
        return

    def pct(n: int) -> str:
        return f"{n / total * 100:.0f}%"

    has_summary    = sum(1 for c in chunks if c.summary)
    has_clean      = sum(1 for c in chunks if c.clean_text and c.clean_text != c.content)
    has_conditions = sum(1 for c in chunks if c.conditions)
    has_exceptions = sum(1 for c in chunks if c.exceptions)
    has_keywords   = sum(1 for c in chunks if len(c.keywords) >= 3)
    has_refs       = sum(1 for c in chunks if c.references)

    print(f"\n{'='*60}")
    print(f"ENRICHMENT STATS — {act_year} Act ({total:,} chunks)")
    print(f"{'='*60}")
    print(f"  With summary        : {has_summary:>5,}  ({pct(has_summary)})")
    print(f"  With clean_text≠raw : {has_clean:>5,}  ({pct(has_clean)})")
    print(f"  With conditions     : {has_conditions:>5,}  ({pct(has_conditions)})")
    print(f"  With exceptions     : {has_exceptions:>5,}  ({pct(has_exceptions)})")
    print(f"  With ≥3 keywords    : {has_keywords:>5,}  ({pct(has_keywords)})")
    print(f"  With references     : {has_refs:>5,}  ({pct(has_refs)})")

    type_counts = Counter(c.chunk_type for c in chunks)
    print(f"\n  Chunk type distribution:")
    for t, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t:<20} {cnt:>5}")

    print(f"\n  Sample enriched chunks:")
    shown = 0
    for c in chunks:
        if c.summary and c.conditions:
            print(f"\n  Section {c.section}{c.subsection}: {c.section_title[:50]}")
            print(f"  chunk_type : {c.chunk_type}")
            print(f"  summary    : {c.summary[:180]}")
            print(f"  conditions : {c.conditions[:2]}")
            print(f"  exceptions : {c.exceptions[:2]}")
            print(f"  keywords   : {c.keywords[:5]}")
            shown += 1
            if shown >= 3:
                break

    if not shown:
        # Fallback: show any chunk with a summary
        for c in chunks:
            if c.summary:
                print(f"\n  Section {c.section}{c.subsection}: {c.section_title[:50]}")
                print(f"  chunk_type : {c.chunk_type}")
                print(f"  summary    : {c.summary[:180]}")
                print(f"  keywords   : {c.keywords[:5]}")
                break


# ── Qdrant re-index ────────────────────────────────────────────────────────────

def rebuild_index(chunks: list[RagChunk], act_year: str) -> None:
    from backend.config import QDRANT_URL, QDRANT_API_KEY
    from backend.indexing.embedder import embed_texts, check_ollama_available, EMBED_MODEL
    from backend.indexing.qdrant_store import QdrantStore
    import numpy as np

    print(f"\n{'='*60}")
    print(f"Re-indexing {act_year} Act → Qdrant ({len(chunks):,} chunks)")
    print(f"{'='*60}")

    if not check_ollama_available():
        print(f"ERROR: Ollama not running or '{EMBED_MODEL}' not pulled.")
        sys.exit(1)

    texts = [c.clean_text or c.content for c in chunks]

    cache_path = DATA_DIR / f"vectors_{act_year}.npy"
    if cache_path.exists() and len(chunks) == len(np.load(str(cache_path))):
        print(f"Loading cached embeddings from {cache_path.name}...")
        vectors = np.load(str(cache_path)).tolist()
    else:
        print(f"Embedding {len(chunks):,} chunks with {EMBED_MODEL}...")
        vectors = embed_texts(texts, verbose=True)
        np.save(str(cache_path), np.array(vectors, dtype="float32"))
        print(f"Cached → {cache_path.name}")

    store = QdrantStore()
    store.upsert_rag_chunks(chunks, vectors, act_year, verbose=True)
    count = store.collection_point_count(act_year)
    print(f"  sections_{act_year}: {count:,} points in Qdrant")
    store.close()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rule-based enrichment — no LLM, no cost, runs in seconds."
    )
    parser.add_argument(
        "--act", choices=["1961", "2025"], required=True,
        help="Which act to enrich",
    )
    parser.add_argument(
        "--index", action="store_true",
        help="After enrichment, re-embed and push to Qdrant",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print quality stats and exit (does not save)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Only process first N sections (smoke test)",
    )
    args = parser.parse_args()

    parsed_path = DATA_DIR / f"parsed_{args.act}.json"
    output_jsonl = DATA_DIR / f"enriched_{args.act}_progress.jsonl"
    output_json  = DATA_DIR / f"enriched_{args.act}.json"

    if not parsed_path.exists():
        print(f"ERROR: {parsed_path} not found. Run: python scripts/parse_pdfs.py --act {args.act}")
        sys.exit(1)

    print("=" * 60)
    print("Income Tax Act — Rule-Based Enrichment Pipeline")
    print("=" * 60)
    print(f"  Act     : {args.act}")
    print(f"  Source  : {parsed_path.name}  ({parsed_path.stat().st_size/1024/1024:.1f} MB)")
    print(f"  Mode    : pure rules (no LLM)")
    if args.limit:
        print(f"  Limit   : first {args.limit} sections")
    print()

    # Load
    t0 = time.time()
    print("Loading parsed data...", flush=True)
    with open(parsed_path, encoding="utf-8") as f:
        data = json.load(f)
    parsed = ParsedAct.model_validate(data)

    sections = parsed.sections
    if args.limit:
        sections = sections[: args.limit]
        # Patch parsed object for build_chunks_from_parsed
        parsed = parsed.model_copy(update={"sections": sections})

    print(f"Loaded {len(sections)} sections.", flush=True)

    # Build base chunks
    print("Building chunks from parsed structure...", flush=True)
    chunks = build_chunks_from_parsed(parsed)
    print(f"Built {len(chunks):,} base chunks.", flush=True)

    # Enrich
    print("Applying rule-based enrichment...", flush=True)
    t_enrich = time.time()
    enriched = [enrich_chunk(c) for c in chunks]
    enrich_time = time.time() - t_enrich
    total_time  = time.time() - t0

    print(f"Enriched {len(enriched):,} chunks in {enrich_time:.2f}s  "
          f"({len(enriched)/enrich_time:.0f} chunks/s)", flush=True)

    # Stats
    print_stats(enriched, args.act)

    if args.stats:
        print("\n[--stats mode] Not saving output.")
        return

    # Save JSONL checkpoint
    print(f"\nSaving JSONL → {output_jsonl.name}...", flush=True)
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for chunk in enriched:
            f.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")

    # Save final JSON
    print(f"Saving JSON  → {output_json.name}...", flush=True)
    chunk_dicts = [c.model_dump() for c in enriched]
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(chunk_dicts, f, ensure_ascii=False, indent=2)

    size_mb = output_json.stat().st_size / 1024 / 1024
    print(f"\nDone: {len(enriched):,} chunks → {output_json.name} ({size_mb:.1f} MB)")
    print(f"Total time: {total_time:.1f}s")

    if args.index:
        rebuild_index(enriched, args.act)

    print("\nAll done!")


if __name__ == "__main__":
    main()
