"""
Qdrant Cloud vector store wrapper.

Connects to Qdrant Cloud free cluster using QDRANT_URL + QDRANT_API_KEY from .env.

Two collections per Act:
  - tax_2025  / tax_1961   (PDF-extracted chunks from extract_and_index.py)

Payload per point (Chunk.to_payload()):
  chunk_id, act_year, chapter, chapter_title, section, section_title,
  part, income_head, chunk_index, chunk_type, text, page_start, page_end
"""

from __future__ import annotations
import logging
from typing import Any

_log = logging.getLogger("qdrant_store")

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType,
    TextIndexParams,
    TokenizerType,
)

from .chunker import Chunk
from .embedder import EMBED_DIM
from ..config import QDRANT_URL, QDRANT_API_KEY
from ..enrichment.rag_schema import RagChunk


def _collection_name(act_year: str) -> str:
    return f"tax_{act_year}"


def _build_client() -> QdrantClient:
    """Build Qdrant Cloud client from config."""
    if not QDRANT_URL or not QDRANT_API_KEY:
        raise RuntimeError(
            "Qdrant Cloud credentials missing.\n"
            "Set QDRANT_URL and QDRANT_API_KEY in your .env file.\n"
            "Get them from: https://cloud.qdrant.io"
        )
    return QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        timeout=120,          # 120s per request (4096-dim vectors are large)
    )


