"""
LangGraph-based agentic RAG pipeline for Income Tax Act queries.

Graph nodes:
  route_question    → decide: exact_lookup | semantic_search | cross_act_search
  retrieve          → vector / exact section lookup
  grade_documents   → LLM-grades whether retrieved chunks are relevant
  rewrite_query     → rephrase question if docs were irrelevant
  generate          → stream final answer with citations

Edges:
  START → route_question
  route_question → retrieve  (all paths; routing sets search_strategy in state)
  retrieve → grade_documents
  grade_documents → generate          (if relevant)
                  → rewrite_query     (if not relevant, max 2 retries)
  rewrite_query → retrieve
  generate → END

State carries: question, act_year, chunks, generation, search_strategy, retries
"""

from __future__ import annotations

import re
import json
from typing import Annotated, Any, AsyncIterator, Literal
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from ..indexing.qdrant_store import QdrantStore
from ..indexing.embedder import embed_query
from .retriever import Retriever, _extract_section_number, _infer_income_head
from .prompt_builder import build_context_prompt, SYSTEM_PROMPT
from .llm_provider import LLMConfig, get_provider
from .web_search import web_search_tax, web_results_to_chunks

# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class RAGState(TypedDict):
    question: str
    act_year: str                        # "1961" | "2025" | "both"
    search_strategy: str                 # "exact" | "semantic" | "cross_act"
    chunks: list[dict[str, Any]]         # retrieved + graded chunks
    generation: str                      # final answer text
    sources: list[dict[str, Any]]        # deduplicated citations
    retries: int                         # rewrite retry counter
    chat_history: list[dict[str, str]]   # prior conversation turns


MAX_RETRIES = 2

# ---------------------------------------------------------------------------
# Helper: call LLM without streaming (for grading / routing)
# ---------------------------------------------------------------------------

async def _llm_call(system: str, user: str, config: LLMConfig) -> str:
    provider = get_provider(config)
    return await provider.chat(system, [{"role": "user", "content": user}])


# ---------------------------------------------------------------------------
# Node 1: Route question
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"\b(?:section|sec\.?|§)\s*\d{1,3}[A-Z]{0,5}\b", re.I)
_CROSS_ACT_TRIGGERS = re.compile(
    r"\b(compare|difference|1961\s+(vs|versus|and)\s+2025|"
    r"2025\s+(vs|versus|and)\s+1961|both acts?|old act|new act)\b",
    re.I,
)


def route_question(state: RAGState) -> RAGState:
    """
    Determine search strategy without LLM call (pure pattern matching — fast).
    Sets state['search_strategy'].
    """
    q = state["question"]

    if _CROSS_ACT_TRIGGERS.search(q):
        strategy = "cross_act"
    elif _SECTION_RE.search(q):
        strategy = "exact"
    else:
        strategy = "semantic"

    return {**state, "search_strategy": strategy}


# ---------------------------------------------------------------------------
# Node 2: Retrieve
# ---------------------------------------------------------------------------

def retrieve(state: RAGState, *, store: QdrantStore) -> RAGState:
    """Retrieve relevant chunks based on search_strategy."""
    retriever = Retriever(store)
    q = state["question"]
    strategy = state["search_strategy"]
    act_year = state["act_year"]

    if strategy == "exact":
        sec_num = _extract_section_number(q)
        if sec_num:
            if act_year == "both":
                chunks = []
                for yr in ["2025", "1961"]:
                    chunks.extend(store.search_by_section(sec_num, yr))
            else:
                chunks = store.search_by_section(sec_num, act_year)
                # Fallback: if section not found in selected act, try the other act
                # (e.g. Section 80C only exists in 1961 Act, not 2025 Act)
                if not chunks:
                    other_year = "1961" if act_year == "2025" else "2025"
                    chunks = store.search_by_section(sec_num, other_year)
                # Still nothing? Fall back to semantic search across both acts
                if not chunks:
                    qv = embed_query(q)
                    chunks = store.search_both_acts(qv, top_k=10)
        else:
            # Fallback to semantic if no section number extracted
            chunks = retriever.retrieve(q, act_year=None if act_year == "both" else act_year, top_k=10)

    elif strategy == "cross_act":
        qv = embed_query(q)
        head = _infer_income_head(q)
        chunks = store.search_both_acts(qv, top_k=10, income_head=head)

    else:  # semantic
        chunks = retriever.retrieve(
            q,
            act_year=None if act_year == "both" else act_year,
            top_k=10,
        )

    return {**state, "chunks": chunks}


