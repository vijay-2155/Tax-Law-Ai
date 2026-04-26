#!/usr/bin/env python3
"""
LLM-powered enrichment pipeline: parsed JSON → enriched RAG-ready JSON + Qdrant re-index.

Speed design:
  • llm_batch_size (default 5): each LLM call processes 5 sections at once.
  • concurrency (default 8): 8 batches run in parallel.
  • Effective throughput: ~40 sections in-flight simultaneously.
  • Kimi K2 (256K context) can comfortably handle 5 sections per call.

Default: Ollama Cloud signed-in mode (run `ollama signin` once, no API key needed).

Usage
-----
# Default (Ollama Cloud, kimi-k2, batch=5, concurrency=8):
    python scripts/enrich_sections.py --act 2025

# Custom batch size (bigger = fewer calls but more tokens per call):
    python scripts/enrich_sections.py --act 2025 --llm-batch-size 8

# Different cloud model:
    python scripts/enrich_sections.py --act 2025 --model deepseek-v3.1:671b-cloud

# With explicit API key:
    python scripts/enrich_sections.py --act 2025 --api-key <key>

# Local Ollama (single-threaded to avoid overloading):
    python scripts/enrich_sections.py --act 2025 \\
        --provider ollama --model qwen2.5:7b --concurrency 1 --llm-batch-size 1

# Enrich + immediately re-index into Qdrant:
    python scripts/enrich_sections.py --act 1961 --index

# Resume an interrupted run:
    python scripts/enrich_sections.py --act 1961 --resume

# Smoke test (10 sections):
    python scripts/enrich_sections.py --act 2025 --limit 10
"""

import sys
import json
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DATA_DIR, QDRANT_URL, QDRANT_API_KEY, OLLAMA_BASE_URL
from backend.rag.llm_provider import LLMConfig
from backend.enrichment.batch_enricher import enrich_act
from backend.enrichment.rag_schema import RagChunk


# ── Indexing helpers ───────────────────────────────────────────────────────────

def _rebuild_index(chunks: list[RagChunk], act_year: str, verbose: bool = True) -> None:
    """Embed enriched chunks and upload to Qdrant (replaces existing collection)."""
    from backend.indexing.embedder import embed_texts, check_ollama_available, EMBED_MODEL
    from backend.indexing.qdrant_store import QdrantStore

    print(f"\n{'='*60}")
    print(f"Re-indexing {act_year} Act → Qdrant Cloud ({len(chunks):,} enriched chunks)")
    print(f"{'='*60}")

    if not check_ollama_available():
        print(f"ERROR: Ollama not running or '{EMBED_MODEL}' not pulled.")
        print("  Start Ollama: ollama serve")
        print(f"  Pull model  : ollama pull {EMBED_MODEL}")
        sys.exit(1)

    # Use clean_text for embedding (richer than raw content)
    texts = [c.clean_text or c.content for c in chunks]

    # Cache embeddings to disk
    import numpy as np
    cache_path = DATA_DIR / f"vectors_{act_year}.npy"
    if cache_path.exists() and len(chunks) == len(np.load(str(cache_path))):
        print(f"Loading cached embeddings from {cache_path.name}...")
        vectors = np.load(str(cache_path)).tolist()
    else:
        print(f"Embedding {len(chunks):,} enriched chunks with {EMBED_MODEL}...")
        vectors = embed_texts(texts, verbose=verbose)
        np.save(str(cache_path), np.array(vectors, dtype="float32"))
        print(f"Cached to {cache_path.name}")

    store = QdrantStore()
    # upsert_rag_chunks always recreates the collection
    store.upsert_rag_chunks(chunks, vectors, act_year, verbose=verbose)
    count = store.collection_point_count(act_year)
    print(f"  sections_{act_year}: {count:,} enriched points in Qdrant")
    store.close()


# ── Stats helpers ──────────────────────────────────────────────────────────────

