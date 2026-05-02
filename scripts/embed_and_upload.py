#!/usr/bin/env python3
"""
Embed chunks_*.json files using Qwen3-Embedding-0.6B and upload to Qdrant Cloud.

Reads:  backend/data/chunks_1961.json  (6082 chunks)
        backend/data/chunks_2025.json  (2899 chunks)

Embeds: Qwen/Qwen3-Embedding-0.6B  (1024-dim, via sentence-transformers)

Uploads: Qdrant Cloud  (recreates collections — old 4096-dim vectors are deleted)

Caches:  backend/data/vectors_hf_1961.npy  (so re-runs don't re-embed)
         backend/data/vectors_hf_2025.npy

Usage:
    python scripts/embed_and_upload.py              # both acts
    python scripts/embed_and_upload.py --act 2025   # one act only
    python scripts/embed_and_upload.py --no-cache   # force re-embed
"""

from __future__ import annotations

import sys
import json
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DATA_DIR, QDRANT_URL, QDRANT_API_KEY, HF_TOKEN, HF_EMBED_MODEL, validate, summary
from backend.indexing.embedder import embed_texts, check_embedder_available, EMBED_DIM
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue, PayloadSchemaType, TextIndexParams, TokenizerType,
)


# ── Qdrant helpers ────────────────────────────────────────────────────────────

def _build_client() -> QdrantClient:
    if not QDRANT_URL or not QDRANT_API_KEY:
        raise RuntimeError("QDRANT_URL and QDRANT_API_KEY must be set in .env")
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=60)


def _ensure_collection(client: QdrantClient, name: str, recreate: bool = True) -> None:
    exists = any(c.name == name for c in client.get_collections().collections)
    if exists and recreate:
        print(f"  Deleting existing collection '{name}'...")
        client.delete_collection(name)
        exists = False

    if not exists:
        print(f"  Creating collection '{name}' (dim={EMBED_DIM}, cosine)...")
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        # Keyword payload indices (server-side filters)
        for field in ("section", "income_head", "act_year", "chapter", "chunk_type", "part"):
            client.create_payload_index(name, field_name=field, field_schema=PayloadSchemaType.KEYWORD)
        # Full-text indices
        for field in ("text", "section_title"):
            client.create_payload_index(name, field_name=field, field_schema=TextIndexParams(
                type="text", tokenizer=TokenizerType.WORD, lowercase=True,
            ))
        print(f"  Collection '{name}' created with payload indices.")


def _upload_batch(
    client: QdrantClient,
    collection_name: str,
    chunks: list[dict],
    vectors: list[list[float]],
    batch_size: int = 50,
) -> None:
    total = len(chunks)
    for start in range(0, total, batch_size):
        batch_chunks = chunks[start:start + batch_size]
        batch_vectors = vectors[start:start + batch_size]

        points = [
            PointStruct(
                id=abs(hash(c["chunk_id"])) % (2 ** 63),
                vector=v,
                payload={
                    # Store all fields so retriever can use them
                    "chunk_id":      c["chunk_id"],
                    "act_year":      c["act_year"],
                    "section":       c["section"],
                    "section_title": c["section_title"],
                    "chapter":       c["chapter"],
                    "chapter_title": c["chapter_title"],
                    "part":          c.get("part", ""),
                    "income_head":   c["income_head"],
                    "chunk_index":   c["chunk_index"],
                    "chunk_type":    c["chunk_type"],
                    "text":          c["text"],
                    "page_start":    c.get("page_start", 0),
                    "page_end":      c.get("page_end", 0),
                },
            )
            for c, v in zip(batch_chunks, batch_vectors)
        ]

        for attempt in range(3):
            try:
                client.upsert(collection_name=collection_name, points=points)
                break
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** attempt
                    print(f"\n  Retry {attempt+1} after {wait}s ({e})", end="")
                    time.sleep(wait)
                else:
                    raise

        done = min(start + batch_size, total)
        pct = done / total * 100
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"  [{bar}] {done:,}/{total:,} ({pct:.0f}%)", end="\r")

    print()  # newline after progress bar


# ── Main indexing function ────────────────────────────────────────────────────