# ---------------------------------------------------------------------------
# Node 3: Grade documents
# ---------------------------------------------------------------------------

_GRADE_SYSTEM = (
    "You are a relevance grader for an Indian Income Tax legal database. "
    "Assess whether the retrieved legal text chunks contain information that would help answer the user's tax question. "
    "Be lenient: if ANY chunk mentions the topic, section, rate, or concept being asked about — even partially — mark as relevant. "
    "Only mark irrelevant if the chunks are completely unrelated to the question topic. "
    "Reply with ONLY valid JSON: {\"relevant\": true} or {\"relevant\": false}. No other text."
)


async def grade_documents(state: RAGState, *, config: LLMConfig) -> RAGState:
    """Grade retrieved chunks for relevance using LLM. Fast, single call."""
    chunks = state["chunks"]
    if not chunks:
        return {**state}

    # Build a short snippet of chunk texts for grading
    snippet = "\n---\n".join(
        f"[{i+1}] {c.get('text', '')[:200]}" for i, c in enumerate(chunks[:5])
    )
    user_msg = (
        f"Question: {state['question']}\n\n"
        f"Retrieved chunks:\n{snippet}\n\n"
        "Are these chunks relevant to the question?"
    )

    try:
        raw = await _llm_call(_GRADE_SYSTEM, user_msg, config)
        # Strip <think>...</think> blocks produced by reasoning models (DeepSeek, GLM, etc.)
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()
        # Also handle bare ---thinking--- style separators used by some models
        raw = re.sub(r"^.*?---+\s*\n", "", raw, flags=re.DOTALL).strip()
        # Extract JSON from remaining response
        m = re.search(r'\{[^}]+\}', raw)
        if m:
            result = json.loads(m.group(0))
            relevant = result.get("relevant", True)
        else:
            relevant = True  # default to relevant if parsing fails
    except Exception:
        relevant = True  # fail open

    return {**state, "chunks": chunks if relevant else []}


# ---------------------------------------------------------------------------
# Node 4: Rewrite query
# ---------------------------------------------------------------------------

_REWRITE_SYSTEM = (
    "You are a query rewriter for an Indian Income Tax legal search engine. "
    "The user's question failed to retrieve relevant sections from the database. "
    "Rewrite it using precise Indian tax law terminology: "
    "use official chapter names (e.g. 'TDS', 'capital gains', 'deductions under Chapter VI-A'), "
    "section numbers if implied, and statutory language from the Income Tax Act. "
    "Make the rewritten query shorter and more targeted. "
    "Return ONLY the rewritten question. No explanation, no preamble."
)


async def rewrite_query(state: RAGState, *, config: LLMConfig) -> RAGState:
    """Rewrite the query if documents were not relevant."""
    user_msg = f"Original question: {state['question']}\n\nRewrite this question to better match Indian tax law terminology."
    try:
        new_q = await _llm_call(_REWRITE_SYSTEM, user_msg, config)
        # Strip think blocks from reasoning models
        new_q = re.sub(r"<think>[\s\S]*?</think>", "", new_q, flags=re.IGNORECASE).strip()
        new_q = new_q.strip().strip('"').strip("'")
    except Exception:
        new_q = state["question"]  # keep original on failure

    return {
        **state,
        "question": new_q,
        "retries": state.get("retries", 0) + 1,
        "search_strategy": "semantic",  # always do semantic on rewrite
    }


# ---------------------------------------------------------------------------
# Node 5: Generate answer
# ---------------------------------------------------------------------------

async def generate(state: RAGState, *, config: LLMConfig) -> RAGState:
    """Generate final answer (non-streaming) and build source list."""
    system, messages = build_context_prompt(
        state["question"],
        state["chunks"],
        chat_history=state.get("chat_history"),
    )

    provider = get_provider(config)
    answer = await provider.chat(system, messages)

    # Deduplicate sources
    seen: set[str] = set()
    sources: list[dict[str, Any]] = []
    for c in state["chunks"]:
        key = f"{c.get('act_year')}_{c.get('section')}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "section": c.get("section"),
                "section_title": c.get("section_title"),
                "act_year": c.get("act_year"),
                "income_head": c.get("income_head"),
                "chunk_type": c.get("chunk_type"),
                "page_start": c.get("page_start"),
                "score": round(c.get("score", 1.0), 3),
            })

    return {**state, "generation": answer, "sources": sources}