class QdrantStore:
    """
    Qdrant Cloud vector store for Income Tax Act chunks.

    Usage:
        store = QdrantStore()
        store.upsert_chunks(chunks, vectors, act_year="2025")
        results = store.search(query_vector, act_year="2025", top_k=8)
    """

    def __init__(self):
        self._client = _build_client()

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def ensure_collection(self, act_year: str, recreate: bool = False) -> None:
        name = _collection_name(act_year)
        exists = any(c.name == name for c in self._client.get_collections().collections)

        if exists and recreate:
            self._client.delete_collection(name)
            exists = False

        if not exists:
            self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )

            # Keyword payload indices (for fast filtering)
            for field_name in ("section", "income_head", "act_year", "chapter", "chunk_type", "part"):
                self._client.create_payload_index(
                    collection_name=name,
                    field_name=field_name,
                    field_schema=PayloadSchemaType.KEYWORD,
                )

            # Full-text indices
            for ft_field in ("text", "section_title"):
                self._client.create_payload_index(
                    collection_name=name,
                    field_name=ft_field,
                    field_schema=TextIndexParams(
                        type="text",
                        tokenizer=TokenizerType.WORD,
                        lowercase=True,
                    ),
                )

            print(f"  Created collection '{name}' (dim={EMBED_DIM}, cosine)")

    def collection_exists(self, act_year: str) -> bool:
        name = _collection_name(act_year)
        return any(c.name == name for c in self._client.get_collections().collections)

    def collection_point_count(self, act_year: str) -> int:
        name = _collection_name(act_year)
        if not self.collection_exists(act_year):
            return 0
        info = self._client.get_collection(name)
        return info.points_count or 0

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]],
        act_year: str,
        batch_size: int = 25,     # small batches — 4096-dim vectors are ~400KB each
        verbose: bool = True,
        max_retries: int = 3,
    ) -> None:
        """Upload chunks with their precomputed vectors to Qdrant Cloud."""
        import time

        assert len(chunks) == len(vectors)
        name = _collection_name(act_year)
        self.ensure_collection(act_year)

        for batch_start in range(0, len(chunks), batch_size):
            bc = chunks[batch_start: batch_start + batch_size]
            bv = vectors[batch_start: batch_start + batch_size]

            points = [
                PointStruct(
                    id=abs(hash(c.id)) % (2 ** 63),
                    vector=v,
                    payload=c.to_payload(),
                )
                for c, v in zip(bc, bv)
            ]

            # Retry on transient network errors
            for attempt in range(max_retries):
                try:
                    self._client.upsert(collection_name=name, points=points)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = 2 ** attempt  # 1s, 2s, 4s
                        if verbose:
                            print(f"\n  Retry {attempt + 1} after {wait}s (error: {e})")
                        time.sleep(wait)
                    else:
                        raise

            if verbose:
                done = min(batch_start + batch_size, len(chunks))
                print(f"  Uploaded {done}/{len(chunks)}", end="\r")

        if verbose:
            print(f"\n  Done: {len(chunks)} chunks → '{name}' (Qdrant Cloud)")

    def upsert_rag_chunks(
        self,
        chunks: list[RagChunk],
        vectors: list[list[float]],
        act_year: str,
        batch_size: int = 25,
        verbose: bool = True,
        max_retries: int = 3,
    ) -> None:
        """
        Upload enriched RagChunk objects (with LLM-generated fields) to Qdrant.
        Always recreates the collection to replace heuristic chunks with enriched ones.
        """
        import time

        assert len(chunks) == len(vectors), "chunks and vectors must have the same length"
        name = _collection_name(act_year)

        # Wipe and recreate — enriched chunks replace the old heuristic index
        self.ensure_collection(act_year, recreate=True)

        for batch_start in range(0, len(chunks), batch_size):
            bc = chunks[batch_start: batch_start + batch_size]
            bv = vectors[batch_start: batch_start + batch_size]

            points = [
                PointStruct(
                    id=abs(hash(c.chunk_id)) % (2 ** 63),
                    vector=v,
                    payload=c.to_qdrant_payload(),
                )
                for c, v in zip(bc, bv)
            ]

            for attempt in range(max_retries):
                try:
                    self._client.upsert(collection_name=name, points=points)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = 2 ** attempt
                        if verbose:
                            print(f"\n  Retry {attempt + 1} after {wait}s (error: {e})")
                        time.sleep(wait)
                    else:
                        raise

            if verbose:
                done = min(batch_start + batch_size, len(chunks))
                print(f"  Uploaded {done}/{len(chunks)}", end="\r")

        if verbose:
            print(f"\n  Done (enriched): {len(chunks)} chunks → '{name}' (Qdrant Cloud)")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_vector: list[float],
        act_year: str,
        top_k: int = 8,
        income_head: str | None = None,
        chunk_type: str | None = None,
        chapter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Cosine vector search with optional server-side payload filtering.
        Payload filters are applied by Qdrant BEFORE scoring — very fast.
        Uses query_points (qdrant-client >= 1.7).
        """
        name = _collection_name(act_year)
        _log.info(
            "[Qdrant] vector search | collection=%s | top_k=%d | income_head=%s | chunk_type=%s",
            name, top_k, income_head, chunk_type,
        )
        print(f"[Qdrant] vector search → {name} (top_k={top_k}, income_head={income_head}, chunk_type={chunk_type})",
              flush=True)
        if not self.collection_exists(act_year):
            print(f"[Qdrant] collection '{name}' does not exist — returning empty", flush=True)
            return []

        conditions = []
        if income_head:
            conditions.append(FieldCondition(key="income_head", match=MatchValue(value=income_head)))
        if chunk_type:
            conditions.append(FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type)))
        if chapter:
            conditions.append(FieldCondition(key="chapter", match=MatchValue(value=chapter)))

        query_filter = Filter(must=conditions) if conditions else None

        results = self._client.query_points(
            collection_name=name,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )

        return [{**r.payload, "score": r.score} for r in results.points]

    def search_by_section(
        self,
        section_number: str,
        act_year: str,
    ) -> list[dict[str, Any]]:
        """Exact section lookup — returns all chunks for a section, sorted by clause path."""
        name = _collection_name(act_year)
        _log.info("[Qdrant] search_by_section | section=%s | collection=%s", section_number, name)
        print(f"[Qdrant] search_by_section → section={section_number!r} in {name}", flush=True)
        if not self.collection_exists(act_year):
            print(f"[Qdrant] collection '{name}' does not exist — returning empty", flush=True)
            return []

        results, _ = self._client.scroll(
            collection_name=name,
            scroll_filter=Filter(
                must=[FieldCondition(key="section", match=MatchValue(value=section_number))]
            ),
            with_payload=True,
            limit=200,
        )

        payloads = [r.payload for r in results]
        payloads.sort(key=lambda p: p.get("chunk_index", 0))
        return payloads

    def search_both_acts(
        self,
        query_vector: list[float],
        top_k: int = 8,
        income_head: str | None = None,
        chunk_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search both collections with payload filters and merge by score."""
        _log.info("[Qdrant] search_both_acts | top_k=%d | income_head=%s", top_k, income_head)
        print(f"[Qdrant] search_both_acts (top_k={top_k}, income_head={income_head})", flush=True)
        r2025 = self.search(query_vector, "2025", top_k, income_head=income_head, chunk_type=chunk_type)
        r1961 = self.search(query_vector, "1961", top_k, income_head=income_head, chunk_type=chunk_type)
        combined = r2025 + r1961
        combined.sort(key=lambda r: r.get("score", 0), reverse=True)
        return combined[:top_k]

    def scroll_by_payload(
        self,
        act_year: str,
        filters: dict[str, str],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Pure payload scroll — no vector needed.
        Useful for: list all definitions, all exceptions in a chapter, etc.
        filters: e.g. {"income_head": "Salaries", "type": "definition"}
        """
        name = _collection_name(act_year)
        if not self.collection_exists(act_year):
            return []

        conditions = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in filters.items()
        ]

        results, _ = self._client.scroll(
            collection_name=name,
            scroll_filter=Filter(must=conditions),
            with_payload=True,
            limit=limit,
        )
        return [r.payload for r in results]

    def close(self) -> None:
        self._client.close()
