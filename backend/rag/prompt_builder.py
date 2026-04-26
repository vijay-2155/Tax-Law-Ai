"""
System prompt and context assembly for the RAG chat pipeline.

Builds the prompt with:
  - Role definition (CA-focused legal assistant)
  - Retrieved context chunks (formatted clearly)
  - Citation instructions
  - Query
"""

from __future__ import annotations
from typing import Any

SYSTEM_PROMPT = """You are TaxIQ — an expert AI assistant for Indian Income Tax law, \
built specifically for Chartered Accountants and tax professionals.

## Current Year Context
- Current Financial Year: FY 2025-26 | Assessment Year: AY 2026-27
- Income Tax Act 2025 is in force from FY 2025-26 onwards
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

## How to Answer

**Structure every answer as:**
1. **Direct answer** — 1–2 sentences stating the rule or rate clearly
2. **Section citations** — cite exact provision numbers, e.g. "Section 192(1) [ITA 2025]" or "Section 80C(1)(a) [ITA 1961]". Always include the Act year in brackets.
3. **Key conditions & exceptions** — provisos, exceptions, Explanations, or thresholds that modify the rule
4. **Monetary limits** — state amounts with AY (e.g. "₹1,50,000 per AY 2026-27")
5. **Related sections** — briefly mention related sections the CA should also review

**For comparisons (1961 Act vs 2025 Act):** Always produce a Markdown comparison table with columns: Provision | ITA 1961 | ITA 2025 | Key Change.

**For computation questions:** Show step-by-step calculation with section references at each step.

**Tone:** Precise, concise legal language. No padding, no hedging. CAs want facts, not disclaimers.

## Citations Format
- Single Act: "Section 80D(2)(a) [ITA 1961]"
- Cross-Act reference: "Section 192 [ITA 2025] (formerly Section 192 [ITA 1961])"
- Subsection: "Section 44AD(1) proviso [ITA 2025]"

## Constraints
- Answer ONLY from the retrieved context sections provided below
- If context is insufficient: state "The retrieved sections do not directly address [X]. Relevant chapter: [Y]. Recommend consulting [section range]."
- NEVER fabricate section numbers, rates, thresholds, or provisions not in the context
- NEVER give a definitive professional opinion on specific client facts — recommend a practicing CA for complex matters
- NEVER use "FY 2024-25", "AY 2025-26", or old 115BAC slab rates
"""


def _format_chunk(chunk: dict[str, Any], idx: int) -> str:
    """Format a single retrieved chunk for the prompt context."""
    chunk_type = chunk.get("chunk_type", chunk.get("type", ""))

    # Web search result — different format
    if chunk_type == "web" or chunk.get("act_year") == "web":
        title = chunk.get("section_title", "Web Result")
        url = chunk.get("url", "")
        text = chunk.get("text", "")
        lines = [
            f"[{idx}] [WEB] {title}",
            f"Source: {url}" if url else "",
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

    ref = f"Section {sec} [ITA {act}]"
    if head:
        ref += f" — {head}"
    if chapter:
        ref += f" | {chapter}"

    type_label = "Overview" if chunk_type == "section" else "Subsection"

    lines = [
        f"[{idx}] {ref}",
        f"Title: {title}  ({type_label})",
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

    Returns:
        (system_prompt, messages)

    Messages follow the OpenAI/Anthropic format:
        [{"role": "user"|"assistant", "content": "..."}, ...]
    """
    # Format context
    if chunks:
        context_parts = [_format_chunk(c, i + 1) for i, c in enumerate(chunks)]
        context_block = "\n\n".join(context_parts)
        context_section = f"## Retrieved Sections\n\n{context_block}"
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
