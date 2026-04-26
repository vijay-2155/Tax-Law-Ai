#!/usr/bin/env python3
"""
Embed all parsed sections and upload to Qdrant Cloud.

Usage:
    python scripts/build_index.py               # Index both Acts
    python scripts/build_index.py --act 2025    # Index only 2025 Act
    python scripts/build_index.py --recreate    # Wipe collections and rebuild

Prerequisites:
    - Fill QDRANT_URL and QDRANT_API_KEY in .env
    - Run scripts/parse_pdfs.py first to generate parsed_*.json files
    - Ollama must be running with qwen3-embedding pulled
"""

import sys
import json
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DATA_DIR, QDRANT_URL, validate, summary
from backend.parsing.structure import ParsedAct
from backend.indexing.chunker import chunk_parsed_act
from backend.indexing.embedder import embed_texts, check_ollama_available, EMBED_MODEL
from backend.indexing.qdrant_store import QdrantStore


def load_parsed(act_year: str) -> ParsedAct:
    path = DATA_DIR / f"parsed_{act_year}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Parsed data not found: {path}\n"
            f"Run: python scripts/parse_pdfs.py --act {act_year}"
        )
    size_mb = path.stat().st_size / 1024 / 1024
    print(f"Loading {path.name} ({size_mb:.1f} MB)...")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return ParsedAct.model_validate(data)


def index_act(act_year: str, store: QdrantStore, recreate: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"Indexing {act_year} Act → Qdrant Cloud")
    print(f"{'='*60}")

    if not recreate and store.collection_exists(act_year):
        count = store.collection_point_count(act_year)
        print(f"  sections_{act_year}: already has {count:,} points. Use --recreate to rebuild.")
        return

    t0 = time.time()

    parsed = load_parsed(act_year)
    print(f"Loaded: {len(parsed.sections)} sections")

    print("Chunking into atomic clause-level units...")
    chunks = chunk_parsed_act(parsed)
    print(f"Created {len(chunks):,} chunks")

    type_counts: dict[str, int] = {}
    for c in chunks:
        type_counts[c.type] = type_counts.get(c.type, 0) + 1
    for t, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:<15} {cnt:>5}")

    # Cache embeddings to disk so a retry doesn't re-embed
    cache_path = DATA_DIR / f"vectors_{act_year}.npy"
    if cache_path.exists():
        print(f"Loading cached embeddings from {cache_path.name}...")
        import numpy as np
        vectors = np.load(str(cache_path)).tolist()
        print(f"Loaded {len(vectors):,} cached vectors")
    else:
        print(f"\nEmbedding {len(chunks):,} chunks with {EMBED_MODEL}...")
        texts = [c.text for c in chunks]
        vectors = embed_texts(texts, verbose=True)
        print(f"Embedding done: {len(vectors):,} vectors ({len(vectors[0])}-dim)")
        import numpy as np
        np.save(str(cache_path), np.array(vectors, dtype="float32"))
        print(f"Cached to {cache_path.name}")

    print(f"\nUploading to Qdrant Cloud (batch_size=25)...")
    store.upsert_chunks(chunks, vectors, act_year, verbose=True)

    elapsed = time.time() - t0
    per_chunk = elapsed / len(chunks)
    print(f"Done in {elapsed:.1f}s  ({per_chunk:.3f}s/chunk)")


def main():
    parser = argparse.ArgumentParser(description="Build Qdrant Cloud vector index")
    parser.add_argument("--act", choices=["1961", "2025"], help="Index only this act")
    parser.add_argument("--recreate", action="store_true", help="Delete and rebuild collections")
    args = parser.parse_args()

    print("Configuration:")
    print(summary())
    print()

    # Validate config
    errors = validate()
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)

    # Check Ollama
    print("Checking Ollama embedding model...")
    if not check_ollama_available():
        print(f"ERROR: Ollama not running or '{EMBED_MODEL}' not pulled.")
        print("  Start Ollama : ollama serve")
        print(f"  Pull model   : ollama pull {EMBED_MODEL}")
        sys.exit(1)
    print(f"  Ollama OK — {EMBED_MODEL} ready\n")

    acts = [args.act] if args.act else ["2025", "1961"]

    store = QdrantStore()

    for act_year in acts:
        index_act(act_year, store, recreate=args.recreate)

    print("\n" + "="*60)
    print("Indexing complete! Collection stats:")
    for act_year in acts:
        count = store.collection_point_count(act_year)
        print(f"  sections_{act_year}: {count:,} points")

    store.close()


if __name__ == "__main__":
    main()
