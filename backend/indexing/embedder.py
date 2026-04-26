"""
Ollama embedding client for qwen3-embedding (1024-dim).
Batches requests to avoid overwhelming Ollama.
"""

from __future__ import annotations
import httpx
import time
from typing import Iterator

from ..config import OLLAMA_BASE_URL as OLLAMA_BASE, OLLAMA_EMBED_MODEL as EMBED_MODEL

EMBED_DIM = 4096
_BATCH_SIZE = 16       # embed this many texts per API call
_RETRY_DELAY = 2.0     # seconds between retries
_MAX_RETRIES = 3


def embed_texts(texts: list[str], verbose: bool = False) -> list[list[float]]:
    """
    Embed a list of texts using Ollama qwen3-embedding.
    Returns list of 1024-dim float vectors, one per input text.
    Batches automatically.
    """
    all_vectors: list[list[float]] = []

    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start: batch_start + _BATCH_SIZE]
        if verbose:
            print(f"  Embedding batch {batch_start // _BATCH_SIZE + 1} "
                  f"({batch_start + 1}–{batch_start + len(batch)} of {len(texts)})")

        vectors = _embed_batch(batch)
        all_vectors.extend(vectors)

    return all_vectors


def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    return _embed_batch([text])[0]


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Call Ollama /api/embed with retry logic."""
    for attempt in range(_MAX_RETRIES):
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{OLLAMA_BASE}/api/embed",
                    json={"model": EMBED_MODEL, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", [])
                if len(embeddings) != len(texts):
                    raise ValueError(
                        f"Expected {len(texts)} embeddings, got {len(embeddings)}"
                    )
                return embeddings
        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY)
                continue
            raise RuntimeError(f"Embedding failed after {_MAX_RETRIES} retries: {e}") from e

    return []  # unreachable


def check_ollama_available() -> bool:
    """Return True if Ollama is running and qwen3-embedding is available."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{OLLAMA_BASE}/api/tags")
            if resp.status_code != 200:
                return False
            models = [m["name"] for m in resp.json().get("models", [])]
            return any(EMBED_MODEL in m for m in models)
    except Exception:
        return False
