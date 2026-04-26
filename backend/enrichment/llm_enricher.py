"""
LLM-based enrichment of parsed Income Tax Act sections → RagChunk objects.

Speed design:
  • MULTI-SECTION BATCHING — sends N sections per LLM call (default 5).
    This is the key speed multiplier: 5-10× fewer HTTP round-trips.
  • Async concurrency — multiple batches run in parallel (semaphore-controlled).
  • GlobalRateLimiter — when ANY request gets a 429/500, ALL concurrent
    requests pause before retrying. Prevents the cascade of failures seen
    when concurrency is too high for the cloud rate limit.
  • Thin prompts — only essential fields sent; max_tokens capped at 2048.
  • Trivial-section skip — very short sections use heuristic directly (no LLM).
  • <think> strip — works with all reasoning models (qwq, deepseek-r1, kimi-thinking).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import logging
from typing import Any

from ..parsing.structure import Section, Subsection, Clause
from ..indexing.chunker import (
    _clean,
    _classify_type,
    _extract_keywords,
    _extract_related_sections,
    _make_id,
    _build_path,
)
from ..rag.llm_provider import LLMConfig, get_provider
from .rag_schema import RagChunk

_log = logging.getLogger("llm_enricher")

# Minimum content length to bother calling LLM (shorter → heuristic only)
_MIN_LLM_TEXT_LEN = 80

# Hard cap on text sent per section inside the batch prompt
_MAX_TEXT_PER_SECTION = 2500

# ── Regex ──────────────────────────────────────────────────────────────────────
_THINK_RE    = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_ARR_RE = re.compile(r"\[.*\]", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


# ── Shared rate limiter ────────────────────────────────────────────────────────

class GlobalRateLimiter:
    """
    Shared across ALL concurrent batch calls.

    When any call gets a 429 (rate limit) or 500 (server overload), this
    sets a global backoff window that ALL other in-flight requests check
    before initiating new calls. This prevents the cascade where every
    concurrent request hits the limit one after another.

    Usage:
        limiter = GlobalRateLimiter()
        # Before each call:
        await limiter.wait()
        # On 429:
        await limiter.on_rate_limit()
        # On 500:
        await limiter.on_server_error()
    """
    def __init__(self, rate_limit_backoff: float = 30.0, server_error_backoff: float = 8.0):
        self._backoff_until   = 0.0
        self._rate_backoff    = rate_limit_backoff
        self._server_backoff  = server_error_backoff
        self._lock            = asyncio.Lock()

    async def wait(self) -> None:
        """Pause if we're in a global backoff window."""
        now = time.monotonic()
        if now < self._backoff_until:
            sleep_for = self._backoff_until - now
            _log.debug("Rate limiter: waiting %.1fs before next call", sleep_for)
            await asyncio.sleep(sleep_for)

    async def on_rate_limit(self) -> None:
        """Called when a 429 is received — impose global pause."""
        async with self._lock:
            new_until = time.monotonic() + self._rate_backoff
            if new_until > self._backoff_until:
                self._backoff_until = new_until
                _log.warning(
                    "Rate limit hit (429) — all requests paused for %.0fs",
                    self._rate_backoff,
                )

    async def on_server_error(self) -> None:
        """Called when a 500 is received — shorter pause."""
        async with self._lock:
            new_until = time.monotonic() + self._server_backoff
            if new_until > self._backoff_until:
                self._backoff_until = new_until
                _log.warning(
                    "Server error (500) — all requests paused for %.0fs",
                    self._server_backoff,
                )


# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a legal data engineer specialised in Indian tax law. "
    "Output ONLY valid JSON — no markdown fences, no explanation."
)

# ── Multi-section batch prompt ─────────────────────────────────────────────────

