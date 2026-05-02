"""
System prompt and context assembly for the RAG chat pipeline.

Builds the prompt with:
  - Role definition (CA-focused legal assistant)
  - Retrieved context chunks (clearly grouped by act, 2025 first)
  - Citation instructions
  - Query
"""

from __future__ import annotations
from typing import Any

SYSTEM_PROMPT = """You are ActInsight — an expert AI assistant for Indian Income Tax law, \
built specifically for Chartered Accountants and tax professionals.

## Current Year Context
- Current Financial Year: FY 2025-26 | Assessment Year: AY 2026-27
- Income Tax Act 2025 (ITA 2025) is NOW in force from FY 2025-26 onwards
- The new tax regime (Section 202, ITA 2025) is the DEFAULT regime for individuals from AY 2026-27
- Always frame rates, slabs, and examples for FY 2025-26 / AY 2026-27 unless the user specifies otherwise

## Authoritative Tax Slabs — New Regime (Section 202, ITA 2025) — AY 2026-27
These are the ONLY valid current slab rates. Never use slab rates from your training data.

| Total Income (₹)           | Tax Rate |
|----------------------------|----------|
| Up to ₹4,00,000            | Nil      |
| ₹4,00,001 – ₹8,00,000     | 5%       |
| ₹8,00,001 – ₹12,00,000    | 10%      |
| ₹12,00,001 – ₹16,00,000   | 15%      |
| ₹16,00,001 – ₹20,00,000   | 20%      |
| ₹20,00,001 – ₹24,00,000   | 25%      |
| Above ₹24,00,000           | 30%      |

CRITICAL: The old slabs (₹3L nil / ₹7L 5% / ₹10L 10% / ₹12.5L 15% / ₹15L 20%) are FY 2024-25 under the 1961 Act — NEVER present them as current. Never write "FY 2024-25" or "AY 2025-26" anywhere in your answer.

## Authoritative Rebate & Surcharge Facts — ITA 2025
- **Section 87A Rebate [ITA 2025]**: Full tax rebate if total income ≤ ₹12,00,000. Effective tax = ₹0 for income up to ₹12L under new regime. (Under old ITA 1961 it was ₹5L/₹7L — NEVER quote those as current.)
- **Standard Deduction [ITA 2025]**: ₹75,000 for salaried individuals and family pension recipients.
- **Surcharge** on income above ₹50L: 10% | above ₹1Cr: 15% | above ₹2Cr: 25% | above ₹5Cr: 25% (capped at 25% under new regime, no 37% surcharge).
- **Health & Education Cess**: 4% on income tax + surcharge.

## How to Answer

**PRIORITY RULE for cross-act queries:**
When both ITA 1961 and ITA 2025 sections are retrieved, ALWAYS lead with the ITA 2025 answer since it is the CURRENT applicable law (FY 2025-26 onwards). Then provide ITA 1961 for historical comparison if relevant.

**Structure every answer as:**
1. **Direct answer** — 1–2 sentences stating the rule or rate clearly, with the ITA 2025 section number
2. **Section citations** — cite exact provision numbers, e.g. "Section 393(2)(b) [ITA 2025]" or "Section 194C(1) [ITA 1961]". ALWAYS include the Act year in brackets.
3. **Rate / Threshold table** — for TDS/rate questions, always present a Markdown table with: Recipient Type | Rate | Threshold
4. **Key conditions & exceptions** — provisos, exceptions, Explanations, or thresholds that modify the rule
5. **Cross-Act comparison** — if both acts cover the topic, show a brief comparison table: Provision | ITA 1961 | ITA 2025

**For comparisons (1961 Act vs 2025 Act):** Always produce a Markdown comparison table with columns: Provision | ITA 1961 | ITA 2025 | Key Change.

**For computation questions:** Show step-by-step calculation with section references at each step.

**Tone:** Precise, detailed legal language. CAs need complete information with all conditions, thresholds, and exceptions — not brief summaries. Provide comprehensive answers covering all sub-clauses and provisos from the retrieved context.

## Citations Format
- Single Act: "Section 80D(2)(a) [ITA 1961]"
- Cross-Act reference: "Section 393 [ITA 2025] (formerly Section 194C [ITA 1961])"
- Subsection: "Section 44AD(1) proviso [ITA 2025]"

## Constraints
- Answer ONLY from the retrieved context sections provided below
- READ ALL retrieved sections carefully — do not skip ITA 2025 sections even if they appear different from what you expect
- If the context contains ITA 2025 sections with rates/provisions, CITE THEM. Do not say "not explicitly stated" if the information is present in the context.
- If context is insufficient: state "The retrieved sections do not directly address [X]. Relevant chapter: [Y]. Recommend consulting [section range]."
- NEVER fabricate section numbers, rates, thresholds, or provisions not in the context
- NEVER derive ITA 2025 rates from amendment annotations inside ITA 1961 chunks (e.g. "Sub. by Act No. 7 of 2025" inside a 1961 section does NOT give you valid ITA 2025 rates — only sections explicitly marked "ITA 2025 ← CURRENT LAW" are authoritative for 2025)
- NEVER give a definitive professional opinion on specific client facts — recommend a practicing CA for complex matters
- NEVER use "FY 2024-25", "AY 2025-26", or old 115BAC slab rates
- Do NOT start your response with filler phrases like "Of course", "Certainly", "Sure", or "Based on the provided context"
"""


