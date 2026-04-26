import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Loader2, ChevronRight, Zap, Scale, TrendingUp, Briefcase, Home, BarChart3, BookOpen } from "lucide-react";
import { searchSections, autocomplete, type SearchResult } from "../lib/api";
import ActToggle from "../components/ActToggle";

const HEAD_STYLES: Record<string, { badge: string; dot: string }> = {
  "Salaries":                { badge: "badge-blue",   dot: "#7dd3fc" },
  "House Property":          { badge: "badge-green",  dot: "#6ee7b7" },
  "Business and Profession": { badge: "badge-purple", dot: "#c4b5fd" },
  "Capital Gains":           { badge: "badge-amber",  dot: "#fcd34d" },
  "Income from Other Sources":{ badge: "badge-red",   dot: "#fb923c" },
  "Deductions":              { badge: "badge-cyan",   dot: "#67e8f9" },
  "TDS / TCS":               { badge: "badge-purple", dot: "#f0abfc" },
};

const QUICK_CHIPS = [
  { label: "Section 80C",      icon: BookOpen },
  { label: "TDS salary",       icon: Zap },
  { label: "Capital gains",    icon: TrendingUp },
  { label: "HRA exemption",    icon: Home },
  { label: "Business income",  icon: Briefcase },
  { label: "Residential status", icon: Scale },
  { label: "Section 10",       icon: BarChart3 },
];

function headStyle(h: string) {
  return HEAD_STYLES[h] || { badge: "badge-gray", dot: "var(--text-muted)" };
}

