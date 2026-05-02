#!/usr/bin/env python3
"""
load_to_qdrant.py — Fast one-time data loader for TaxIQ.

Reads the pre-computed vectors + chunks from the repo and loads them
into a local (or cloud) Qdrant instance. No PDF parsing or embedding
is needed — vectors_hf_*.npy + chunks_*.json are already in the repo.

Typical runtime: ~60-120 seconds on a local Qdrant container.

Usage:
    python scripts/load_to_qdrant.py              # both acts
    python scripts/load_to_qdrant.py --act 2025   # one act only
    python scripts/load_to_qdrant.py --force       # drop & recreate collections

Called automatically by the app on startup when collections are empty.
"""

from __future__ import annotations

import sys
import json
import time
import argparse
import logging
from pathlib import Path

# Allow running from project root or scripts/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("load_to_qdrant")

# ── Qdrant imports ────────────────────────────────────────────────────────────

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    PayloadSchemaType,
    TextIndexParams,
    TokenizerType,
)

# ── Config ────────────────────────────────────────────────────────────────────

from backend.config import QDRANT_URL, QDRANT_API_KEY, DATA_DIR

EMBED_DIM = 1024          # Qwen3-Embedding-0.6B output dimension
BATCH_SIZE = 100          # points per upsert call
ACTS = ["1961", "2025"]


# ── Qdrant client ─────────────────────────────────────────────────────────────

def _build_client() -> QdrantClient:
    """Build Qdrant client — supports both local Docker and Cloud."""
    url = QDRANT_URL or "http://localhost:6333"
    api_key = QDRANT_API_KEY or None   # None = no auth (local mode)

    if api_key:
        print(f"  Connecting to Qdrant Cloud: {url}")
        return QdrantClient(url=url, api_key=api_key, timeout=60)
    else:
        print(f"  Connecting to local Qdrant: {url}")
        return QdrantClient(url=url, timeout=60)


# ── Collection management ─────────────────────────────────────────────────────

def _collection_name(act_year: str) -> str:
    return f"tax_{act_year}"


def _ensure_collection(client: QdrantClient, act_year: str, force: bool = False) -> bool:
    """
    Create collection if it doesn't exist (or force-recreate).
    Returns True if collection was just created, False if it already existed.
    """
    name = _collection_name(act_year)
    existing = {c.name for c in client.get_collections().collections}

    if name in existing:
        if force:
            print(f"  Dropping existing collection '{name}'...")
            client.delete_collection(name)
        else:
            count = client.get_collection(name).points_count or 0
            if count > 0:
                print(f"  Collection '{name}' already has {count:,} points — skipping.")
                return False  # already loaded

    print(f"  Creating collection '{name}' (dim={EMBED_DIM}, cosine)...")
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )

    # Keyword payload indices for fast server-side filtering
    for field in ("section", "income_head", "act_year", "chapter", "chunk_type", "part"):
        client.create_payload_index(
            collection_name=name,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )

    # Full-text indices for keyword search
    for field in ("text", "section_title"):
        client.create_payload_index(
            collection_name=name,
            field_name=field,
            field_schema=TextIndexParams(
                type="text",
                tokenizer=TokenizerType.WORD,
                lowercase=True,
            ),
        )

    print(f"  Collection '{name}' ready.")
    return True


# ── Batch upload ──────────────────────────────────────────────────────────────

def _upload(
    client: QdrantClient,
    act_year: str,
    chunks: list[dict],
    vectors: list[list[float]],
    progress_cb=None,
) -> None:
    """Upload chunks+vectors to Qdrant in batches with progress."""
    name = _collection_name(act_year)
    total = len(chunks)

    for start in range(0, total, BATCH_SIZE):
        bc = chunks[start: start + BATCH_SIZE]
        bv = vectors[start: start + BATCH_SIZE]

        points = [
            PointStruct(
                id=abs(hash(c["chunk_id"])) % (2 ** 63),
                vector=v,
                payload={
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
            for c, v in zip(bc, bv)
        ]

        # Retry on transient errors
        for attempt in range(3):
            try:
                client.upsert(collection_name=name, points=points)
                break
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** attempt
                    print(f"\n  Retry {attempt + 1} after {wait}s ({e})", end="")
                    time.sleep(wait)
                else:
                    raise

        done = min(start + BATCH_SIZE, total)
        pct = done / total * 100
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"  [{bar}] {done:,}/{total:,} ({pct:.0f}%)", end="\r", flush=True)

        if progress_cb:
            progress_cb(act_year, done, total)

    print()  # newline after progress bar


# ── Per-act loader ────────────────────────────────────────────────────────────

def load_act(
    act_year: str,
    client: QdrantClient,
    force: bool = False,
    progress_cb=None,
) -> bool:
    """
    Load one act's chunks + vectors into Qdrant.
    Returns True if data was loaded, False if already present (skipped).
    """
    import numpy as np

    print(f"\n{'='*60}")
    print(f"  Loading ITA {act_year} → Qdrant")
    print(f"{'='*60}")

    # ── Locate files ──────────────────────────────────────────────────────
    chunks_path = DATA_DIR / f"chunks_{act_year}.json"
    vectors_path = DATA_DIR / f"vectors_hf_{act_year}.npy"

    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {chunks_path}\n"
            f"Make sure backend/data/chunks_{act_year}.json is in the repository."
        )
    if not vectors_path.exists():
        raise FileNotFoundError(
            f"Vectors file not found: {vectors_path}\n"
            f"Make sure backend/data/vectors_hf_{act_year}.npy is in the repository."
        )

    # ── Ensure collection ─────────────────────────────────────────────────
    created = _ensure_collection(client, act_year, force=force)
    if not created:
        return False   # already loaded, skipped

    # ── Load data ─────────────────────────────────────────────────────────
    print(f"\n[1/2] Loading chunks from {chunks_path.name}...")
    with open(chunks_path, encoding="utf-8") as f:
        chunks: list[dict] = json.load(f)
    print(f"      {len(chunks):,} chunks loaded")

    print(f"[2/2] Loading vectors from {vectors_path.name}...")
    vecs = np.load(str(vectors_path))
    if vecs.shape != (len(chunks), EMBED_DIM):
        raise ValueError(
            f"Vector shape mismatch: got {vecs.shape}, "
            f"expected ({len(chunks)}, {EMBED_DIM}). "
            f"Re-run scripts/embed_and_upload.py to regenerate."
        )
    vectors: list[list[float]] = vecs.tolist()
    print(f"      {len(vectors):,} vectors loaded ({EMBED_DIM}-dim)")

    # ── Upload ────────────────────────────────────────────────────────────
    print(f"\n  Uploading to Qdrant...")
    t0 = time.time()
    _upload(client, act_year, chunks, vectors, progress_cb=progress_cb)
    elapsed = time.time() - t0

    # Verify
    count = client.get_collection(_collection_name(act_year)).points_count or 0
    print(f"\n  ✓ {count:,} points loaded in {elapsed:.1f}s")
    return True