def _format_chunk(chunk: dict[str, Any], idx: int, highlight_act: str | None = None) -> str:
    """Format a single retrieved chunk for the prompt context."""
    chunk_type = chunk.get("chunk_type", chunk.get("type", ""))

    # Web search result — different format
    if chunk_type == "web" or chunk.get("act_year") == "web":
        title = chunk.get("section_title", "Web Result")
        url = chunk.get("url", "")
        text = chunk.get("text", "")
        lines = [
            f"[{idx}] [WEB SOURCE] {title}",
            f"URL: {url}" if url else "",
            "---",
            text[:800],  # cap web snippets
        ]
        return "\n".join(l for l in lines if l)

    sec = chunk.get("section", "?")
    act = chunk.get("act_year", "?")
    title = chunk.get("section_title", "")
    head = chunk.get("income_head", "")
    chapter = chunk.get("chapter_title", "")
    text = chunk.get("text", "")
    reranker_score = chunk.get("reranker_score", chunk.get("score", 0))

    # Mark current law clearly
    act_label = f"ITA {act}"
    if act == "2025":
        act_label = "ITA 2025 ← CURRENT LAW (FY 2025-26)"
    elif act == "1961":
        act_label = "ITA 1961 (historical reference)"

    ref = f"Section {sec} [{act_label}]"
    if title:
        ref += f" — {title}"
    if head:
        ref += f"\nHead: {head}"
    if chapter:
        ref += f" | Chapter: {chapter}"

    lines = [
        f"[{idx}] {ref}",
        "---",
        text,
    ]
    return "\n".join(lines)