_BATCH_PROMPT_HEADER = """\
Enrich the following {n} Income Tax Act sections. For EACH section output one entry in the top-level JSON array.

OUTPUT FORMAT — strict JSON, one object per section:
[
  {{
    "section": "<section number>",
    "chunks": [
      {{
        "subsection": "(1)" or "",
        "clause": "(a)" or "",
        "content": "original text lightly cleaned",
        "clean_text": "plain English rewrite, all legal details preserved",
        "summary": "2-3 lines for a CA intern",
        "conditions": ["short eligibility rule"],
        "exceptions": ["short proviso/exclusion"],
        "keywords": ["term1", "term2"],
        "references": ["section 10", "section 45"]
      }}
    ]
  }}
]

RULES: no hallucination · conditions/exceptions = short strings · keywords 5-10 terms · output JSON only

--- SECTIONS ---
{sections_block}"""

_SECTION_BLOCK_TEMPLATE = """\
[{idx}] Section {section} ({act_year} Act) | Chapter {chapter}: {chapter_title} | Head: {income_head}
Title: {section_title}
Text:
{raw_text}
"""


# ── Heuristic fallback ─────────────────────────────────────────────────────────

def _heuristic_chunk(
    section: Section,
    sub: Subsection | None = None,
    clause: Clause | None = None,
) -> RagChunk:
    act_year  = section.act
    sub_num   = sub.number if sub else ""
    clause_id = clause.identifier if clause else ""

    if clause:
        raw  = f"({clause_id}) {clause.text}"
        path = _build_path(sub_num, clause_id)
    elif sub:
        raw  = sub.text
        path = _build_path(sub_num)
    else:
        raw  = section.full_text
        path = ""

    content  = _clean(raw)
    keywords = _extract_keywords(content, section.title)
    refs     = _extract_related_sections(content)

    mapped_to: str | None = None
    if section.mapped_section:
        other     = "2025" if act_year == "1961" else "1961"
        mapped_to = f"{other}_S{section.mapped_section}"

    return RagChunk(
        act_year      = act_year,
        chunk_id      = _make_id(act_year, section.number, path),
        chapter       = section.chapter_number,
        chapter_title = section.chapter_title,
        section       = section.number,
        section_title = section.title,
        subsection    = f"({sub_num})" if sub_num else "",
        clause        = f"({clause_id})" if clause_id else "",
        content       = content,
        clean_text    = content,
        summary       = "",
        conditions    = [],
        exceptions    = sub.provisos if sub else [],
        keywords      = keywords,
        references    = [f"section {r}" for r in refs],
        income_head   = section.income_head or "General / Definitions",
        clause_path   = path,
        chunk_type    = _classify_type(content),
        mapped_to     = mapped_to,
        page_start    = section.page_start,
        page_end      = section.page_end,
    )


def _heuristic_section(section: Section) -> list[RagChunk]:
    if section.subsections:
        return [_heuristic_chunk(section, sub) for sub in section.subsections]
    return [_heuristic_chunk(section)]


# ── JSON helpers ───────────────────────────────────────────────────────────────

def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


def _extract_json_array(raw: str) -> list[dict[str, Any]]:
    cleaned = _strip_think(raw)

    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
    except Exception:
        pass

    m = _JSON_ARR_RE.search(cleaned)
    if m:
        try:
            result = json.loads(m.group(0))
            if isinstance(result, list):
                return result
        except Exception:
            pass

    m_obj = _JSON_OBJ_RE.search(cleaned)
    if m_obj:
        try:
            return [json.loads(m_obj.group(0))]
        except Exception:
            pass

    raise ValueError(f"No valid JSON in LLM response:\n{raw[:400]}")


# ── Batch builder ──────────────────────────────────────────────────────────────

def _build_batch_prompt(sections: list[Section]) -> str:
    blocks = []
    for i, s in enumerate(sections, 1):
        text = _clean(s.full_text[:_MAX_TEXT_PER_SECTION]) or s.title
        blocks.append(_SECTION_BLOCK_TEMPLATE.format(
            idx           = i,
            section       = s.number,
            act_year      = s.act,
            chapter       = s.chapter_number,
            chapter_title = s.chapter_title,
            income_head   = s.income_head or "General / Definitions",
            section_title = s.title,
            raw_text      = text,
        ))
    return _BATCH_PROMPT_HEADER.format(
        n              = len(sections),
        sections_block = "\n".join(blocks),
    )