def _print_stats(chunks: list[RagChunk], act_year: str) -> None:
    print(f"\n{'='*60}")
    print(f"ENRICHMENT STATS — {act_year} Act")
    print(f"{'='*60}")
    print(f"Total chunks    : {len(chunks):,}")

    has_summary    = sum(1 for c in chunks if c.summary)
    has_clean      = sum(1 for c in chunks if c.clean_text)
    has_conditions = sum(1 for c in chunks if c.conditions)
    has_exceptions = sum(1 for c in chunks if c.exceptions)
    has_keywords   = sum(1 for c in chunks if c.keywords)
    has_refs       = sum(1 for c in chunks if c.references)

    total = len(chunks)
    def pct(n): return f"{n/total*100:.0f}%" if total else "—"

    print(f"With summary    : {has_summary:>6,}  ({pct(has_summary)})")
    print(f"With clean_text : {has_clean:>6,}  ({pct(has_clean)})")
    print(f"With conditions : {has_conditions:>6,}  ({pct(has_conditions)})")
    print(f"With exceptions : {has_exceptions:>6,}  ({pct(has_exceptions)})")
    print(f"With keywords   : {has_keywords:>6,}  ({pct(has_keywords)})")
    print(f"With references : {has_refs:>6,}  ({pct(has_refs)})")

    # Chunk type distribution
    from collections import Counter
    type_counts = Counter(c.chunk_type for c in chunks)
    print("\nChunk type distribution:")
    for t, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:<20} {cnt:>5}")

    # Sample
    print("\nSample (first enriched chunk with summary):")
    for c in chunks:
        if c.summary:
            print(f"  Section {c.section}: {c.section_title[:50]}")
            print(f"  Summary   : {c.summary[:200]}")
            print(f"  Conditions: {c.conditions[:3]}")
            print(f"  Keywords  : {c.keywords[:5]}")
            break


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enrich Income Tax Act sections with LLM-generated summaries and metadata"
    )
    parser.add_argument(
        "--act", choices=["1961", "2025"], required=True,
        help="Which act to enrich",
    )
    parser.add_argument(
        "--provider", default="ollama_cloud",
        choices=["ollama", "ollama_cloud", "openai", "anthropic", "gemini", "groq", "openrouter"],
        help="LLM provider (default: ollama_cloud in signed-in mode)",
    )
    parser.add_argument(
        "--model", default="",
        help="Model name override (default: provider default)",
    )
    parser.add_argument(
        "--api-key", default="",
        help="API key for cloud providers",
    )
    parser.add_argument(
        "--base-url", default="",
        help="Custom base URL override",
    )
    parser.add_argument(
        "--concurrency", type=int, default=3,
        help=(
            "Parallel LLM batch calls (default: 3). "
            "Increase carefully — too high causes 429 rate-limit cascade. "
            "Use 1 for local Ollama."
        ),
    )
    parser.add_argument(
        "--llm-batch-size", type=int, default=5, dest="llm_batch_size",
        help="Sections per LLM call (default: 5). Higher=fewer calls but more tokens per call.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from checkpoint (skip already-enriched sections)",
    )
    parser.add_argument(
        "--index", action="store_true",
        help="After enrichment, re-embed and re-index into Qdrant (replaces existing collection)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Only enrich first N sections (smoke test)",
    )
    args = parser.parse_args()

    # ── Build LLM config ──────────────────────────────────────────────────────
    provider = args.provider
    model = args.model

    # Sensible defaults per provider
    if not model:
        defaults = {
            "ollama":       "gemma4:latest",
            "ollama_cloud": "deepseek-v3.1:671b-cloud",
            "openai":       "gpt-4o-mini",
            "anthropic":    "claude-haiku-4-5-20251001",
            "gemini":       "gemini-2.0-flash",
            "groq":         "llama-3.3-70b-versatile",
            "openrouter":   "meta-llama/llama-3.3-70b-instruct",
        }
        model = defaults.get(provider, "deepseek-v3.1:671b-cloud")

    provider_api_keys = {}
    if args.api_key:
        provider_api_keys[provider] = args.api_key

    config = LLMConfig(
        provider=provider,
        model=model,
        api_key=args.api_key,
        base_url=args.base_url,
        provider_api_keys=provider_api_keys,
        temperature=0.1,
        max_tokens=4096,
    )

    print("=" * 60)
    print("Income Tax Act — LLM Enrichment Pipeline")
    print("=" * 60)
    print(f"  Act      : {args.act}")
    print(f"  Provider : {provider}")
    print(f"  Model    : {model}")
    print(f"  Concurrent LLM calls : {args.concurrency}")
    print(f"  Resume   : {args.resume}")
    print(f"  Re-index : {args.index}")
    effective = args.concurrency * args.llm_batch_size
    print(f"  Effective in-flight sections : ~{effective} "
          f"({args.concurrency} concurrent × {args.llm_batch_size} per batch)")
    if args.limit:
        print(f"  Limit    : first {args.limit} sections only (smoke test)")
    print()

    # ── Validate Qdrant config if indexing ────────────────────────────────────
    if args.index:
        if not QDRANT_URL or not QDRANT_API_KEY:
            print("ERROR: --index requires QDRANT_URL and QDRANT_API_KEY in .env")
            sys.exit(1)

    t0 = time.time()

    # ── If --limit: patch the parsed JSON temporarily ────────────────────────
    if args.limit:
        parsed_path = DATA_DIR / f"parsed_{args.act}.json"
        with open(parsed_path, encoding="utf-8") as f:
            raw = json.load(f)
        raw["sections"] = raw["sections"][: args.limit]
        # Write a temp file
        tmp_path = DATA_DIR / f"parsed_{args.act}_tmp_limit.json"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
        # Swap
        import shutil
        shutil.copy(str(parsed_path), str(DATA_DIR / f"parsed_{args.act}_backup.json"))
        shutil.copy(str(tmp_path), str(parsed_path))
        tmp_path.unlink()
        print(f"  [smoke test] Limited to first {args.limit} sections\n")

    try:
        chunks = enrich_act(
            act_year       = args.act,
            config         = config,
            data_dir       = DATA_DIR,
            resume         = args.resume,
            concurrency    = args.concurrency,
            llm_batch_size = args.llm_batch_size,
            verbose        = True,
        )
    finally:
        # Restore original parsed file if we swapped it
        if args.limit:
            backup = DATA_DIR / f"parsed_{args.act}_backup.json"
            if backup.exists():
                import shutil
                shutil.copy(str(backup), str(DATA_DIR / f"parsed_{args.act}.json"))
                backup.unlink()

    _print_stats(chunks, args.act)

    total_elapsed = time.time() - t0
    print(f"\nTotal time: {total_elapsed:.1f}s")

    if args.index:
        _rebuild_index(chunks, args.act)

    print("\nDone!")


if __name__ == "__main__":
    main()
