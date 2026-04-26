#!/usr/bin/env python3
"""
RAG quality test suite.

Tests: section lookup, income-head filtering, semantic retrieval,
       definition queries, slab-rate injection, cross-act search.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.indexing.qdrant_store import QdrantStore
from backend.rag.retriever import Retriever

store = QdrantStore()
r = Retriever(store)

PASS = "✓"
FAIL = "✗"
WARN = "~"

results: list[tuple[str, str, str]] = []   # (status, test_name, detail)


def check(name, chunks, *, min_chunks=1, expect_section=None,
          expect_head=None, expect_act=None, expect_text=None):
    if not chunks:
        results.append((FAIL, name, "returned 0 chunks"))
        return

    hits = len(chunks)
    detail_parts = [f"{hits} chunks"]

    # Section check
    if expect_section:
        matched = [c for c in chunks if str(c.get("section")) == str(expect_section)]
        if matched:
            detail_parts.append(f"section {expect_section} ✓")
        else:
            got = [c.get("section") for c in chunks[:3]]
            results.append((FAIL, name, f"expected section {expect_section}, got {got}"))
            return

    # Income head check
    if expect_head:
        heads = [c.get("income_head", "") for c in chunks[:3]]
        if any(expect_head.lower() in h.lower() for h in heads):
            detail_parts.append(f"head={expect_head} ✓")
        else:
            results.append((WARN, name, f"expected head '{expect_head}', got {heads[:2]}"))
            return

    # Act year check
    if expect_act:
        acts = [str(c.get("act_year", "")) for c in chunks[:3]]
        if any(expect_act in a for a in acts):
            detail_parts.append(f"act={expect_act} ✓")
        else:
            results.append((WARN, name, f"expected act {expect_act}, got {acts}"))
            return

    # Text keyword check
    if expect_text:
        combined = " ".join(c.get("text", "") or "" for c in chunks[:5]).lower()
        if expect_text.lower() in combined:
            detail_parts.append(f"'{expect_text}' found ✓")
        else:
            results.append((WARN, name, f"'{expect_text}' not found in top-5 chunks"))
            return

    if hits < min_chunks:
        results.append((WARN, name, f"only {hits} chunks (expected ≥{min_chunks})"))
    else:
        results.append((PASS, name, " | ".join(detail_parts)))


print("=" * 65)
print("RAG Quality Test Suite")
print("=" * 65)

# ── 1. Collection health ───────────────────────────────────────────────────────
print("\n[1] Collection health")
for yr in ("2025", "1961"):
    exists = store.collection_exists(yr)
    count  = store.collection_point_count(yr) if exists else 0
    status = PASS if (exists and count > 100) else FAIL
    results.append((status, f"collection tax_{yr}", f"exists={exists}, points={count:,}"))
    print(f"  tax_{yr}: {count:,} points")

# ── 2. Exact section lookup ────────────────────────────────────────────────────
print("\n[2] Exact section lookup (2025)")
chunks = r.retrieve_section("15", "2025")
check("Section 15 (Salaries head)", chunks, expect_section="15", expect_head="Salaries")

chunks = r.retrieve_section("202", "2025")
check("Section 202 (Tax rates/slabs)", chunks, expect_section="202")

chunks = r.retrieve_section("67", "2025")
check("Section 67 (Capital Gains)", chunks, expect_section="67", expect_head="Capital Gains")

chunks = r.retrieve_section("2", "2025")
check("Section 2 (Definitions)", chunks, expect_section="2")

# ── 3. Income-head filtered search (2025) ─────────────────────────────────────
print("\n[3] Income-head filtered vector search (2025)")
chunks = r.retrieve("salary perquisite allowance", act_year="2025", top_k=5)
check("Salaries query", chunks, expect_head="Salaries")

chunks = r.retrieve("house property annual value deduction", act_year="2025", top_k=5)
check("House Property query", chunks, expect_head="House Property")

chunks = r.retrieve("capital gains transfer asset LTCG", act_year="2025", top_k=5)
check("Capital Gains query", chunks, expect_head="Capital Gains")

chunks = r.retrieve("business depreciation profit profession", act_year="2025", top_k=5)
check("Business & Profession query", chunks, expect_head="Business and Profession")

chunks = r.retrieve("80C deduction investment", act_year="2025", top_k=5)
check("Deductions 80C query", chunks, expect_head="Deductions")

# ── 4. Semantic definition queries ────────────────────────────────────────────
print("\n[4] Semantic definition queries (2025)")
chunks = r.retrieve("what is the definition of residential status", act_year="2025", top_k=6)
check("Residential status definition", chunks, min_chunks=2, expect_text="resident")

chunks = r.retrieve('what does "person" mean under income tax', act_year="2025", top_k=6)
check("Definition of person", chunks, min_chunks=2, expect_text="person")

chunks = r.retrieve("definition of previous year assessment year", act_year="2025", top_k=6)
check("Previous year / assessment year", chunks, min_chunks=2)

# ── 5. Tax slab / rate injection ──────────────────────────────────────────────
print("\n[5] Tax slab rate injection (must inject Section 202)")
chunks = r.retrieve("what is the income tax slab rate for individuals new regime", act_year="2025", top_k=6)
has_202 = any(str(c.get("section")) == "202" for c in chunks)
results.append(
    (PASS if has_202 else FAIL,
     "Slab query → Section 202 injected",
     f"Section 202 {'present' if has_202 else 'MISSING'} in {len(chunks)} chunks")
)

# ── 6. Specific legal queries ──────────────────────────────────────────────────
print("\n[6] Specific legal queries (2025)")
chunks = r.retrieve("who is liable to pay advance tax", act_year="2025", top_k=6)
# 2025 Act uses "advance payment" (Section 390) — not "advance tax"
check("Advance payment liability (S390)", chunks, min_chunks=2, expect_text="advance payment")

chunks = r.retrieve("TDS deduction on salary employer", act_year="2025", top_k=6)
check("TDS on salary", chunks, min_chunks=2)

chunks = r.retrieve("appeal to income tax appellate tribunal ITAT", act_year="2025", top_k=6)
check("ITAT appeal", chunks, min_chunks=2)

# ── 7. 1961 Act (if indexed) ───────────────────────────────────────────────────
print("\n[7] 1961 Act queries")
if store.collection_exists("1961") and store.collection_point_count("1961") > 100:
    chunks = r.retrieve_section("10", "1961")
    check("1961 Section 10 (Exempt income)", chunks, expect_section="10")

    chunks = r.retrieve("salary HRA exemption", act_year="1961", top_k=5)
    check("1961 HRA salary query", chunks, min_chunks=2)

    chunks = r.retrieve("capital gains indexation cost", act_year="1961", top_k=5)
    check("1961 Capital gains query", chunks, min_chunks=2)
else:
    results.append((WARN, "1961 collection", "still indexing — skipped"))

# ── 8. Cross-act search ────────────────────────────────────────────────────────
print("\n[8] Cross-act search")
chunks = r.retrieve("compare salary provisions old act new act", cross_act=True, top_k=8)
acts_found = {str(c.get("act_year")) for c in chunks}
check("Cross-act salary compare", chunks, min_chunks=4)
if chunks:
    results[-1] = (
        PASS if len(acts_found) == 2 else WARN,
        "Cross-act salary compare",
        f"acts found: {acts_found}, {len(chunks)} chunks"
    )

# ── 9. retrieve_definitions / retrieve_exceptions ─────────────────────────────
print("\n[9] Specialised retrieval methods")
chunks = r.retrieve_definitions("agricultural income", "2025", top_k=5)
check("retrieve_definitions: agricultural income", chunks, min_chunks=1)

chunks = r.retrieve_exceptions("exemption on dividend income", "2025", top_k=5)
check("retrieve_exceptions: dividend exemption", chunks, min_chunks=1)

# ── Summary ────────────────────────────────────────────────────────────────────
store.close()

print("\n" + "=" * 65)
print("RESULTS")
print("=" * 65)
counts = {PASS: 0, FAIL: 0, WARN: 0}
for status, name, detail in results:
    counts[status] += 1
    print(f"  {status}  {name}")
    if status != PASS:
        print(f"       {detail}")
    else:
        print(f"       {detail}")

total = len(results)
print(f"\n  {counts[PASS]}/{total} passed  |  {counts[WARN]} warnings  |  {counts[FAIL]} failures")