export default function SearchPage() {
  const [query, setQuery]       = useState("");
  const [act, setAct]           = useState("2025");
  const [results, setResults]   = useState<SearchResult[]>([]);
  const [suggestions, setSugg]  = useState<any[]>([]);
  const [loading, setLoading]   = useState(false);
  const [searched, setSearched] = useState(false);
  const [showSugg, setShowSugg] = useState(false);
  const navigate   = useNavigate();
  const inputRef   = useRef<HTMLInputElement>(null);
  const debRef     = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (query.length < 2) { setSugg([]); return; }
    clearTimeout(debRef.current);
    debRef.current = setTimeout(async () => {
      try {
        const data = await autocomplete(query, act);
        setSugg(data.suggestions);
        setShowSugg(true);
      } catch {}
    }, 200);
    return () => clearTimeout(debRef.current);
  }, [query, act]);

  async function handleSearch(q = query) {
    if (!q.trim()) return;
    setShowSugg(false);
    setLoading(true);
    setSearched(true);
    try {
      const data = await searchSections(q, act, 20);
      setResults(data.results);
    } finally {
      setLoading(false);
    }
  }

  const searchBar = (
    <div className="flex gap-2.5 items-center">
      {/* Search input */}
      <div
        className="relative flex-1 search-input rounded-xl transition-all duration-200"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border-default)" }}
      >
        <Search
          className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none"
          style={{ color: "var(--text-muted)" }}
        />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleSearch()}
          onFocus={() => suggestions.length > 0 && setShowSugg(true)}
          onBlur={() => setTimeout(() => setShowSugg(false), 150)}
          placeholder="Search sections, topics, or ask a question…"
          className="w-full pl-11 pr-4 py-3 bg-transparent text-sm outline-none"
          style={{ color: "var(--text-primary)" }}
        />
        <div
          className="absolute right-3.5 top-1/2 -translate-y-1/2 rounded px-1.5 py-0.5 text-[10px] font-mono select-none"
          style={{ background: "var(--bg-hover)", color: "var(--text-muted)", border: "1px solid var(--border-default)" }}
        >
          /
        </div>

        {/* Autocomplete dropdown */}
        {showSugg && suggestions.length > 0 && (
          <div
            className="absolute top-full mt-2 left-0 right-0 rounded-xl z-50 overflow-hidden fade-in"
            style={{
              background: "var(--bg-panel)",
              border: "1px solid var(--border-default)",
              boxShadow: "0 16px 48px rgba(0,0,0,0.5)",
            }}
          >
            {suggestions.map((s, i) => (
              <button
                key={i}
                onMouseDown={() => { setQuery(`Section ${s.section}`); handleSearch(`Section ${s.section}`); }}
                className="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors"
                style={{ borderBottom: i < suggestions.length - 1 ? "1px solid var(--border-faint)" : "none" }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                <span className="section-pill shrink-0">#{s.section}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>{s.section_title}</div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{s.act_year} Act · {s.income_head}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <ActToggle value={act} onChange={setAct} />
      <button onClick={() => handleSearch()} className="btn-primary">
        Search
      </button>
    </div>
  );

  return (
    <div
      className="flex flex-col h-full overflow-auto"
      style={{ background: "var(--bg-app)" }}
    >
      {/* ── Hero (pre-search) ── */}
      {!searched && (
        <div className="flex-1 flex flex-col items-center justify-center px-8 pb-16 fade-up">
          {/* Icon mark */}
          <div className="mb-6 relative">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center"
              style={{
                background: "linear-gradient(135deg, #1d4ed8, #4a8bff)",
                boxShadow: "0 4px 28px rgba(74,139,255,0.4)",
              }}
            >
              <Scale className="w-8 h-8 text-white" />
            </div>
            <div
              className="absolute -top-1 -right-1 w-4 h-4 rounded-full flex items-center justify-center"
              style={{ background: "var(--green)", boxShadow: "0 0 8px rgba(45,212,171,0.6)" }}
            >
              <Zap className="w-2.5 h-2.5 text-white" />
            </div>
          </div>

          <h1
            className="text-3xl font-bold mb-2 text-center"
            style={{ color: "var(--text-primary)", letterSpacing: "-0.02em" }}
          >
            Income Tax Intelligence
          </h1>
          <p className="text-sm mb-8 text-center" style={{ color: "var(--text-secondary)" }}>
            Semantic search across both Income Tax Acts &middot; 7,921 indexed sections
          </p>

          {/* Search bar — hero size */}
          <div className="w-full max-w-2xl">
            {searchBar}
          </div>

          {/* Quick chips */}
          <div className="mt-8 w-full max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
              Common searches
            </p>
            <div className="flex flex-wrap gap-2">
              {QUICK_CHIPS.map(({ label, icon: Icon }) => (
                <button
                  key={label}
                  onClick={() => { setQuery(label); handleSearch(label); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150"
                  style={{
                    background: "var(--bg-panel)",
                    color: "var(--text-secondary)",
                    border: "1px solid var(--border-subtle)",
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = "var(--bg-hover)";
                    e.currentTarget.style.color = "var(--text-primary)";
                    e.currentTarget.style.borderColor = "var(--border-accent)";
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = "var(--bg-panel)";
                    e.currentTarget.style.color = "var(--text-secondary)";
                    e.currentTarget.style.borderColor = "var(--border-subtle)";
                  }}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Compact header (post-search) ── */}
      {searched && (
        <div
          className="shrink-0 px-6 py-4"
          style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-surface)" }}
        >
          <div className="max-w-4xl mx-auto">{searchBar}</div>
        </div>
      )}

      {/* ── Loading ── */}
      {loading && (
        <div className="flex items-center justify-center py-20 gap-3">
          <Loader2 className="w-5 h-5 animate-spin" style={{ color: "var(--accent)" }} />
          <span className="text-sm" style={{ color: "var(--text-secondary)" }}>Searching…</span>
        </div>
      )}

      {/* ── No results ── */}
      {!loading && searched && results.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20">
          <Search className="w-10 h-10 mb-3" style={{ color: "var(--border-default)" }} />
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>No sections found — try different keywords</p>
        </div>
      )}

      {/* ── Results ── */}
      {!loading && results.length > 0 && (
        <div className="max-w-4xl mx-auto w-full px-6 py-5">
          <p className="text-xs font-medium mb-4" style={{ color: "var(--text-muted)" }}>
            {results.length} results for <span style={{ color: "var(--text-secondary)" }}>"{query}"</span>
          </p>

          <div className="space-y-2">
            {results.map((r, i) => {
              const hs = headStyle(r.income_head);
              return (
                <button
                  key={i}
                  onClick={() => navigate(`/section/${r.act_year}/${r.section}`)}
                  className="card-hover w-full text-left p-4 fade-up flex items-start gap-4"
                  style={{ animationDelay: `${i * 0.03}s` }}
                >
                  {/* Section number */}
                  <div className="shrink-0 pt-0.5">
                    <span className="section-pill text-sm px-2 py-1">#{r.section}</span>
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <span className={hs.badge}>{r.income_head}</span>
                      <span className="badge-gray">{r.act_year} Act</span>
                      {r.score > 0 && (
                        <span className="ml-auto text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                          {(r.score * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <div className="text-sm font-semibold mb-1" style={{ color: "var(--text-primary)" }}>
                      {r.section_title}
                    </div>
                    <div className="text-xs mb-1.5" style={{ color: "var(--text-muted)" }}>
                      {r.chapter_title}
                    </div>
                    <p className="text-xs leading-relaxed line-clamp-2" style={{ color: "var(--text-secondary)" }}>
                      {r.preview}
                    </p>
                  </div>

                  <ChevronRight className="w-4 h-4 shrink-0 mt-1 transition-colors" style={{ color: "var(--text-muted)" }} />
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
