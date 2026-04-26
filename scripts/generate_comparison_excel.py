"""
Generate a comprehensive Excel comparison between IT Act 1961 and IT Act 2025.

Columns:
  Section (1961) | Title (1961) | Section (2025) | Title (2025) | Chapter
  Definition (1961) | Rates (1961) | Applicability (1961)
  Definition (2025) | Rates (2025) | Applicability (2025)
  Key Changes
"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import xlsxwriter

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "backend" / "data"
OUT  = BASE / "IT_Act_Comparison_1961_vs_2025.xlsx"


# ─── Chapter mapping: 1961 chapter number → 2025 chapter number(s) ─────────
# Based on structural analysis of both acts

CHAPTER_MAP_1961_TO_2025 = {
    "I":     ["I"],
    "II":    ["II"],
    "III":   ["III"],
    "IV":    ["IV"],
    "V":     ["V"],
    "VI":    ["VI", "VII", "VIII"],   # 1961 Ch VI covers set-off, losses, deductions
    "VII":   ["VIII", "IX"],
    "VIII":  ["IX"],
    "IX":    ["X", "XI"],
    "X":     ["X", "XI"],
    "XI":    ["XIII"],
    "XII":   ["XIII"],
    "XIII":  ["XIV"],
    "XIV":   ["XV", "XVI"],
    "XV":    ["XVII"],
    "XVI":   ["XVII"],
    "XVII":  ["XIX"],
    "XVIII": ["IX", "XX"],
    "XIX":   ["XX"],
    "XX":    ["XVIII"],
    "XXI":   ["XXI"],
    "XXII":  ["XXII"],
    "XXIII": ["XXIII"],
}

# Build reverse mapping for quick lookup
_2025_to_possible_1961: dict[str, list[str]] = {}
for ch1, chs2 in CHAPTER_MAP_1961_TO_2025.items():
    for ch2 in chs2:
        _2025_to_possible_1961.setdefault(ch2, []).append(ch1)


# ─── Text extraction helpers ─────────────────────────────────────────────────

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def title_sim(a: str, b: str) -> float:
    a = re.sub(r'[^\w\s]', '', a.lower())
    b = re.sub(r'[^\w\s]', '', b.lower())
    return SequenceMatcher(None, a, b).ratio()


def keyword_overlap(a: str, b: str) -> float:
    """Fraction of significant words in `a` that appear in `b`."""
    stop = {"the", "of", "in", "to", "and", "a", "or", "for", "on",
            "any", "be", "is", "are", "at", "by", "an", "this", "that"}
    wa = {w for w in re.findall(r'\w+', a.lower()) if w not in stop and len(w) > 2}
    wb = {w for w in re.findall(r'\w+', b.lower()) if w not in stop and len(w) > 2}
    if not wa:
        return 0.0
    return len(wa & wb) / len(wa)


def combined_sim(t1: str, t2: str) -> float:
    """Blended score: 60% sequence ratio + 40% keyword overlap."""
    return 0.6 * title_sim(t1, t2) + 0.4 * keyword_overlap(t1, t2)


def extract_definition(text: str, title: str) -> str:
    text = clean(text)
    # Pattern: "X" means …
    m = re.search(r'"[^"]{2,80}"\s+(?:means|includes)\s+([^;]{15,350})', text)
    if m:
        return clean(m.group(0))[:450]
    # Pattern: For the purposes of …
    m = re.search(r'(For the purposes of[^,\.]{0,80}[,\.]\s*[^\.]{15,300})', text)
    if m:
        return clean(m.group(1))[:450]
    # Strip leading section number and return first meaningful chunk
    body = re.sub(r'^\d+[\w\-]*\.\s*', '', text)
    return clean(body)[:450]


def extract_rates(text: str) -> str:
    text = clean(text)
    # Explicit "at the rate of X%"
    hits = re.findall(
        r'(?:at\s+(?:the\s+)?rate\s+of\s+|@\s*|rate\s+of\s+)'
        r'[\d\.]+\s*(?:per\s*cent|percent|%)',
        text, re.IGNORECASE
    )
    if hits:
        return "; ".join(dict.fromkeys(hits))[:300]
    # Standalone percentages
    hits2 = re.findall(r'[\d\.]+\s*(?:per\s*cent|percent|%)', text, re.IGNORECASE)
    if hits2:
        return "; ".join(dict.fromkeys(hits2[:8]))[:300]
    return "Not specified"


def extract_applicability(text: str, title: str) -> str:
    text = clean(text)
    patterns = [
        r'(applies?\s+to\s+[^\.;]{10,200})',
        r'(applicable\s+to\s+[^\.;]{10,200})',
        r'(shall\s+apply\s+to\s+[^\.;]{10,200})',
        r'(every\s+(?:person|assessee|individual|company|firm|HUF|resident)[^\.;]{0,200})',
        r'(in\s+the\s+case\s+of\s+[^\.;]{10,200})',
        r'(where\s+(?:any|the)\s+(?:person|assessee|company|individual|firm)[^\.;]{10,200})',
        r'(any\s+(?:person|assessee|individual|company|firm|resident)[^,\.;]{10,200})',
    ]
    found = []
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            snippet = clean(m.group(1))
            if snippet not in found:
                found.append(snippet)
            if len(found) >= 2:
                break
        if len(found) >= 2:
            break
    if found:
        return "; ".join(found)[:400]
    return f"Refer to section text ({title})"


# ─── Load data ───────────────────────────────────────────────────────────────

def load(path):
    with open(path) as f:
        return json.load(f)["sections"]

s1961_all = load(DATA / "parsed_1961.json")
s2025_all = load(DATA / "parsed_2025.json")

# Build maps – first occurrence wins (avoids TDS schedule pseudo-sections)
map1961: dict = {}
for s in s1961_all:
    map1961.setdefault(s["number"], s)

map2025: dict = {}
for s in s2025_all:
    map2025.setdefault(s["number"], s)

# Group 2025 sections by chapter
ch2025: dict[str, list] = {}
for s in s2025_all:
    # Skip duplicate-number TDS schedule rows (chapter XIX rows 1-8)
    if s["number"] in map2025 and map2025[s["number"]] is not s:
        continue
    ch2025.setdefault(s["chapter_number"], []).append(s)


# ─── Matching ────────────────────────────────────────────────────────────────

def candidate_2025_pool(s1961: dict, used: set) -> list:
    """Return candidate 2025 sections for matching, preferring mapped chapters."""
    ch = s1961["chapter_number"]
    mapped_chs = CHAPTER_MAP_1961_TO_2025.get(ch, [ch])

    pool = []
    for mch in mapped_chs:
        for s in ch2025.get(mch, []):
            if s["number"] not in used:
                pool.append(s)

    # Fallback: all unmatched 2025 sections
    if not pool:
        pool = [s for s in map2025.values() if s["number"] not in used]
    return pool


def best_2025_match(s1961: dict, used: set):
    """
    Match a 1961 section to a 2025 section.
    Priority:
      1. Same section number AND combined_sim >= 0.40
      2. Best combined_sim in chapter-mapped pool (>= 0.50)
      3. Best combined_sim across all remaining (>= 0.65)
    """
    num   = s1961["number"]
    title = s1961["title"]

    # 1. Same section number
    if num in map2025 and num not in used:
        sim = combined_sim(title, map2025[num]["title"])
        if sim >= 0.35:
            return map2025[num], "number_match"

    # 2. Chapter-mapped pool
    pool = candidate_2025_pool(s1961, used)
    best_s, best_sim = None, 0.0
    for s in pool:
        sim = combined_sim(title, s["title"])
        if sim > best_sim:
            best_sim, best_s = sim, s
    if best_sim >= 0.48:
        return best_s, "chapter_title_match"

    # 3. Global fallback
    best_s, best_sim = None, 0.0
    for s in map2025.values():
        if s["number"] in used:
            continue
        sim = combined_sim(title, s["title"])
        if sim > best_sim:
            best_sim, best_s = sim, s
    if best_sim >= 0.62:
        return best_s, "global_title_match"

    return None, "no_match"


def compute_changes(s1: dict | None, s2: dict | None) -> str:
    if s1 is None:
        return "NEW section in ITA 2025 — no direct equivalent in ITA 1961"
    if s2 is None:
        return "Section NOT carried forward to ITA 2025 (repealed/merged)"

    changes = []
    t1 = re.sub(r'[^\w\s]', '', s1["title"].lower()).strip()
    t2 = re.sub(r'[^\w\s]', '', s2["title"].lower()).strip()
    if t1 != t2 and title_sim(t1, t2) < 0.92:
        changes.append(f'Title revised: "{s1["title"]}" → "{s2["title"]}"')

    if s1["number"] != s2["number"]:
        changes.append(f'Renumbered: Sec {s1["number"]} (1961) → Sec {s2["number"]} (2025)')

    c1 = s1["chapter_title"].strip().upper()
    c2 = s2["chapter_title"].strip().upper()
    if combined_sim(c1, c2) < 0.7:
        changes.append(f'Moved: Chapter "{s1["chapter_title"]}" → "{s2["chapter_title"]}"')

    len1 = len(s1.get("full_text", ""))
    len2 = len(s2.get("full_text", ""))
    if len2 > len1 * 1.30:
        changes.append("Scope expanded — provisions significantly elaborated in 2025")
    elif len2 < len1 * 0.70:
        changes.append("Scope reduced/consolidated — text substantially shorter in 2025")
    else:
        changes.append("Language modernised / minor drafting changes")

    return "; ".join(changes)


# ─── Build rows ──────────────────────────────────────────────────────────────

rows = []
used_2025: set[str] = set()

# Pass 1: for each 1961 section, find best 2025 match
for s1 in s1961_all:
    s2, mtype = best_2025_match(s1, used_2025)
    if s2:
        used_2025.add(s2["number"])

    rows.append({
        "sec_1961":   s1["number"],
        "title_1961": clean(s1["title"]),
        "sec_2025":   s2["number"] if s2 else "—",
        "title_2025": clean(s2["title"]) if s2 else "—",
        "chapter":    clean(s1["chapter_title"]),
        "def_1961":   extract_definition(s1.get("full_text", ""), s1["title"]),
        "rates_1961": extract_rates(s1.get("full_text", "")),
        "app_1961":   extract_applicability(s1.get("full_text", ""), s1["title"]),
        "def_2025":   extract_definition(s2.get("full_text", ""), s2["title"]) if s2 else "—",
        "rates_2025": extract_rates(s2.get("full_text", "")) if s2 else "—",
        "app_2025":   extract_applicability(s2.get("full_text", ""), s2["title"]) if s2 else "—",
        "changes":    compute_changes(s1, s2),
        "match_type": mtype,
    })

# Pass 2: 2025 sections not matched to any 1961 section
for s2 in map2025.values():
    if s2["number"] in used_2025:
        continue
    rows.append({
        "sec_1961":   "—",
        "title_1961": "—",
        "sec_2025":   s2["number"],
        "title_2025": clean(s2["title"]),
        "chapter":    clean(s2["chapter_title"]),
        "def_1961":   "—",
        "rates_1961": "—",
        "app_1961":   "—",
        "def_2025":   extract_definition(s2.get("full_text", ""), s2["title"]),
        "rates_2025": extract_rates(s2.get("full_text", "")),
        "app_2025":   extract_applicability(s2.get("full_text", ""), s2["title"]),
        "changes":    "NEW section in ITA 2025 — no direct equivalent in ITA 1961",
        "match_type": "new_2025",
    })


# ─── Sort ────────────────────────────────────────────────────────────────────

def sort_key(row):
    n = row["sec_1961"]
    if n == "—":
        n2 = row["sec_2025"]
        m = re.match(r'^(\d+)', n2)
        return (900000 + (int(m.group(1)) if m else 0), n2)
    m = re.match(r'^(\d+)', n)
    return (int(m.group(1)) if m else 999999, n)

rows.sort(key=sort_key)


# ─── Write Excel ─────────────────────────────────────────────────────────────

wb = xlsxwriter.Workbook(str(OUT))
ws = wb.add_worksheet("Comparison")

# ── Formats ──────────────────────────────────────────────────────────────────
def fmt(wb, **kw):
    return wb.add_format(kw)

hdr_top = fmt(wb, bold=True, font_size=10, font_color="white",
              bg_color="#1F4E79", border=1, align="center",
              valign="vcenter", text_wrap=True)
hdr_1961 = fmt(wb, bold=True, font_size=9, font_color="white",
               bg_color="#2E75B6", border=1, align="center",
               valign="vcenter", text_wrap=True)
hdr_2025 = fmt(wb, bold=True, font_size=9, font_color="white",
               bg_color="#375623", border=1, align="center",
               valign="vcenter", text_wrap=True)
hdr_cmn  = fmt(wb, bold=True, font_size=9, font_color="white",
               bg_color="#7030A0", border=1, align="center",
               valign="vcenter", text_wrap=True)
hdr_col  = fmt(wb, bold=True, font_size=9, font_color="white",
               bg_color="#203864", border=1, align="center",
               valign="vcenter", text_wrap=True)

base = dict(font_size=9, border=1, valign="top", text_wrap=True)
cf1  = fmt(wb, **base, bg_color="#DDEEFF")          # 1961 cells
cf2  = fmt(wb, **base, bg_color="#E2EFDA")          # 2025 cells
cfc  = fmt(wb, **base, bg_color="#FFF9E6")          # chapter cells
cfch = fmt(wb, **base, bg_color="#FFFACD", italic=True)   # changes
cfs1 = fmt(wb, **base, bg_color="#B8CCE4", bold=True, align="center")  # sec# 1961
cfs2 = fmt(wb, **base, bg_color="#C6E0B4", bold=True, align="center")  # sec# 2025
cfnw = fmt(wb, **base, bg_color="#E2EFDA", italic=True)  # new in 2025
cfdl = fmt(wb, **base, bg_color="#FCE4D6", italic=True)  # deleted in 2025

# ── Merged group headers (row 0) ──────────────────────────────────────────────
#  Cols:  0  1    |  2  3    |  4      |  5  6  7   |  8  9  10  |  11
ws.merge_range(0, 0,  0, 1,  "Income Tax Act 1961",  hdr_1961)
ws.merge_range(0, 2,  0, 3,  "Income Tax Act 2025",  hdr_2025)
ws.write(0, 4,  "Chapter", hdr_cmn)
ws.merge_range(0, 5,  0, 7,  "Income Tax Act 1961",  hdr_1961)
ws.merge_range(0, 8,  0, 10, "Income Tax Act 2025",  hdr_2025)
ws.write(0, 11, "Key Changes (1961 → 2025)", hdr_cmn)

# ── Sub-headers (row 1) ──────────────────────────────────────────────────────
SUB = [
    "Section No.\n(1961)",  "Section Title\n(1961)",
    "Section No.\n(2025)",  "Section Title\n(2025)",
    "Chapter",
    "Definition\n(ITA 1961)", "Tax Rates\n(ITA 1961)", "Applicability\n(ITA 1961)",
    "Definition\n(ITA 2025)", "Tax Rates\n(ITA 2025)", "Applicability\n(ITA 2025)",
    "Key Changes",
]
for c, h in enumerate(SUB):
    ws.write(1, c, h, hdr_col)

# Column widths
WS = [10, 32, 10, 32, 26, 42, 26, 36, 42, 26, 36, 48]
for c, w in enumerate(WS):
    ws.set_column(c, c, w)

ws.freeze_panes(2, 0)
ws.set_row(0, 22)
ws.set_row(1, 30)

# ── Data rows ─────────────────────────────────────────────────────────────────
STATS = {"matched": 0, "deleted": 0, "new": 0}

for r, row in enumerate(rows, start=2):
    is_new = row["sec_1961"] == "—"
    is_del = row["sec_2025"] == "—"

    if is_new:
        STATS["new"] += 1
        f1, f2, fs1, fs2, fch, fchg = cfnw, cf2, cfs2, cfs2, cfc, cfch
    elif is_del:
        STATS["deleted"] += 1
        f1, f2, fs1, fs2, fch, fchg = cf1, cfdl, cfs1, cfs2, cfc, cfdl
    else:
        STATS["matched"] += 1
        f1, f2, fs1, fs2, fch, fchg = cf1, cf2, cfs1, cfs2, cfc, cfch

    ws.write(r, 0,  row["sec_1961"],   fs1)
    ws.write(r, 1,  row["title_1961"], f1)
    ws.write(r, 2,  row["sec_2025"],   fs2)
    ws.write(r, 3,  row["title_2025"], f2)
    ws.write(r, 4,  row["chapter"],    fch)
    ws.write(r, 5,  row["def_1961"],   f1)
    ws.write(r, 6,  row["rates_1961"], f1)
    ws.write(r, 7,  row["app_1961"],   f1)
    ws.write(r, 8,  row["def_2025"],   f2)
    ws.write(r, 9,  row["rates_2025"], f2)
    ws.write(r, 10, row["app_2025"],   f2)
    ws.write(r, 11, row["changes"],    fchg)

    ws.set_row(r, 90)


# ── Summary sheet ─────────────────────────────────────────────────────────────
ws2 = wb.add_worksheet("Summary")
sfmt = fmt(wb, bold=True, font_size=11, font_color="white",
           bg_color="#1F4E79", border=1, align="left", valign="vcenter")
vfmt = fmt(wb, font_size=11, border=1, align="left", valign="vcenter")

SUMMARY = [
    ("Total comparison rows", len(rows)),
    ("Sections matched (1961 ↔ 2025)", STATS["matched"]),
    ("Sections only in 1961 (repealed/merged)", STATS["deleted"]),
    ("Sections new in 2025 (no 1961 equivalent)", STATS["new"]),
    ("Total sections in ITA 1961", len(s1961_all)),
    ("Total sections in ITA 2025", len(s2025_all)),
    ("", ""),
    ("Colour Legend", ""),
    ("Blue background", "Income Tax Act 1961 data"),
    ("Green background", "Income Tax Act 2025 data"),
    ("Yellow-cream background", "Key Changes / Chapter"),
    ("Red-orange background", "Section repealed / not in ITA 2025"),
]
ws2.set_column(0, 0, 50)
ws2.set_column(1, 1, 20)
for r2, (label, val) in enumerate(SUMMARY):
    ws2.write(r2, 0, label, sfmt if label else vfmt)
    ws2.write(r2, 1, val,   vfmt)
    ws2.set_row(r2, 22)

wb.close()
print(f"Done! {len(rows)} rows — matched={STATS['matched']}, "
      f"deleted={STATS['deleted']}, new={STATS['new']}")
print(f"Output: {OUT}")
