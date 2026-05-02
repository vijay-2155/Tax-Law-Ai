"""
HuggingFace embedding client using sentence-transformers.

Model : Qwen/Qwen3-Embedding-0.6B  (~2.4 GB, 1024-dim)
Source: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B

The model is downloaded automatically on first use and cached in
~/.cache/huggingface/hub. Subsequent loads are instant.

Uses a lazy singleton — model is NOT loaded at import time.
It is loaded on the first call to embed_texts() or embed_query().
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from ..config import HF_EMBED_MODEL, EMBED_DEVICE, HF_TOKEN

# ── Embedding dimension ───────────────────────────────────────────────────────
EMBED_DIM = 1024          # Qwen3-Embedding-0.6B native output dimension
EMBED_MODEL = HF_EMBED_MODEL

# ── Batching ──────────────────────────────────────────────────────────────────
_BATCH_SIZE = 32          # sentence-transformers handles batching internally
_RETRY_DELAY = 2.0
_MAX_RETRIES = 3

# ── Lazy singleton ────────────────────────────────────────────────────────────
_model = None
_model_loaded = False


def _resolve_device() -> str:
    """Auto-detect best available device unless overridden in config."""
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


def _get_model():
    """Lazy-load and cache the SentenceTransformer model."""
    global _model, _model_loaded
    if _model_loaded:
        return _model

    from sentence_transformers import SentenceTransformer

    # Set HF token if provided (speeds up downloads, allows gated models)
    if HF_TOKEN:
        os.environ.setdefault("HF_TOKEN", HF_TOKEN)
        os.environ.setdefault("HUGGINGFACE_TOKEN", HF_TOKEN)

    device = _resolve_device()
    print(f"[Embedder] Loading {EMBED_MODEL} on device={device!r} ...", flush=True)
    t0 = time.time()

    _model = SentenceTransformer(EMBED_MODEL, device=device)

    elapsed = time.time() - t0
    print(f"[Embedder] Model ready ({elapsed:.1f}s). dim={EMBED_DIM}, device={device}", flush=True)
    _model_loaded = True
    return _model


# ── Public API ────────────────────────────────────────────────────────────────

def embed_texts(texts: list[str], verbose: bool = False) -> list[list[float]]:
    """
    Embed a list of texts using Qwen3-Embedding-0.6B.
    Returns list of 1024-dim float vectors, one per input text.
    Handles batching automatically via sentence-transformers.
    """
    if not texts:
        return []

    model = _get_model()

    for attempt in range(_MAX_RETRIES):
        try:
            if verbose:
                print(f"  Embedding {len(texts)} texts (batch_size={_BATCH_SIZE})...", flush=True)

            embeddings = model.encode(
                texts,
                batch_size=_BATCH_SIZE,
                show_progress_bar=verbose,
                normalize_embeddings=True,   # cosine similarity works best with L2-normalized vecs
                convert_to_numpy=True,
            )

            result = embeddings.tolist()

            if verbose:
                print(f"  Done: {len(result)} vectors ({len(result[0])}-dim)", flush=True)

            return result

        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                print(f"[Embedder] Attempt {attempt + 1} failed: {e} — retrying in {_RETRY_DELAY}s", flush=True)
                time.sleep(_RETRY_DELAY)
                continue
            raise RuntimeError(f"Embedding failed after {_MAX_RETRIES} retries: {e}") from e

    return []  # unreachable


def embed_query(text: str) -> list[float]:
    """
    Embed a single query string.
    Uses the same model as embed_texts — consistent vector space.
    """
    return embed_texts([text])[0]


def check_embedder_available() -> bool:
    """
    Return True if the embedding model can be loaded successfully.
    Used by build_index.py to validate setup before indexing.
    """
    try:
        model = _get_model()
        # Quick sanity check: embed a tiny test string
        vec = embed_texts(["test"])
        return len(vec) == 1 and len(vec[0]) == EMBED_DIM
    except Exception as e:
        print(f"[Embedder] check failed: {e}", flush=True)
        return False


# Legacy alias — some scripts import check_ollama_available
def check_ollama_available() -> bool:
    """Deprecated alias — calls check_embedder_available() instead."""
    return check_embedder_available()
