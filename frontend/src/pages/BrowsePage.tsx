import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Loader2, ChevronRight, Briefcase, Home, TrendingUp,
  DollarSign, BookOpen, Shield, FileText, Gavel, Scale,
  BarChart2, AlertTriangle, Settings2, RefreshCw,
  ArrowLeftRight, Minus, HelpCircle, Globe
} from "lucide-react";
import { getHeads, getSectionsByHead, type IncomeHead, type SearchResult } from "../lib/api";
import ActToggle from "../components/ActToggle";

const HEAD_META: Record<string, { icon: any; color: string; bg: string }> = {
  "Salaries":                    { icon: Briefcase,      color: "#7dd3fc", bg: "rgba(125,211,252,0.08)" },
  "House Property":              { icon: Home,           color: "#6ee7b7", bg: "rgba(110,231,183,0.08)" },
  "Business and Profession":     { icon: BarChart2,      color: "#c4b5fd", bg: "rgba(196,181,253,0.08)" },
  "Capital Gains":               { icon: TrendingUp,     color: "#fcd34d", bg: "rgba(252,211,77,0.08)" },
  "Income from Other Sources":   { icon: DollarSign,     color: "#fb923c", bg: "rgba(251,146,60,0.08)" },
  "Deductions":                  { icon: Minus,          color: "#67e8f9", bg: "rgba(103,232,249,0.08)" },
  "Rebates and Reliefs":         { icon: Shield,         color: "#86efac", bg: "rgba(134,239,172,0.08)" },
  "TDS / TCS":                   { icon: ArrowLeftRight, color: "#f0abfc", bg: "rgba(240,171,252,0.08)" },
  "Collection and Recovery":     { icon: RefreshCw,      color: "#93c5fd", bg: "rgba(147,197,253,0.08)" },
  "Return of Income":            { icon: FileText,       color: "#a5b4fc", bg: "rgba(165,180,252,0.08)" },
  "Assessment":                  { icon: BookOpen,       color: "#fde68a", bg: "rgba(253,230,138,0.08)" },
  "Appeals and Revisions":       { icon: Gavel,          color: "#fca5a5", bg: "rgba(252,165,165,0.08)" },
  "Penalties":                   { icon: AlertTriangle,  color: "#fbbf24", bg: "rgba(251,191,36,0.08)" },
  "Offences and Prosecution":    { icon: Scale,          color: "#f87171", bg: "rgba(248,113,113,0.08)" },
  "Exempt Income":               { icon: Shield,         color: "#6ee7b7", bg: "rgba(110,231,183,0.08)" },
  "Aggregation of Income":       { icon: BarChart2,      color: "#a5b4fc", bg: "rgba(165,180,252,0.08)" },
  "Set-off and Carry Forward":   { icon: RefreshCw,      color: "#93c5fd", bg: "rgba(147,197,253,0.08)" },
  "Anti-Avoidance":              { icon: Shield,         color: "#fb923c", bg: "rgba(251,146,60,0.08)" },
  "General Anti-Avoidance Rule": { icon: Shield,         color: "#fca5a5", bg: "rgba(252,165,165,0.08)" },
  "Special Tax Rates":           { icon: Settings2,      color: "#fcd34d", bg: "rgba(252,211,77,0.08)" },
  "Special Provisions":          { icon: BookOpen,       color: "#c4b5fd", bg: "rgba(196,181,253,0.08)" },
  "Tax Administration":          { icon: Settings2,      color: "#7dd3fc", bg: "rgba(125,211,252,0.08)" },
  "General / Definitions":       { icon: HelpCircle,     color: "#8896c8", bg: "rgba(136,150,200,0.08)" },
  "Basis of Charge":             { icon: Globe,          color: "#67e8f9", bg: "rgba(103,232,249,0.08)" },
  "Miscellaneous":               { icon: FileText,       color: "#8896c8", bg: "rgba(136,150,200,0.08)" },
};

function fallbackMeta() {
  return { icon: FileText, color: "#8896c8", bg: "rgba(136,150,200,0.08)" };
}