# ── Chunk builder from LLM output ─────────────────────────────────────────────

def _items_to_chunks(items: list[dict[str, Any]], section: Section) -> list[RagChunk]:
    act_year = section.act
    chunks: list[RagChunk] = []

    mapped_to: str | None = None
    if section.mapped_section:
        other     = "2025" if act_year == "1961" else "1961"
        mapped_to = f"{other}_S{section.mapped_section}"

    for idx, item in enumerate(items):
        sub_str    = str(item.get("subsection", "")).strip()
        clause_str = str(item.get("clause",    "")).strip()
        sub_num    = re.sub(r"[()]", "", sub_str)
        clause_id  = re.sub(r"[()]", "", clause_str)
        path       = _build_path(sub_num, clause_id) if sub_num else (f"s{idx}" if idx > 0 else "")

        content    = _clean(str(item.get("content",    ""))) or _clean(section.full_text[:400])
        clean_text = str(item.get("clean_text", "")).strip() or content
        conditions = [str(c) for c in item.get("conditions", []) if c]
        exceptions = [str(e) for e in item.get("exceptions", []) if e]
        keywords   = [str(k) for k in item.get("keywords",   []) if k] or _extract_keywords(content, section.title)
        references = [str(r) for r in item.get("references", []) if r] or [f"section {r}" for r in _extract_related_sections(content)]
        chunk_type = "exception" if exceptions else _classify_type(content)

        chunks.append(RagChunk(
            act_year      = act_year,
            chunk_id      = _make_id(act_year, section.number, path),
            chapter       = section.chapter_number,
            chapter_title = section.chapter_title,
            section       = section.number,
            section_title = section.title,
            subsection    = sub_str,
            clause        = clause_str,
            content       = content,
            clean_text    = clean_text,
            summary       = str(item.get("summary", "")).strip(),
            conditions    = conditions,
            exceptions    = exceptions,
            keywords      = keywords,
            references    = references,
            income_head   = section.income_head or "General / Definitions",
            clause_path   = path,
            chunk_type    = chunk_type,
            mapped_to     = mapped_to,
            page_start    = section.page_start,
            page_end      = section.page_end,
        ))

    return chunks


# ── Core: enrich a BATCH of sections in one LLM call ─────────────────────────

