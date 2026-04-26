"""
Batch enrichment pipeline: parsed_{act}.json → enriched_{act}.json

Speed features:
  • llm_batch_size (default 5): each LLM call processes N sections at once.
    Combined with concurrency=8, this gives ~40 sections in flight simultaneously.
  • Semaphore-controlled async concurrency: N LLM batch calls in parallel.
  • JSONL checkpoint: safe to kill and resume at any time.
  • Progress bar: shows sections/s rate and ETA every update.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from ..parsing.structure import ParsedAct, Section
from ..rag.llm_provider import LLMConfig
from .llm_enricher import enrich_batch_async, _heuristic_section, GlobalRateLimiter
from .rag_schema import RagChunk

_log = logging.getLogger("batch_enricher")


# ── Checkpoint helpers ─────────────────────────────────────────────────────────

def _load_checkpoint(path: Path) -> set[str]:
    """Return set of already-enriched section numbers."""
    done: set[str] = set()
    if not path.exists():
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                sec = obj.get("section")
                if sec:
                    done.add(str(sec))
            except json.JSONDecodeError:
                continue
    return done


def _append_checkpoint(path: Path, chunks: list[RagChunk]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")


def _load_all_from_checkpoint(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not path.exists():
        return items
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return items


# ── Core async pipeline ────────────────────────────────────────────────────────

async def _run_pipeline(
    sections: list[Section],
    config: LLMConfig,
    checkpoint_path: Path,
    concurrency: int,
    llm_batch_size: int,
    verbose: bool,
) -> list[RagChunk]:
    """
    Groups sections into batches of llm_batch_size, runs up to `concurrency`
    batches in parallel. Each batch = 1 LLM call → N sections enriched.

    ONE GlobalRateLimiter is shared across all concurrent tasks so that
    a 429 from any single batch pauses every other in-flight batch.
    """
    semaphore    = asyncio.Semaphore(concurrency)
    rate_limiter = GlobalRateLimiter(
        rate_limit_backoff  = 30.0,  # 429 → pause all for 30s
        server_error_backoff = 8.0,  # 500 → pause all for 8s
    )

    # Split into batches
    batches = [
        sections[i: i + llm_batch_size]
        for i in range(0, len(sections), llm_batch_size)
    ]

    total_sections = len(sections)
    total_batches  = len(batches)
    completed_secs = 0
    failed_secs    = 0
    all_chunks: list[RagChunk] = []
    t_start = time.time()

    if verbose:
        effective = concurrency * llm_batch_size
        print(f"  {total_sections} sections → {total_batches} batches "
              f"(batch={llm_batch_size}, concurrency={concurrency}, "
              f"~{effective} sections in-flight)", flush=True)

    async def process_batch(batch: list[Section], batch_idx: int) -> None:
        nonlocal completed_secs, failed_secs

        async with semaphore:
            try:
                result = await enrich_batch_async(batch, config, rate_limiter)
            except Exception as e:
                _log.error("Batch %d failed entirely: %s", batch_idx, e)
                result = {s.number: _heuristic_section(s) for s in batch}
                nonlocal failed_secs
                failed_secs += len(batch)

            chunks_this_batch: list[RagChunk] = []
            for s in batch:
                sec_chunks = result.get(s.number, _heuristic_section(s))
                chunks_this_batch.extend(sec_chunks)
                all_chunks.extend(sec_chunks)

            _append_checkpoint(checkpoint_path, chunks_this_batch)
            completed_secs += len(batch)

            if verbose:
                elapsed = time.time() - t_start
                rate    = completed_secs / elapsed if elapsed > 0 else 0
                pct     = completed_secs / total_sections * 100
                eta_s   = (total_sections - completed_secs) / rate if rate > 0 else 0
                eta_str = f"{eta_s/60:.0f}m" if eta_s > 90 else f"{eta_s:.0f}s"
                print(
                    f"  [{completed_secs}/{total_sections}] {pct:.0f}%  "
                    f"rate={rate:.1f} sec/s  ETA={eta_str}  failures={failed_secs}    ",
                    end="\r", flush=True,
                )

    tasks = [
        asyncio.create_task(process_batch(b, i))
        for i, b in enumerate(batches)
    ]
    await asyncio.gather(*tasks)

    if verbose:
        elapsed = time.time() - t_start
        rate    = total_sections / elapsed if elapsed > 0 else 0
        print(f"\n  Done: {completed_secs} sections | "
              f"{len(all_chunks)} chunks | "
              f"{rate:.1f} sec/s | {failed_secs} failures",
              flush=True)

    return all_chunks


# ── Public API ─────────────────────────────────────────────────────────────────

def enrich_act(
    act_year: str,
    config: LLMConfig,
    data_dir: Path,
    resume: bool = False,
    concurrency: int = 3,       # 3 concurrent batches — safe for Ollama Cloud rate limits
    llm_batch_size: int = 5,    # 5 sections per LLM call
    verbose: bool = True,
) -> list[RagChunk]:
    """
    Run the full enrichment pipeline for one act.

    Speed levers (effective throughput ≈ concurrency × llm_batch_size sections/call):
      concurrency=3, llm_batch_size=5  → ~15 sections/call-round, rate-limit safe
      concurrency=5, llm_batch_size=8  → ~40 sections/call-round (riskier on free tier)

    A shared GlobalRateLimiter ensures all concurrent calls back off together
    when Ollama Cloud returns 429 or 500, preventing the cascade failure.

    Outputs:
      data_dir/enriched_{act_year}_progress.jsonl  — live checkpoint
      data_dir/enriched_{act_year}.json            — final merged output
    """
    parsed_path     = data_dir / f"parsed_{act_year}.json"
    checkpoint_path = data_dir / f"enriched_{act_year}_progress.jsonl"
    output_path     = data_dir / f"enriched_{act_year}.json"

    if not parsed_path.exists():
        raise FileNotFoundError(
            f"Parsed data not found: {parsed_path}\n"
            f"Run: python scripts/parse_pdfs.py --act {act_year}"
        )

    if verbose:
        size_mb = parsed_path.stat().st_size / 1024 / 1024
        print(f"Loading {parsed_path.name} ({size_mb:.1f} MB)...")

    with open(parsed_path, encoding="utf-8") as f:
        data = json.load(f)
    parsed = ParsedAct.model_validate(data)

    if verbose:
        print(f"Loaded {len(parsed.sections)} sections from {act_year} Act")

    # Resume
    done_sections: set[str] = set()
    existing_chunks: list[dict[str, Any]] = []
    if resume and checkpoint_path.exists():
        done_sections   = _load_checkpoint(checkpoint_path)
        existing_chunks = _load_all_from_checkpoint(checkpoint_path)
        if verbose:
            print(f"Resuming: {len(done_sections)} already done, "
                  f"{len(existing_chunks)} chunks loaded")
    elif not resume and checkpoint_path.exists():
        checkpoint_path.unlink()
        if verbose:
            print("Cleared previous checkpoint. Use --resume to continue interrupted runs.")

    remaining = [s for s in parsed.sections if str(s.number) not in done_sections]
    if not remaining:
        if verbose:
            print("All sections already enriched. Nothing to do.")
        all_chunks = [RagChunk.model_validate(d) for d in existing_chunks]
        return all_chunks

    if verbose:
        print(f"Sections remaining: {len(remaining)}", flush=True)

    t0 = time.time()
    new_chunks = asyncio.run(
        _run_pipeline(
            sections        = remaining,
            config          = config,
            checkpoint_path = checkpoint_path,
            concurrency     = concurrency,
            llm_batch_size  = llm_batch_size,
            verbose         = verbose,
        )
    )
    elapsed = time.time() - t0

    all_chunk_dicts = existing_chunks + [c.model_dump() for c in new_chunks]

    # Save final JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_chunk_dicts, f, ensure_ascii=False, indent=2)

    if verbose:
        size_mb = output_path.stat().st_size / 1024 / 1024
        rate    = len(remaining) / elapsed if elapsed > 0 else 0
        print(f"Saved {len(all_chunk_dicts)} chunks → {output_path.name} "
              f"({size_mb:.1f} MB)  [{elapsed:.0f}s, {rate:.1f} sec/s]")

    return [RagChunk.model_validate(d) for d in all_chunk_dicts]
