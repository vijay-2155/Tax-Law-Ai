import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  Loader2, ArrowLeft, FileText, Lightbulb, ArrowRightLeft,
  ChevronDown, ChevronRight, ExternalLink, Sparkles, AlertCircle,
  GitCompare, RefreshCw,
} from "lucide-react";
import {
  getSection, getSectionSummary, getSectionEquivalent,
  getSettings, updateSettings,
  type SectionDetail, type Chunk, type SectionEquivalent, type LLMSettings,
} from "../lib/api";
import Markdown from "../components/Markdown";

// ── Model selector ────────────────────────────────────────────────────────────

const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama", ollama_cloud: "Ollama Cloud",
  openai: "OpenAI", anthropic: "Anthropic",
  gemini: "Gemini", groq: "Groq", openrouter: "OpenRouter",
  nvidia: "NVIDIA",
};

function ModelSelector({
  settings, currentModel, onSelect,
}: { settings: LLMSettings | null; currentModel: string; onSelect: (p: string, m: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!settings) return null;

  const displayModel = currentModel || settings.model || "Select model";
  const shortModel = displayModel.length > 22 ? displayModel.slice(0, 22) + "…" : displayModel;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-all"
        style={{ background: "var(--bg-hover)", color: "var(--text-secondary)", border: "1px solid var(--border-default)" }}
        onMouseEnter={e => (e.currentTarget.style.color = "var(--text-primary)")}
        onMouseLeave={e => (e.currentTarget.style.color = "var(--text-secondary)")}
      >
        <span className="font-medium" style={{ color: "var(--text-primary)" }}>
          {PROVIDER_LABELS[settings.provider] ?? settings.provider}
        </span>
        <span style={{ color: "var(--border-default)" }}>/</span>
        <span>{shortModel}</span>
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          className="absolute top-full mt-2 left-0 w-72 rounded-xl z-50 overflow-hidden"
          style={{ background: "var(--bg-panel)", border: "1px solid var(--border-default)", boxShadow: "0 20px 60px rgba(0,0,0,0.6)" }}
        >
          <div className="max-h-64 overflow-y-auto">
            {settings.available_providers.map(p => (
              <div key={p} style={{ borderBottom: "1px solid var(--border-faint)" }}>
                <div className="px-3 py-1.5 flex items-center justify-between" style={{ background: "var(--bg-card)" }}>
                  <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                    {PROVIDER_LABELS[p] ?? p}
                  </span>
                  {p === settings.provider && (
                    <span className="text-[10px] font-semibold" style={{ color: "var(--accent-light)" }}>Active</span>
                  )}
                </div>
                {(settings.available_models[p] || []).map(m => (
                  <button
                    key={`${p}-${m}`}
                    onClick={() => { onSelect(p, m); setOpen(false); }}
                    className="w-full text-left px-3 py-2 text-xs transition-colors"
                    style={{
                      background: (p === settings.provider && m === (currentModel || settings.model)) ? "var(--bg-active)" : "transparent",
                      color: (p === settings.provider && m === (currentModel || settings.model)) ? "var(--accent-light)" : "var(--text-secondary)",
                    }}
                    onMouseEnter={e => { if (!(p === settings.provider && m === (currentModel || settings.model))) { e.currentTarget.style.background = "var(--bg-hover)"; e.currentTarget.style.color = "var(--text-primary)"; } }}
                    onMouseLeave={e => { if (!(p === settings.provider && m === (currentModel || settings.model))) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-secondary)"; } }}
                  >
                    {m === "auto" ? "Auto (Recommended)" : m}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Chunk card ────────────────────────────────────────────────────────────────

function ChunkCard({ chunk }: { chunk: Chunk }) {
  const [expanded, setExpanded] = useState(chunk.chunk_index === 0);
  const isOverview = chunk.chunk_type === "section";

  return (
    <div
      className="rounded-xl overflow-hidden mb-3 transition-all duration-150"
      style={{
        background: "var(--bg-card)",
        border: `1px solid ${isOverview ? "var(--border-accent)" : "var(--border-subtle)"}`,
      }}
    >
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors"
        style={{ background: expanded && !isOverview ? "var(--bg-panel)" : "transparent" }}
        onMouseEnter={e => { if (!expanded || !isOverview) e.currentTarget.style.background = "var(--bg-hover)"; }}
        onMouseLeave={e => { e.currentTarget.style.background = expanded && !isOverview ? "var(--bg-panel)" : "transparent"; }}
      >
        {expanded
          ? <ChevronDown className="w-3.5 h-3.5 shrink-0" style={{ color: "var(--text-muted)" }} />
          : <ChevronRight className="w-3.5 h-3.5 shrink-0" style={{ color: "var(--text-muted)" }} />}

        {isOverview ? (
          <span
            className="text-xs font-bold px-2 py-0.5 rounded"
            style={{ background: "var(--accent-dim)", color: "var(--accent-light)", border: "1px solid var(--border-accent)" }}
          >
            Overview
          </span>
        ) : (
          <span
            className="text-xs font-mono font-medium px-1.5 py-0.5 rounded"
            style={{ background: "var(--bg-hover)", color: "var(--text-secondary)", border: "1px solid var(--border-default)" }}
          >
            Part {chunk.chunk_index}
          </span>
        )}

        {!expanded && (
          <span className="text-xs line-clamp-1 flex-1 ml-1" style={{ color: "var(--text-muted)" }}>
            {chunk.text.slice(0, 120)}…
          </span>
        )}
      </button>

      {expanded && (
        <div className="px-5 pb-5 pt-2">
          <p
            className="text-sm leading-relaxed whitespace-pre-wrap"
            style={{ color: isOverview ? "var(--text-primary)" : "var(--text-secondary)", fontFamily: "'Plus Jakarta Sans', sans-serif" }}
          >
            {chunk.text}
          </p>
        </div>
      )}
    </div>
  );
}

function stripThinkTags(text: string): string {
  return text.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
}

// Extracts verdict keyword from analysis text for the banner
function extractVerdict(analysis: string): { verdict: string; justification: string } | null {
  const m = analysis.match(/(EQUIVALENT|PARTIALLY_EQUIVALENT|RENAMED_ONLY|NO_EQUIVALENT)[\s—–-]+(.+)/i);
  if (!m) return null;
  return { verdict: m[1].toUpperCase(), justification: m[2].trim() };
}

const VERDICT_STYLES: Record<string, { color: string; bg: string; border: string; label: string }> = {
  EQUIVALENT:           { color: "var(--green)",        bg: "rgba(45,212,171,0.08)",  border: "rgba(45,212,171,0.25)",  label: "Equivalent" },
  PARTIALLY_EQUIVALENT: { color: "var(--amber)",        bg: "rgba(251,191,36,0.08)",  border: "rgba(251,191,36,0.25)",  label: "Partially Equivalent" },
  RENAMED_ONLY:         { color: "var(--accent-light)", bg: "rgba(74,139,255,0.08)",  border: "var(--border-accent)",   label: "Renamed Only" },
  NO_EQUIVALENT:        { color: "var(--red)",           bg: "rgba(248,113,113,0.08)", border: "rgba(248,113,113,0.25)", label: "No Equivalent" },
};

// ── Equivalence tab ───────────────────────────────────────────────────────────

function EquivalentTab({ act, number, otherAct }: { act: string; number: string; otherAct: string }) {
  const [data, setData] = useState<SectionEquivalent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    getSectionEquivalent(act, number)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [act, number]);

  // ── Loading ──
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center"
          style={{ background: "var(--accent-dim)", border: "1px solid var(--border-accent)" }}
        >
          <Loader2 className="w-6 h-6 animate-spin" style={{ color: "var(--accent-light)" }} />
        </div>
        <div className="text-center">
          <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            Finding equivalent section…
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Semantic matching + AI comparison in progress
          </p>
        </div>
      </div>
    );
  }

  // ── Error ──
  if (error) {
    return (
      <div
        className="flex items-start gap-3 p-5 rounded-xl"
        style={{ background: "rgba(248,113,113,0.07)", border: "1px solid rgba(248,113,113,0.2)" }}
      >
        <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" style={{ color: "var(--red)" }} />
        <div>
          <p className="text-sm font-semibold mb-1" style={{ color: "var(--red)" }}>Comparison Failed</p>
          <p className="text-xs" style={{ color: "rgba(248,113,113,0.7)" }}>{error}</p>
        </div>
      </div>
    );
  }

  // ── No equivalent ──
  if (!data?.equivalent) {
    return (
      <div
        className="rounded-2xl p-8 text-center max-w-md mx-auto"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)" }}
      >
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4"
          style={{ background: "var(--bg-hover)", border: "1px solid var(--border-default)" }}
        >
          <ArrowRightLeft className="w-5 h-5" style={{ color: "var(--text-muted)" }} />
        </div>
        <h3 className="text-base font-bold mb-2" style={{ color: "var(--text-primary)" }}>
          No Equivalent Found
        </h3>
        <p className="text-sm leading-relaxed mb-5" style={{ color: "var(--text-secondary)" }}>
          Section {number} [{act} Act] has no semantically similar counterpart in the {otherAct} Act.
          This section may be new, merged, or removed.
        </p>
        <Link
          to={`/section/${otherAct}/${number}`}
          className="btn-secondary text-xs"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          Try #{number} in {otherAct} Act anyway
        </Link>
      </div>
    );
  }

  const eq = data.equivalent;
  const pct = Math.round(eq.confidence * 100);
  const confColor = pct >= 80 ? "var(--green)" : pct >= 60 ? "var(--amber)" : "var(--red)";
  const verdictInfo = data.analysis ? extractVerdict(stripThinkTags(data.analysis)) : null;
  const vStyle = verdictInfo ? (VERDICT_STYLES[verdictInfo.verdict] ?? VERDICT_STYLES.PARTIALLY_EQUIVALENT) : null;

  return (
    <div className="space-y-5 fade-up">

      {/* ── Two-panel section cards ── */}
      <div className="grid grid-cols-1 gap-3" style={{ gridTemplateColumns: "1fr auto 1fr" }}>

        {/* Source panel */}
        <div
          className="rounded-2xl p-5"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border-default)" }}
        >
          <div className="text-[10px] font-bold uppercase tracking-widest mb-3 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
            <span
              className="px-1.5 py-0.5 rounded"
              style={{ background: "var(--bg-hover)", border: "1px solid var(--border-default)" }}
            >
              {act} Act
            </span>
            <span>Source</span>
          </div>
          <div
            className="text-3xl font-bold mb-1"
            style={{ color: "var(--accent-light)", fontFamily: "'JetBrains Mono', monospace", letterSpacing: "-0.02em" }}
          >
            #{data.source.section}
          </div>
          <div className="text-sm font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
            {data.source.section_title}
          </div>
        </div>

        {/* Center column: connector + confidence */}
        <div className="flex flex-col items-center justify-center gap-2 px-2">
          <div className="flex flex-col items-center gap-1">
            <div
              className="w-px flex-1"
              style={{ background: "linear-gradient(to bottom, transparent, var(--border-default))", minHeight: 16 }}
            />
            <ArrowRightLeft className="w-5 h-5" style={{ color: "var(--text-muted)" }} />
            <div
              className="w-px flex-1"
              style={{ background: "linear-gradient(to top, transparent, var(--border-default))", minHeight: 16 }}
            />
          </div>
          {/* Confidence meter */}
          <div className="text-center">
            <div className="text-lg font-bold" style={{ color: confColor, fontFamily: "'JetBrains Mono', monospace" }}>
              {pct}%
            </div>
            <div className="text-[9px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>match</div>
            <div
              className="w-10 h-1 rounded-full mt-1.5 overflow-hidden"
              style={{ background: "var(--bg-hover)" }}
            >
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${pct}%`, background: confColor }}
              />
            </div>
          </div>
        </div>

        {/* Equivalent panel */}
        <div
          className="rounded-2xl p-5"
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-accent)",
            boxShadow: "0 0 0 1px rgba(74,139,255,0.06), 0 4px 20px rgba(74,139,255,0.06)",
          }}
        >
          <div className="text-[10px] font-bold uppercase tracking-widest mb-3 flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
            <span
              className="px-1.5 py-0.5 rounded"
              style={{ background: "var(--accent-dim)", border: "1px solid var(--border-accent)", color: "var(--accent-light)" }}
            >
              {otherAct} Act
            </span>
            <span>Equivalent</span>
          </div>
          <Link to={`/section/${otherAct}/${eq.section}`} className="group flex items-start gap-2">
            <div
              className="text-3xl font-bold"
              style={{ color: "var(--accent-light)", fontFamily: "'JetBrains Mono', monospace", letterSpacing: "-0.02em" }}
            >
              #{eq.section}
            </div>
            <ExternalLink
              className="w-4 h-4 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity"
              style={{ color: "var(--accent-light)" }}
            />
          </Link>
          <div className="text-sm font-semibold mb-1" style={{ color: "var(--text-primary)" }}>
            {eq.section_title}
          </div>
          {eq.income_head && (
            <div className="text-[11px] mt-1 badge-blue inline-flex">{eq.income_head}</div>
          )}
          <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--border-faint)" }}>
            <Link
              to={`/section/${otherAct}/${eq.section}`}
              className="btn-primary text-xs"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Open #{eq.section} in {otherAct} Act
            </Link>
          </div>
        </div>
      </div>

      {/* ── Verdict banner ── */}
      {vStyle && verdictInfo && (
        <div
          className="rounded-xl px-5 py-4 flex items-center gap-3"
          style={{ background: vStyle.bg, border: `1px solid ${vStyle.border}` }}
        >
          <span
            className="text-xs font-bold px-3 py-1.5 rounded-full shrink-0"
            style={{ background: `${vStyle.color}22`, color: vStyle.color, border: `1px solid ${vStyle.border}` }}
          >
            {vStyle.label.toUpperCase()}
          </span>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {verdictInfo.justification}
          </p>
        </div>
      )}

      {/* ── AI Comparison (full Markdown) ── */}
      {data.analysis && (
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)" }}
        >
          {/* Card header */}
          <div
            className="flex items-center gap-3 px-6 py-4"
            style={{ borderBottom: "1px solid var(--border-faint)", background: "var(--bg-surface)" }}
          >
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
              style={{ background: "linear-gradient(135deg, var(--accent) 0%, #22d3ee 100%)" }}
            >
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
            <div>
              <h3 className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>
                AI Comparison Analysis
              </h3>
              <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                What changed between the {act} Act and {otherAct} Act
              </p>
            </div>
          </div>

          {/* Markdown body */}
          <div className="px-6 py-5 prose-legal">
            <Markdown act={act}>
              {stripThinkTags(data.analysis)}
            </Markdown>
          </div>
        </div>
      )}

      {/* ── Side-by-side preview ── */}
      {eq.preview && (
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)" }}
        >
          <div
            className="flex items-center justify-between px-5 py-3"
            style={{ borderBottom: "1px solid var(--border-faint)", background: "var(--bg-surface)" }}
          >
            <span className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
              #{eq.section} Text Preview — {otherAct} Act
            </span>
            <Link
              to={`/section/${otherAct}/${eq.section}`}
              className="text-xs flex items-center gap-1.5 transition-colors"
              style={{ color: "var(--accent-light)" }}
            >
              View full section <ExternalLink className="w-3 h-3" />
            </Link>
          </div>
          <div className="px-5 py-4">
            <p
              className="text-sm leading-[1.8] whitespace-pre-wrap line-clamp-8"
              style={{ color: "var(--text-secondary)", fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              {eq.preview}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type TabKey = "full" | "summary" | "equivalent";

export default function SectionPage() {
  const { act, number } = useParams<{ act: string; number: string }>();
  const navigate = useNavigate();
  const [data, setData]         = useState<SectionDetail | null>(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState("");
  const [tab, setTab]           = useState<TabKey>("full");
  const [summary, setSummary]   = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [currentModel, setCurrentModel] = useState("");
  const [equivalentKey, setEquivalentKey] = useState(0);

  useEffect(() => {
    getSettings().then(s => { setSettings(s); setCurrentModel(s.model); }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!act || !number) return;
    setLoading(true);
    setError("");
    setData(null);
    setSummary(null);
    setTab("full");
    getSection(act, number)
      .then(d => { setData(d); if (d.summary) setSummary(d.summary); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [act, number]);

  async function handleLlmChange(provider: string, model: string) {
    setCurrentModel(model);
    await updateSettings({ provider, model }).catch(() => {});
    setSettings(prev => prev ? { ...prev, provider, model } : prev);
  }

  async function loadSummary(force = false) {
    if ((summary && !force) || !act || !number) return;
    setSummary(null);
    setSummaryLoading(true);
    try {
      const res = await getSectionSummary(act, number, force);
      setSummary(res.summary);
    } catch (e: any) {
      setSummary("Failed to generate summary: " + e.message);
    } finally {
      setSummaryLoading(false);
    }
  }

  useEffect(() => {
    if (tab === "summary") loadSummary();
  }, [tab]);

  if (loading) return (
    <div className="flex items-center justify-center h-full" style={{ background: "var(--bg-app)" }}>
      <Loader2 className="w-5 h-5 animate-spin" style={{ color: "var(--accent)" }} />
    </div>
  );

  if (error) return (
    <div className="flex flex-col items-center justify-center h-full text-center p-8" style={{ background: "var(--bg-app)" }}>
      <p className="text-sm mb-4" style={{ color: "var(--red)" }}>{error}</p>
      <button onClick={() => navigate(-1)} className="btn-secondary">Go back</button>
    </div>
  );

  if (!data) return null;

  const otherAct = act === "2025" ? "1961" : "2025";

  const tabs: { key: TabKey; label: string; icon: any }[] = [
    { key: "full",      label: "Full Text",    icon: FileText },
    { key: "summary",   label: "AI Summary",   icon: Lightbulb },
    { key: "equivalent",label: "Equivalent",   icon: GitCompare },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: "var(--bg-app)" }}>

      {/* ── Header ── */}
      <div
        className="shrink-0 px-6 py-4 fade-up"
        style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-subtle)" }}
      >
        <div className="max-w-5xl mx-auto">
          {/* Back */}
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1.5 text-xs mb-4 transition-colors"
            style={{ color: "var(--text-muted)" }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--text-primary)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back
          </button>

          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <span
                  className="text-2xl font-bold"
                  style={{ color: "var(--accent-light)", fontFamily: "'JetBrains Mono', monospace" }}
                >
                  #{data.section}
                </span>
                <span className="badge-gray text-xs">{data.act_year} Act</span>
                {data.income_head && (
                  <span className="badge-blue text-xs">{data.income_head}</span>
                )}
              </div>
              <h1 className="text-lg font-bold mb-1" style={{ color: "var(--text-primary)" }}>
                {data.section_title}
              </h1>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                {data.chapter_title}
                {data.page_start && ` · Pages ${data.page_start}–${data.page_end}`}
                {` · ${data.chunk_count} chunks`}
              </p>
            </div>

            <Link
              to={`/section/${otherAct}/${data.section}`}
              className="btn-secondary text-xs shrink-0 flex items-center gap-1.5"
            >
              <ArrowRightLeft className="w-3.5 h-3.5" />
              View in {otherAct} Act
            </Link>
          </div>

          {/* Tabs */}
          <div className="flex gap-0.5 mt-5">
            {tabs.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg transition-all duration-150"
                style={
                  tab === key
                    ? { background: "var(--accent-dim)", color: "var(--accent-light)", border: "1px solid var(--border-accent)" }
                    : { color: "var(--text-muted)", border: "1px solid transparent" }
                }
              >
                <Icon className="w-3.5 h-3.5" /> {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-auto px-6 py-6">
        <div className="max-w-5xl mx-auto">

          {/* Full text */}
          {tab === "full" && (
            <div className="space-y-0 fade-up">
              {data.chunks.map((chunk, i) => (
                <ChunkCard key={chunk.chunk_id || i} chunk={chunk} />
              ))}
            </div>
          )}

          {/* Summary */}
          {tab === "summary" && (
            <div className="fade-up max-w-3xl">
              {/* Toolbar */}
              <div className="flex items-center gap-2 mb-4">
                <ModelSelector settings={settings} currentModel={currentModel} onSelect={handleLlmChange} />
                {summary && !summaryLoading && (
                  <button
                    onClick={() => loadSummary(true)}
                    className="btn-secondary text-xs flex items-center gap-1.5"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Regenerate
                  </button>
                )}
              </div>

              {summaryLoading ? (
                <div className="flex items-center gap-2" style={{ color: "var(--text-secondary)" }}>
                  <Loader2 className="w-4 h-4 animate-spin" style={{ color: "var(--accent)" }} />
                  <span className="text-sm">Generating AI summary…</span>
                </div>
              ) : summary ? (
                <div
                  className="rounded-xl p-6"
                  style={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)" }}
                >
                  <div className="flex items-center gap-2 mb-4">
                    <Lightbulb className="w-4 h-4" style={{ color: "var(--accent)" }} />
                    <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>AI Summary</h3>
                  </div>
                  <div className="prose-legal">
                    <Markdown act={act}>{summary}</Markdown>
                  </div>
                  {data.examples && (
                    <>
                      <hr className="my-5" style={{ borderColor: "var(--border-subtle)" }} />
                      <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>Examples</h3>
                      <div className="prose-legal"><Markdown act={act}>{data.examples}</Markdown></div>
                    </>
                  )}
                </div>
              ) : (
                <button onClick={() => loadSummary()} className="btn-primary flex items-center gap-2">
                  <Lightbulb className="w-4 h-4" /> Generate Summary
                </button>
              )}
            </div>
          )}

          {/* Equivalent */}
          {tab === "equivalent" && act && number && (
            <div className="fade-up">
              {/* Toolbar */}
              <div className="flex items-center gap-2 mb-5">
                <ModelSelector settings={settings} currentModel={currentModel} onSelect={handleLlmChange} />
                <button
                  onClick={() => setEquivalentKey(k => k + 1)}
                  className="btn-secondary text-xs flex items-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Regenerate
                </button>
              </div>
              <EquivalentTab key={equivalentKey} act={act} number={number} otherAct={otherAct} />
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