# ── Public API (called from backend on startup) ───────────────────────────────

def load_all(
    force: bool = False,
    progress_cb=None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
) -> dict[str, bool]:
    """
    Load both acts. Returns dict of {act_year: was_loaded}.
    Called from backend/main.py on startup when collections are empty.

    progress_cb: optional callable(act_year: str, done: int, total: int)
    """
    import os
    url = qdrant_url or QDRANT_URL or "http://localhost:6333"
    key = qdrant_api_key or QDRANT_API_KEY or None

    if key:
        client = QdrantClient(url=url, api_key=key, timeout=60)
    else:
        client = QdrantClient(url=url, timeout=60)

    results = {}
    try:
        for act in ACTS:
            results[act] = load_act(act, client, force=force, progress_cb=progress_cb)
    finally:
        client.close()

    return results


def collections_populated(
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
) -> bool:
    """
    Quick check: are both collections non-empty?
    Used by backend/main.py to decide if auto-load is needed.
    """
    url = qdrant_url or QDRANT_URL or "http://localhost:6333"
    key = qdrant_api_key or QDRANT_API_KEY or None

    try:
        if key:
            client = QdrantClient(url=url, api_key=key, timeout=10)
        else:
            client = QdrantClient(url=url, timeout=10)

        existing = {c.name for c in client.get_collections().collections}
        for act in ACTS:
            name = _collection_name(act)
            if name not in existing:
                return False
            count = client.get_collection(name).points_count or 0
            if count == 0:
                return False
        client.close()
        return True
    except Exception:
        return False


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Load pre-computed TaxIQ vectors into Qdrant (local or cloud)."
    )
    parser.add_argument(
        "--act", choices=["1961", "2025"],
        help="Load only one act (default: both)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Drop existing collections and reload from scratch"
    )
    parser.add_argument(
        "--url", default=None,
        help="Qdrant URL (overrides .env QDRANT_URL, default: http://localhost:6333)"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    print("\n" + "="*60)
    print("  TaxIQ — Qdrant Data Loader")
    print("="*60)

    url = args.url or QDRANT_URL or "http://localhost:6333"
    key = QDRANT_API_KEY or None

    print(f"\n  Qdrant : {url}  ({'cloud' if key else 'local'})")
    print(f"  Data   : {DATA_DIR}")
    print(f"  Acts   : {args.act or '1961 + 2025'}")
    print(f"  Force  : {args.force}")
    print()

    if key:
        client = QdrantClient(url=url, api_key=key, timeout=60)
    else:
        client = QdrantClient(url=url, timeout=60)

    # Check Qdrant is reachable
    try:
        client.get_collections()
        print("  Qdrant connection: OK ✓\n")
    except Exception as e:
        print(f"\n  ERROR: Cannot connect to Qdrant at {url}")
        print(f"  {e}")
        print("\n  If using Docker, make sure it's running:")
        print("    docker compose up -d qdrant")
        sys.exit(1)

    acts = [args.act] if args.act else ACTS
    t_start = time.time()
    loaded = 0

    for act in acts:
        was_loaded = load_act(act, client, force=args.force)
        if was_loaded:
            loaded += 1

    client.close()

    total = time.time() - t_start
    mins, secs = divmod(int(total), 60)

    print("\n" + "="*60)
    print("  Summary")
    print("="*60)
    if loaded == 0:
        print("  All collections already populated — nothing to do.")
        print("  Use --force to reload from scratch.")
    else:
        print(f"  Loaded {loaded} act(s) in {mins}m {secs}s")
    print("\n  Start TaxIQ with:  ./start.sh")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