def index_act(
    act_year: str,
    client: QdrantClient,
    use_cache: bool = True,
) -> None:
    print(f"\n{'='*65}")
    print(f"  Indexing {act_year} Act  →  Qdrant Cloud")
    print(f"  Embed model : {HF_EMBED_MODEL}  ({EMBED_DIM}-dim)")
    print(f"{'='*65}")

    # ── Load chunks ────────────────────────────────────────────────────────────
    chunks_path = DATA_DIR / f"chunks_{act_year}.json"
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Chunk file not found: {chunks_path}\n"
            f"Run the chunking pipeline first."
        )

    print(f"\n[1/4] Loading chunks from {chunks_path.name}...")
    with open(chunks_path, encoding="utf-8") as f:
        chunks: list[dict] = json.load(f)
    print(f"      Loaded {len(chunks):,} chunks")

    texts = [c["text"] for c in chunks]

    # ── Embed (with cache) ─────────────────────────────────────────────────────
    cache_path = DATA_DIR / f"vectors_hf_{act_year}.npy"
    if use_cache and cache_path.exists():
        print(f"\n[2/4] Loading cached vectors from {cache_path.name}...")
        import numpy as np
        vecs_array = np.load(str(cache_path))
        if vecs_array.shape != (len(chunks), EMBED_DIM):
            print(f"      WARNING: Cache shape {vecs_array.shape} doesn't match "
                  f"expected ({len(chunks)}, {EMBED_DIM}) — re-embedding...")
            vecs_array = None
        else:
            vectors = vecs_array.tolist()
            print(f"      Loaded {len(vectors):,} vectors ({EMBED_DIM}-dim) from cache")
    else:
        vecs_array = None

    if vecs_array is None:
        print(f"\n[2/4] Embedding {len(texts):,} texts with {HF_EMBED_MODEL}...")
        print(f"      This may take several minutes on CPU...")
        t0 = time.time()
        vectors = embed_texts(texts, verbose=True)
        elapsed = time.time() - t0
        print(f"      Done: {len(vectors):,} vectors in {elapsed:.1f}s "
              f"({elapsed/len(vectors)*1000:.0f}ms/chunk)")

        # Save cache
        import numpy as np
        print(f"      Saving vector cache to {cache_path.name}...")
        np.save(str(cache_path), np.array(vectors, dtype="float32"))
        print(f"      Cache saved ({cache_path.stat().st_size / 1024**2:.1f} MB)")

    # ── Prepare Qdrant collection ──────────────────────────────────────────────
    collection_name = f"tax_{act_year}"
    print(f"\n[3/4] Preparing Qdrant collection '{collection_name}'...")
    _ensure_collection(client, collection_name, recreate=True)

    # ── Upload ─────────────────────────────────────────────────────────────────
    print(f"\n[4/4] Uploading {len(chunks):,} points to '{collection_name}'...")
    t0 = time.time()
    _upload_batch(client, collection_name, chunks, vectors)
    elapsed = time.time() - t0

    # Verify
    info = client.get_collection(collection_name)
    count = info.points_count or 0
    print(f"\n  ✓ Upload complete!")
    print(f"  Collection '{collection_name}': {count:,} points")
    print(f"  Time: {elapsed:.1f}s")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Embed chunks_*.json with Qwen3-Embedding-0.6B and upload to Qdrant"
    )
    parser.add_argument("--act", choices=["1961", "2025"], help="Index only one act")
    parser.add_argument("--no-cache", action="store_true", help="Force re-embedding (ignore .npy cache)")
    args = parser.parse_args()

    print("\n" + "="*65)
    print("  ActInsight — Qdrant Indexing with Qwen3-Embedding-0.6B")
    print("="*65)
    print("\nConfiguration:")
    print(summary())
    print()

    # Validate Qdrant config
    errors = validate()
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)

    # Set HF token if available
    import os
    if HF_TOKEN:
        os.environ.setdefault("HF_TOKEN", HF_TOKEN)
        print(f"HF_TOKEN: set ✓")
    else:
        print(f"HF_TOKEN: not set (downloads may be slower)")

    # Check embedding model loads
    print("\nChecking embedding model (may trigger download on first run)...")
    if not check_embedder_available():
        print(f"ERROR: Embedding model '{HF_EMBED_MODEL}' failed to load.")
        print("  Install: pip install sentence-transformers torch")
        sys.exit(1)
    print(f"  OK — {HF_EMBED_MODEL} loaded ({EMBED_DIM}-dim)\n")

    client = _build_client()
    acts = [args.act] if args.act else ["2025", "1961"]

    t_start = time.time()
    for act_year in acts:
        index_act(act_year, client, use_cache=not args.no_cache)

    total = time.time() - t_start
    print("\n" + "="*65)
    print("  Indexing Summary")
    print("="*65)
    for act_year in acts:
        collection_name = f"tax_{act_year}"
        try:
            info = client.get_collection(collection_name)
            count = info.points_count or 0
            print(f"  tax_{act_year}: {count:,} points  ✓")
        except Exception as e:
            print(f"  tax_{act_year}: ERROR ({e})")

    mins, secs = divmod(int(total), 60)
    print(f"\n  Total time: {mins}m {secs}s")
    print("="*65)
    print("\n  Done! Start the app with: python -m backend.main")
    print()

    client.close()


if __name__ == "__main__":
    main()