export default function BrowsePage() {
  const [act, setAct]           = useState("2025");
  const [heads, setHeads]       = useState<IncomeHead[]>([]);
  const [selected, setSelected] = useState<IncomeHead | null>(null);
  const [sections, setSections] = useState<SearchResult[]>([]);
  const [loading, setLoading]   = useState(true);
  const [secLoading, setSecLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    setSelected(null);
    setSections([]);
    getHeads(act).then(d => setHeads(d.heads)).finally(() => setLoading(false));
  }, [act]);

  async function selectHead(head: IncomeHead) {
    setSelected(head);
    setSecLoading(true);
    try {
      const data = await getSectionsByHead(head.slug, act);
      setSections(data.sections);
    } finally {
      setSecLoading(false);
    }
  }

  return (
    <div className="flex h-full overflow-hidden" style={{ background: "var(--bg-app)" }}>

      {/* ── Left: head list ── */}
      <div
        className="w-64 flex flex-col shrink-0 h-full overflow-hidden"
        style={{ background: "var(--bg-surface)", borderRight: "1px solid var(--border-subtle)" }}
      >
        {/* Header */}
        <div className="px-4 py-4" style={{ borderBottom: "1px solid var(--border-faint)" }}>
          <div className="text-sm font-bold mb-3" style={{ color: "var(--text-primary)" }}>Browse by Head</div>
          <ActToggle value={act} onChange={setAct} allowBoth={false} />
        </div>

        {/* Head list */}
        <div className="flex-1 overflow-auto py-2 px-2">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin" style={{ color: "var(--accent)" }} />
            </div>
          ) : (
            <div className="space-y-0.5">
              {heads.map(head => {
                const meta = HEAD_META[head.name] || fallbackMeta();
                const Icon = meta.icon;
                const isActive = selected?.slug === head.slug;
                return (
                  <button
                    key={head.slug}
                    onClick={() => selectHead(head)}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-all duration-150"
                    style={{
                      background: isActive ? "var(--bg-active)" : "transparent",
                      borderLeft: isActive ? `2px solid ${meta.color}` : "2px solid transparent",
                    }}
                    onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = "var(--bg-hover)"; }}
                    onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
                  >
                    <div
                      className="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
                      style={{ background: isActive ? meta.bg : "transparent" }}
                    >
                      <Icon className="w-3.5 h-3.5" style={{ color: meta.color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div
                        className="text-xs font-medium truncate leading-tight"
                        style={{ color: isActive ? "var(--text-primary)" : "var(--text-secondary)" }}
                      >
                        {head.name}
                      </div>
                      <div className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                        {head.section_count} sections
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Right: sections ── */}
      <div className="flex-1 overflow-auto">
        {!selected && (
          <div className="flex flex-col items-center justify-center h-full text-center px-8">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
              style={{ background: "var(--bg-panel)" }}
            >
              <BookOpen className="w-6 h-6" style={{ color: "var(--text-muted)" }} />
            </div>
            <p className="text-sm font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
              Select an income head
            </p>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Browse sections by category from the left panel
            </p>
          </div>
        )}

        {selected && (
          <div className="p-6">
            {/* Head header */}
            {(() => {
              const meta = HEAD_META[selected.name] || fallbackMeta();
              const Icon = meta.icon;
              return (
                <div className="flex items-center gap-3 mb-6 fade-up">
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                    style={{ background: meta.bg, border: `1px solid ${meta.color}22` }}
                  >
                    <Icon className="w-5 h-5" style={{ color: meta.color }} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold" style={{ color: "var(--text-primary)" }}>
                      {selected.name}
                    </h2>
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {selected.section_count} sections · {act === "both" ? "Both Acts" : `${act} Act`}
                    </p>
                  </div>
                </div>
              );
            })()}

            {secLoading ? (
              <div className="flex items-center justify-center py-16 gap-2">
                <Loader2 className="w-4 h-4 animate-spin" style={{ color: "var(--accent)" }} />
                <span className="text-sm" style={{ color: "var(--text-secondary)" }}>Loading sections…</span>
              </div>
            ) : (
              <div className="space-y-1.5">
                {sections.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => navigate(`/section/${s.act_year}/${s.section}`)}
                    className="card-hover w-full text-left px-4 py-3 flex items-center gap-3 fade-up"
                    style={{ animationDelay: `${i * 0.02}s` }}
                  >
                    <span className="section-pill shrink-0">#{s.section}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                        {s.section_title}
                      </div>
                      {s.chapter_title && (
                        <div className="text-xs truncate mt-0.5" style={{ color: "var(--text-muted)" }}>
                          {s.chapter_title}
                        </div>
                      )}
                    </div>
                    {act === "both" && (
                      <span className="badge-gray text-[10px] shrink-0">{s.act_year}</span>
                    )}
                    <ChevronRight className="w-3.5 h-3.5 shrink-0" style={{ color: "var(--text-muted)" }} />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