# ---------------------------------------------------------------------------
# Conditional edge: after grade → generate or rewrite?
# ---------------------------------------------------------------------------

def decide_after_grade(state: RAGState) -> Literal["generate", "rewrite_query"]:
    if state.get("chunks"):
        return "generate"
    if state.get("retries", 0) >= MAX_RETRIES:
        return "generate"  # give up and answer with empty context
    return "rewrite_query"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_rag_graph(store: QdrantStore, config: LLMConfig) -> Any:
    """
    Compile and return the LangGraph runnable.

    Usage:
        graph = build_rag_graph(store, config)
        result = await graph.ainvoke({
            "question": "What is TDS rate for contractors?",
            "act_year": "2025",
            "chat_history": [],
            "retries": 0,
            "chunks": [],
            "search_strategy": "",
            "generation": "",
            "sources": [],
        })
        print(result["generation"])
        print(result["sources"])
    """
    builder = StateGraph(RAGState)

    # Register nodes (bind store/config via closures)
    builder.add_node("route_question", route_question)
    builder.add_node("retrieve", lambda s: retrieve(s, store=store))
    builder.add_node("grade_documents", lambda s: _run_async(grade_documents(s, config=config)))
    builder.add_node("rewrite_query", lambda s: _run_async(rewrite_query(s, config=config)))
    builder.add_node("generate", lambda s: _run_async(generate(s, config=config)))

    # Edges
    builder.add_edge(START, "route_question")
    builder.add_edge("route_question", "retrieve")
    builder.add_edge("retrieve", "grade_documents")
    builder.add_conditional_edges(
        "grade_documents",
        decide_after_grade,
        {"generate": "generate", "rewrite_query": "rewrite_query"},
    )
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("generate", END)

    return builder.compile()