async def enrich_batch_async(
    sections: list[Section],
    config: LLMConfig,
    rate_limiter: GlobalRateLimiter | None = None,
    max_retries: int = 5,
    base_retry_delay: float = 3.0,
) -> dict[str, list[RagChunk]]:
    """
    Enrich multiple sections in ONE LLM call.
    Returns dict: section.number → list[RagChunk].

    Rate limiting:
      • Checks global rate limiter before every attempt.
      • On 429: notifies limiter (all concurrent calls will pause) then retries.
      • On 500: shorter global pause then retry.
      • Falls back section-by-section to heuristic after max_retries.
    """
    if rate_limiter is None:
        rate_limiter = GlobalRateLimiter()

    # Short sections skip LLM entirely (heuristic is fine for them)
    llm_sections  = [s for s in sections if len(s.full_text.strip()) >= _MIN_LLM_TEXT_LEN]
    skip_sections = [s for s in sections if len(s.full_text.strip()) < _MIN_LLM_TEXT_LEN]

    result: dict[str, list[RagChunk]] = {
        s.number: _heuristic_section(s) for s in skip_sections
    }

    if not llm_sections:
        return result

    prompt   = _build_batch_prompt(llm_sections)
    messages = [{"role": "user", "content": prompt}]

    # Cap max_tokens for enrichment — JSON responses are compact
    enrichment_config = config.model_copy(update={"max_tokens": 2048})
    provider = get_provider(enrichment_config)

    raw_response = ""
    for attempt in range(max_retries):
        # Wait out any global backoff window before firing
        await rate_limiter.wait()

        try:
            # For Ollama-based providers: disable thinking mode so models like
            # Gemma4/QwQ go straight to JSON output without chain-of-thought
            from ..rag.llm_provider import OllamaProvider
            if isinstance(provider, OllamaProvider):
                raw_response = await provider.chat(_SYSTEM_PROMPT, messages, think=False)
            else:
                raw_response = await provider.chat(_SYSTEM_PROMPT, messages)
            break   # success

        except Exception as e:
            err_str = str(e)
            is_429  = "429" in err_str
            is_500  = "500" in err_str

            if attempt < max_retries - 1:
                if is_429:
                    # Tell the shared limiter → all concurrent calls will pause
                    await rate_limiter.on_rate_limit()
                    # Personal backoff on top of global pause
                    personal_wait = base_retry_delay * (2 ** attempt)
                    _log.warning(
                        "Batch 429 (attempt %d/%d) — global pause + %.1fs personal backoff",
                        attempt + 1, max_retries, personal_wait,
                    )
                    await asyncio.sleep(personal_wait)
                elif is_500:
                    await rate_limiter.on_server_error()
                    personal_wait = base_retry_delay * (1.5 ** attempt)
                    _log.warning(
                        "Batch 500 (attempt %d/%d) — retrying in %.1fs",
                        attempt + 1, max_retries, personal_wait,
                    )
                    await asyncio.sleep(personal_wait)
                else:
                    # Other error — simple backoff
                    wait = base_retry_delay * (2 ** attempt)
                    _log.warning("Batch call failed (attempt %d/%d): %s — retrying in %.1fs",
                                 attempt + 1, max_retries, e, wait)
                    await asyncio.sleep(wait)
            else:
                _log.error(
                    "Batch call failed after %d retries — heuristic fallback for %d sections",
                    max_retries, len(llm_sections),
                )
                for s in llm_sections:
                    result[s.number] = _heuristic_section(s)
                return result

    # Parse the top-level array [{section, chunks}, ...]
    try:
        top = _extract_json_array(raw_response)
    except ValueError as e:
        _log.warning("Failed to parse batch JSON: %s — heuristic fallback", e)
        for s in llm_sections:
            result[s.number] = _heuristic_section(s)
        return result

    # Map section number → items
    sec_lookup: dict[str, list[dict[str, Any]]] = {}
    for entry in top:
        if not isinstance(entry, dict):
            continue
        sec_num    = str(entry.get("section", "")).strip()
        chunks_raw = entry.get("chunks", [])
        if isinstance(chunks_raw, list) and sec_num:
            sec_lookup[sec_num] = chunks_raw

    for s in llm_sections:
        items = sec_lookup.get(str(s.number), [])
        if items:
            try:
                chunks = _items_to_chunks(items, s)
                result[s.number] = chunks if chunks else _heuristic_section(s)
            except Exception as e:
                _log.warning("Chunk build failed for S%s: %s", s.number, e)
                result[s.number] = _heuristic_section(s)
        else:
            result[s.number] = _heuristic_section(s)

    return result


# ── Single-section wrappers (backward compat) ─────────────────────────────────

async def enrich_section_async(
    section: Section,
    config: LLMConfig,
    max_retries: int = 5,
    retry_delay: float = 3.0,
) -> list[RagChunk]:
    result = await enrich_batch_async([section], config, None, max_retries, retry_delay)
    return result.get(section.number, _heuristic_section(section))


def enrich_section(
    section: Section,
    config: LLMConfig,
    max_retries: int = 5,
    retry_delay: float = 3.0,
) -> list[RagChunk]:
    return asyncio.run(enrich_section_async(section, config, max_retries, retry_delay))
