"""
BGE Cross-Encoder Reranker using sentence-transformers.

Model : BAAI/bge-reranker-large  (~1.3 GB)
Source: https://huggingface.co/BAAI/bge-reranker-large

Cross-encoders score each (query, passage) pair jointly — much more accurate
than bi-encoder cosine similarity for determining true relevance. The cost is
O(N) inference passes, so we call it AFTER vector retrieval to rerank a small
candidate set (e.g. top-20) down to the best K (e.g. top-8).

Pipeline:
  Vector search (top-20 candidates, fast)
    → BGE reranker scores each pair
      → Return top-8 by cross-encoder score

The reranker replaces the previous LLM-based grade_documents step, which was
slow (full LLM call) and expensive. The cross-encoder is faster, cheaper, and
more accurate for pure relevance scoring.
"""

from __future__ import annotations

import os
import time
from typing import Any

from ..config import HF_RERANKER_MODEL, EMBED_DEVICE, HF_TOKEN

# ── Lazy singleton ────────────────────────────────────────────────────────────
_reranker = None
_reranker_loaded = False


def _resolve_device() -> str:
    """Auto-detect best device for the reranker."""
    if EMBED_DEVICE:
        return EMBED_DEVICE
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def _get_reranker():
    """Lazy-load and cache the CrossEncoder model."""
    global _reranker, _reranker_loaded
    if _reranker_loaded:
        return _reranker

    from sentence_transformers import CrossEncoder

    # Set HF token if provided
    if HF_TOKEN:
        os.environ.setdefault("HF_TOKEN", HF_TOKEN)
        os.environ.setdefault("HUGGINGFACE_TOKEN", HF_TOKEN)

    device = _resolve_device()
    print(f"[Reranker] Loading {HF_RERANKER_MODEL} on device={device!r} ...", flush=True)
    t0 = time.time()

    _reranker = CrossEncoder(
        HF_RERANKER_MODEL,
        device=device,
        max_length=512,   # BGE-reranker-large max context
    )

    elapsed = time.time() - t0
    print(f"[Reranker] Model ready ({elapsed:.1f}s).", flush=True)
    _reranker_loaded = True
    return _reranker


# ── Public API ────────────────────────────────────────────────────────────────

def rerank(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """
    Rerank a list of retrieved chunks by cross-encoder relevance score.

    Args:
        query  : The user's search query.
        chunks : List of chunk dicts (must have a 'text' key).
        top_k  : How many top chunks to return after reranking.

    Returns:
        Reranked list (length <= top_k), sorted by cross-encoder score descending.
        Each chunk gets an updated 'score' field with the reranker's score.
    """
    if not chunks:
        return []

    if len(chunks) <= top_k:
        # No need to rerank if we have fewer candidates than needed
        return chunks

    model = _get_reranker()

    # Build (query, passage) pairs — BGE expects this format
    pairs = [(query, c.get("text", "")[:512]) for c in chunks]

    try:
        t0 = time.time()
        scores = model.predict(pairs, batch_size=16, show_progress_bar=False)
        elapsed = time.time() - t0
        print(
            f"[Reranker] Scored {len(chunks)} chunks → top {top_k} "
            f"(elapsed={elapsed:.2f}s)",
            flush=True,
        )
    except Exception as e:
        # Fallback: return original order if reranker fails
        print(f"[Reranker] Scoring failed: {e} — returning original order", flush=True)
        return chunks[:top_k]

    # Pair each chunk with its reranker score and sort descending
    scored = sorted(
        zip(chunks, scores.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )

    # Build result — update score field with reranker score
    result = []
    for chunk, score in scored[:top_k]:
        reranked_chunk = dict(chunk)
        reranked_chunk["score"] = round(float(score), 4)
        reranked_chunk["reranker_score"] = round(float(score), 4)
        result.append(reranked_chunk)

    return result


def rerank_with_fallback(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """
    Rerank with graceful fallback to original order if model load fails.
    Safe to call even if sentence-transformers is not installed.
    """
    try:
        return rerank(query, chunks, top_k)
    except Exception as e:
        print(f"[Reranker] Disabled (error: {e}) — using raw vector scores", flush=True)
        return sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)[:top_k]