def build_async_rag_graph(store: QdrantStore, config: LLMConfig) -> Any:
    """
    Async version of the RAG graph. All nodes are properly async.
    This is the preferred version for FastAPI usage.
    """
    from langgraph.graph import StateGraph, START, END
    import asyncio

    builder = StateGraph(RAGState)

    builder.add_node("route_question", route_question)
    builder.add_node("retrieve", lambda s: retrieve(s, store=store))

    async def _grade(s):
        return await grade_documents(s, config=config)

    async def _rewrite(s):
        return await rewrite_query(s, config=config)

    async def _generate(s):
        return await generate(s, config=config)

    builder.add_node("grade_documents", _grade)
    builder.add_node("rewrite_query", _rewrite)
    builder.add_node("generate", _generate)

    builder.add_edge(START, "route_question")
    builder.add_edge("route_question", "retrieve")
    builder.add_edge("retrieve", "grade_documents")
    builder.add_conditional_edges(
        "grade_documents",
        decide_after_grade,
        {"generate": "generate", "rewrite_query": "rewrite_query"},
    )
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("generate", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Streaming wrapper (for SSE)
# ---------------------------------------------------------------------------

async def stream_rag_response(
    question: str,
    store: QdrantStore,
    config: LLMConfig,
    act_year: str = "2025",
    chat_history: list[dict[str, str]] | None = None,
    top_k: int = 8,
) -> AsyncIterator[str]:
    """
    Streaming wrapper: runs retrieval + grading synchronously, then streams generation.

    Yields:
      - Plain text tokens from LLM
      - Final JSON: {"done": true, "sources": [...], "rewritten_question": "..."}
    """
    q = question

    # Step 0: Condense question if we have chat history
    if chat_history:
        history_text = "\n".join(f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history[-6:])
        condense_sys = (
            "You are a query condenser for an Indian Income Tax legal assistant. "
            "Given a conversation history and a follow-up question, rewrite the follow-up as a fully self-contained question. "
            "Resolve pronouns (it, this, that, the section, the rate) by substituting the actual referenced section number, provision, or concept from history. "
            "Preserve all tax-specific details: section numbers, act year, income head, monetary amounts. "
            "If the follow-up is already fully self-contained, return it unchanged. "
            "Return ONLY the standalone question. No explanation."
        )
        condense_user = f"Chat History:\n{history_text}\n\nFollow Up Question: {q}\n\nStandalone question:"
        try:
            condensed = await _llm_call(condense_sys, condense_user, config)
            condensed = re.sub(r"<think>[\s\S]*?</think>", "", condensed, flags=re.IGNORECASE).strip()
            condensed = condensed.strip().strip('"').strip("'")
            if condensed:
                q = condensed
                print(f"[RAG] Condensing query using history -> {q!r}", flush=True)
        except Exception as e:
            print(f"[RAG] Condensation failed: {e}", flush=True)

    # Step 1-3: retrieve + grade (non-streaming)
    retriever = Retriever(store)


    # Route
    if _CROSS_ACT_TRIGGERS.search(q):
        strategy = "cross_act"
    elif _SECTION_RE.search(q):
        strategy = "exact"
    else:
        strategy = "semantic"

    print(f"[RAG] question={q[:80]!r}  act_year={act_year!r}  strategy={strategy!r}", flush=True)

    # Retrieve
    for attempt in range(MAX_RETRIES + 1):
        if strategy == "exact":
            sec_num = _extract_section_number(q)
            if sec_num:
                if act_year == "both":
                    chunks: list[dict] = []
                    for yr in ["2025", "1961"]:
                        chunks.extend(store.search_by_section(sec_num, yr))
                else:
                    chunks = store.search_by_section(sec_num, act_year)
                    # Fallback: if section not found in selected act, try the other act
                    # (e.g. Section 80C only exists in 1961 Act, not 2025 Act)
                    if not chunks:
                        other_year = "1961" if act_year == "2025" else "2025"
                        chunks = store.search_by_section(sec_num, other_year)
                    # Still nothing? Fall back to semantic search across both acts
                    if not chunks:
                        qv = embed_query(q)
                        chunks = store.search_both_acts(qv, top_k=top_k)
            else:
                chunks = retriever.retrieve(q, act_year=None if act_year == "both" else act_year, top_k=top_k)
            chunks = retriever._inject_sec202_if_needed(q, chunks)
        elif strategy == "cross_act":
            qv = embed_query(q)
            head = _infer_income_head(q)
            chunks = store.search_both_acts(qv, top_k=top_k, income_head=head)
            chunks = retriever._inject_sec202_if_needed(q, chunks)
        else:
            chunks = retriever.retrieve(q, act_year=None if act_year == "both" else act_year, top_k=top_k)

        print(f"[RAG] attempt={attempt} strategy={strategy!r} → {len(chunks)} chunks retrieved", flush=True)

        # Grade (only on first semantic attempt, skip for exact if we have chunks)
        if strategy != "exact" and attempt < MAX_RETRIES:
            snippet = "\n---\n".join(
                f"[{i+1}] {c.get('text', '')[:200]}" for i, c in enumerate(chunks[:4])
            )
            grade_user = (
                f"Question: {q}\n\nChunks:\n{snippet}\n\nAre these relevant?"
            )
            try:
                grade_raw = await _llm_call(_GRADE_SYSTEM, grade_user, config)
                # Strip <think>...</think> blocks from reasoning models
                grade_raw = re.sub(r"<think>[\s\S]*?</think>", "", grade_raw, flags=re.IGNORECASE).strip()
                m = re.search(r'\{[^}]+\}', grade_raw)
                relevant = json.loads(m.group(0)).get("relevant", True) if m else True
            except Exception:
                relevant = True

            if relevant or attempt >= MAX_RETRIES:
                print(f"[RAG] grade=relevant={relevant} → {'generating' if relevant else 'rewriting'}", flush=True)
                break

            # Rewrite and retry
            try:
                rewrite_raw = await _llm_call(
                    _REWRITE_SYSTEM,
                    f"Original question: {q}\n\nRewrite for better tax law search.",
                    config,
                )
                # Strip think blocks from reasoning model rewrite response
                rewrite_raw = re.sub(r"<think>[\s\S]*?</think>", "", rewrite_raw, flags=re.IGNORECASE).strip()
                q = rewrite_raw.strip().strip('"').strip("'")
            except Exception:
                break
            strategy = "semantic"
        else:
            break

    # Step 3.5: Web search — always supplement with live results for recency/circulars
    web_chunks: list[dict] = []
    try:
        web_results = await web_search_tax(q, max_results=4)
        web_chunks = web_results_to_chunks(web_results)
        print(f"[RAG] web search returned {len(web_chunks)} results", flush=True)
    except Exception as e:
        print(f"[RAG] web search failed: {e}", flush=True)

    all_chunks = chunks + web_chunks

    # Step 4: Stream generation
    print(
        f"[RAG] generating answer | chunks={len(all_chunks)} (rag={len(chunks)}, web={len(web_chunks)}) | "
        f"provider={config.provider} | model={config.model} | "
        f"context={'YES (RAG-grounded)' if chunks else ('WEB-ONLY' if web_chunks else 'NO CONTEXT')}",
        flush=True,
    )
    system, messages = build_context_prompt(q, all_chunks, chat_history=chat_history)
    provider = get_provider(config)

    # Stream tokens while post-processing for stale FY references and stripping think blocks.
    _STALE_FY_RE = re.compile(
        r"\b(FY\s*2024[-–]25|AY\s*2025[-–]26|Financial\s*Year\s*2024[-–]25|"
        r"Assessment\s*Year\s*2025[-–]26)\b",
        re.IGNORECASE,
    )
    # Matches a complete <think>...</think> block (including partial close tags in buffer)
    _THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
    # Detects an *open* <think> that hasn't been closed yet (so we can buffer)
    _THINK_OPEN_RE  = re.compile(r"<think>", re.IGNORECASE)
    _THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)

    accumulated = ""
    think_buffer = ""   # accumulates text while inside a <think> block
    in_think = False

    async for token in provider.chat_stream(system, messages):
        accumulated += token

        if in_think:
            # We are inside a <think> block — keep buffering
            think_buffer += token
            if _THINK_CLOSE_RE.search(think_buffer):
                # Closing tag arrived — discard the whole block, resume normal streaming
                # Emit any text that came *after* </think> in the same chunk
                after = _THINK_CLOSE_RE.split(think_buffer, maxsplit=1)[-1]
                think_buffer = ""
                in_think = False
                if after:
                    yield after
            # else: still buffering inside think block — yield nothing
        else:
            if _THINK_OPEN_RE.search(token):
                # A <think> opened — split on it: emit text before, buffer the rest
                parts = _THINK_OPEN_RE.split(token, maxsplit=1)
                before = parts[0]
                rest   = parts[1] if len(parts) > 1 else ""
                if before:
                    yield before
                # Check if the same token also closes the block
                if _THINK_CLOSE_RE.search(rest):
                    after = _THINK_CLOSE_RE.split(rest, maxsplit=1)[-1]
                    if after:
                        yield after
                else:
                    in_think = True
                    think_buffer = rest
            else:
                yield token

    # After stream ends, warn if stale FY slipped through
    if _STALE_FY_RE.search(accumulated):
        print(
            "[RAG] WARNING: model generated stale FY 2024-25 reference despite instructions.",
            flush=True,
        )

    # Final sources — law chunks deduplicated + web chunks
    seen: set[str] = set()
    sources: list[dict] = []
    for c in chunks:
        key = f"{c.get('act_year')}_{c.get('section')}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "section": c.get("section"),
                "section_title": c.get("section_title"),
                "act_year": c.get("act_year"),
                "income_head": c.get("income_head"),
                "chunk_type": c.get("chunk_type"),
                "score": round(c.get("score", 1.0), 3),
            })
    for c in web_chunks:
        sources.append({
            "section": None,
            "section_title": c.get("section_title"),
            "act_year": "web",
            "income_head": "",
            "chunk_type": "web",
            "url": c.get("url", ""),
            "score": 0.0,
        })

    rewritten = q if q != question else None
    yield "\n\n" + json.dumps({
        "done": True,
        "sources": sources,
        "rewritten_question": rewritten,
    })


def _run_async(coro):
    """Run async coroutine in sync context (for sync LangGraph nodes)."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