def build_context_prompt(
    query: str,
    chunks: list[dict[str, Any]],
    chat_history: list[dict[str, str]] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """
    Build the full message list for the LLM.

    Groups chunks by act (2025 first) so the LLM sees current-law
    sections before historical ones.

    Returns:
        (system_prompt, messages)
    """
    if chunks:
        # Separate chunks by act for clear grouping
        chunks_2025 = [c for c in chunks if c.get("act_year") == "2025"]
        chunks_1961 = [c for c in chunks if c.get("act_year") == "1961"]
        chunks_web  = [c for c in chunks if c.get("act_year") == "web" or c.get("chunk_type") == "web"]
        chunks_other = [c for c in chunks if c not in chunks_2025 + chunks_1961 + chunks_web]

        parts: list[str] = []
        idx = 1

        # 2025 Act first (current law)
        if chunks_2025:
            parts.append("### ═══ ITA 2025 SECTIONS (CURRENT LAW — FY 2025-26 onwards) ═══")
            for c in chunks_2025:
                parts.append(_format_chunk(c, idx))
                idx += 1

        # 1961 Act second (historical)
        if chunks_1961:
            parts.append("\n### ═══ ITA 1961 SECTIONS (Historical reference only) ═══")
            for c in chunks_1961:
                parts.append(_format_chunk(c, idx))
                idx += 1

        # Other / web
        for c in chunks_other + chunks_web:
            parts.append(_format_chunk(c, idx))
            idx += 1

        context_block = "\n\n".join(parts)

        # Add summary of what was retrieved
        summary_parts = []
        if chunks_2025:
            summary_parts.append(f"{len(chunks_2025)} sections from ITA 2025")
        if chunks_1961:
            summary_parts.append(f"{len(chunks_1961)} sections from ITA 1961")
        if chunks_web:
            summary_parts.append(f"{len(chunks_web)} web sources")
        summary = " | ".join(summary_parts)

        context_section = (
            f"## Retrieved Legal Context ({summary})\n\n"
            f"INSTRUCTION: ITA 2025 sections are the CURRENT applicable law. "
            f"Read all sections carefully before answering.\n\n"
            f"{context_block}"
        )
    else:
        context_section = "## Retrieved Sections\n\n(No relevant sections found in the database.)"

    # Build user message with context embedded
    user_message = f"{context_section}\n\n## Question\n\n{query}"

    messages: list[dict[str, str]] = []

    # Add chat history (last 5 turns for context)
    if chat_history:
        for turn in chat_history[-10:]:  # 5 user+assistant pairs
            messages.append(turn)

    messages.append({"role": "user", "content": user_message})

    return SYSTEM_PROMPT, messages


def build_comparison_prompt(
    source_section: str,
    source_act: str,
    source_title: str,
    source_text: str,
    equiv_section: str,
    equiv_act: str,
    equiv_title: str,
    equiv_text: str,
) -> tuple[str, list[dict[str, str]]]:
    """Build a prompt to compare two corresponding sections across the two Acts."""
    system = (
        "You are an expert in Indian Income Tax law comparing provisions across the Income Tax Act 1961 and 2025. "
        "Analyze the two sections provided and produce a structured comparison. "
        "Be precise: cite exact amounts, rates, and thresholds. "
        "Tag each change as one of: ADDED | REMOVED | MODIFIED | RENAMED | RESTRUCTURED. "
        "CRITICAL INSTRUCTION: Output ONLY the structured comparison below. No preamble, no closing remarks."
    )
    user = (
        f"## Section {source_section} [ITA {source_act}] — {source_title}\n\n"
        f"{source_text[:2000]}\n\n"
        f"---\n\n"
        f"## Section {equiv_section} [ITA {equiv_act}] — {equiv_title}\n\n"
        f"{equiv_text[:2000]}\n\n"
        "Produce a comparison in exactly this format:\n\n"
        "## Summary\n"
        "[One sentence: what both sections are about]\n\n"
        "## Key Changes\n"
        "- [TAG]: [Specific change with exact amounts/rates/conditions]\n"
        "- [TAG]: ...\n\n"
        "## Practical Impact for CAs\n"
        "[2–3 sentences on the most important compliance/planning implications]\n\n"
        "## Verdict\n"
        "[EQUIVALENT | PARTIALLY_EQUIVALENT | RENAMED_ONLY | NO_EQUIVALENT] — [one-line justification]"
    )
    return system, [{"role": "user", "content": user}]


def build_section_summary_prompt(section_text: str, section_ref: str) -> tuple[str, list[dict[str, str]]]:
    """Build a prompt to generate a concise section summary."""
    system = (
        "You are an expert in Indian Income Tax law. "
        "Summarize the given section concisely suitable for a CA's quick reference. "
        "Focus on: who it applies to, what it provides, key conditions, and any monetary limits. "
        "CRITICAL INSTRUCTION: Output ONLY the requested summary. "
        "Do NOT use conversational filler like 'Of course', 'Here is a summary', or 'Sure'."
    )
    messages = [{
        "role": "user",
        "content": (
            f"Summarize {section_ref} from the Income Tax Act:\n\n{section_text}"
        ),
    }]
    return system, messages


def build_example_prompt(section_text: str, section_ref: str) -> tuple[str, list[dict[str, str]]]:
    """Build a prompt to generate practical examples for a section."""
    system = (
        "You are an expert in Indian Income Tax law. "
        "Generate 2 practical examples illustrating the application of the given section. "
        "Use Indian names (Raj, Priya, Arun, etc.), INR amounts, and AY 2026-27 (FY 2025-26) as the assessment year. "
        "Keep each example under 5 sentences."
    )
    messages = [{
        "role": "user",
        "content": (
            f"Generate 2 practical examples for {section_ref}:\n\n{section_text}"
        ),
    }]
    return system, messages
