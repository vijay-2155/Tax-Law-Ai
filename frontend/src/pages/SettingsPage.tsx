import { useState, useEffect } from "react";
import { Settings, CheckCircle, XCircle, Loader2, Zap } from "lucide-react";
import { getSettings, updateSettings, testConnection, formatError, type LLMSettings } from "../lib/api";

const PROVIDER_LABELS: Record<string, string> = {
  ollama:       "Ollama (Local)",
  ollama_cloud: "Ollama Cloud",
  openai:       "OpenAI",
  anthropic:    "Anthropic",
  gemini:       "Google Gemini",
  groq:         "Groq",
  openrouter:   "OpenRouter",
};

const PROVIDER_COLORS: Record<string, string> = {
  ollama:       "#6ee7b7",
  ollama_cloud: "#67e8f9",
  openai:       "#a3e635",
  anthropic:    "#fbbf24",
  gemini:       "#60a5fa",
  groq:         "#c084fc",
  openrouter:   "#fb923c",
};

export default function SettingsPage() {
  const [cfg, setCfg]       = useState<LLMSettings | null>(null);
  const [form, setForm]     = useState<Partial<LLMSettings>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting]   = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [saved, setSaved]   = useState(false);

  useEffect(() => {
    getSettings().then(d => { setCfg(d); setForm(d); }).catch(() => {});
  }, []);

  async function save() {
    setSaving(true);
    setSaved(false);
    try {
      await updateSettings(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTesting(true);
    setTestResult(null);
    try {
      await updateSettings(form);
      const res = await testConnection();
      setTestResult({ ok: res.ok, message: res.ok ? "Connection successful!" : res.error || "Connection failed" });
    } finally {
      setTesting(false);
    }
  }

  if (!cfg) return (
    <div className="flex items-center justify-center h-full" style={{ background: "var(--bg-app)" }}>
      <Loader2 className="w-5 h-5 animate-spin" style={{ color: "var(--accent)" }} />
    </div>
  );

  const currentProvider = form.provider || cfg.provider;
  const models = cfg.available_models[currentProvider] || [];

  return (
    <div className="overflow-auto h-full px-8 py-8" style={{ background: "var(--bg-app)" }}>
      <div className="max-w-lg mx-auto fade-up">

        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center overflow-hidden"
            style={{
              border: "1px solid rgba(204,68,0,0.15)",
              boxShadow: "0 2px 10px rgba(204,68,0,0.1)",
            }}
          >
            <img src="/favicon.png" alt="ActInsight" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-widest mb-0.5" style={{ color: "var(--accent-light)", letterSpacing: "0.08em" }}>ActInsight</div>
            <h1 className="text-base font-bold" style={{ color: "var(--text-primary)", fontFamily: "'Noto Serif', serif" }}>Settings</h1>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>Configure your AI model provider for tax law queries</p>
          </div>
        </div>

        {/* LLM card */}
        <div
          className="rounded-xl p-6 mb-4"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)" }}
        >
          {/* Provider pills */}
          <div className="mb-5">
            <label className="block text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
              Provider
            </label>
            <div className="flex flex-wrap gap-2">
              {cfg.available_providers.map(p => {
                const isSelected = currentProvider === p;
                const pColor = PROVIDER_COLORS[p] || "var(--text-secondary)";
                return (
                  <button
                    key={p}
                    onClick={() => {
                      const newKey = (form.provider_api_keys || cfg.provider_api_keys)[p] || "";
                      setForm(f => ({ ...f, provider: p, model: "auto", api_key: newKey, base_url: "" }));
                    }}
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150"
                    style={
                      isSelected
                        ? { background: `${pColor}18`, color: pColor, border: `1px solid ${pColor}44` }
                        : { background: "var(--bg-hover)", color: "var(--text-secondary)", border: "1px solid var(--border-default)" }
                    }
                  >
                    {PROVIDER_LABELS[p] ?? p}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Divider */}
          <div className="mb-5" style={{ borderTop: "1px solid var(--border-faint)" }} />

          {/* Model */}
          <div className="mb-5">
            <label className="block text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
              Model
            </label>
            <div className="flex gap-2">
              <select
                value={form.model || cfg.model}
                onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                className="select-dark flex-1"
              >
                {models.map(m => (
                  <option key={m} value={m}>{m === "auto" ? "Auto (Recommended)" : m}</option>
                ))}
              </select>
              <input
                type="text"
                placeholder="Custom model…"
                value={form.model || ""}
                onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                className="input-field flex-1"
                style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "12px" }}
              />
            </div>
          </div>

          {/* API Key */}
          {currentProvider !== "ollama" && (
            <div className="mb-5">
              {currentProvider === "ollama_cloud" && (
                <div
                  className="mb-3 p-3 rounded-lg text-xs space-y-1.5"
                  style={{ background: "var(--bg-hover)", border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}
                >
                  <p className="font-semibold" style={{ color: "var(--text-primary)" }}>Two modes for Ollama Cloud:</p>
                  <p><span style={{ color: "var(--accent-light)" }}>API Key mode</span> — enter key below, requests go to ollama.com</p>
                  <p><span style={{ color: "var(--green)" }}>Signed-in mode</span> — run <code>ollama signin</code>, leave key empty</p>
                </div>
              )}
              <label className="block text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
                API Key{" "}
                {currentProvider === "ollama_cloud" && (
                  <a href="https://ollama.com/settings/keys" target="_blank" className="normal-case font-normal" style={{ color: "var(--accent-light)" }}>
                    (get key ↗)
                  </a>
                )}
              </label>
              <input
                type="password"
                value={form.api_key || ""}
                onChange={e => {
                  const newKey = e.target.value;
                  setForm(f => {
                    const updatedKeys = { ...(f.provider_api_keys || cfg.provider_api_keys) };
                    updatedKeys[f.provider || cfg.provider] = newKey;
                    return { ...f, api_key: newKey, provider_api_keys: updatedKeys };
                  });
                }}
                placeholder={currentProvider === "ollama_cloud" ? "Leave empty if using ollama signin" : "Paste your API key…"}
                className="input-field"
                style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "12px" }}
              />
              <p className="text-[11px] mt-1.5" style={{ color: "var(--text-muted)" }}>
                Stored server-side in .env — never exposed to the browser
              </p>
            </div>
          )}

          {/* Base URL */}
          {["openrouter", "ollama"].includes(currentProvider) && (
            <div className="mb-5">
              <label className="block text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
                Base URL
              </label>
              <input
                type="text"
                value={form.base_url || ""}
                onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))}
                placeholder="e.g. http://localhost:11434"
                className="input-field"
                style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "12px" }}
              />
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2.5 pt-1">
            <button onClick={save} disabled={saving} className="btn-primary flex items-center gap-2">
              {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              {saved ? "✓ Saved" : "Save Settings"}
            </button>
            <button onClick={test} disabled={testing} className="btn-secondary flex items-center gap-2">
              {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
              Test Connection
            </button>
          </div>

          {/* Test result */}
          {testResult && (
            <div
              className="mt-4 p-4 rounded-xl text-sm"
              style={
                testResult.ok
                  ? { background: "rgba(45,212,171,0.08)", color: "var(--green)", border: "1px solid rgba(45,212,171,0.2)" }
                  : { background: "rgba(248,113,113,0.08)", color: "var(--red)", border: "1px solid rgba(248,113,113,0.2)" }
              }
            >
              <div className="flex items-center gap-2 font-semibold mb-1">
                {testResult.ok ? <CheckCircle className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                {testResult.ok ? "Connected" : "Connection Failed"}
              </div>
              {!testResult.ok && (
                <p className="text-xs opacity-90">{formatError(testResult.message)}</p>
              )}
            </div>
          )}
        </div>

        {/* Info card */}
        <div
          className="rounded-xl p-5"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)" }}
        >
          <h3 className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
            Provider Notes
          </h3>
          <div className="space-y-2.5 text-xs" style={{ color: "var(--text-secondary)" }}>
            {[
              { key: "ollama",     label: "Ollama (Local)", note: 'Free, on-machine. Start with: ollama serve' },
              { key: "anthropic",  label: "Anthropic",      note: "Claude — best at legal reasoning & structured answers" },
              { key: "openai",     label: "OpenAI",         note: "GPT-4o — strong citation accuracy for tax law" },
              { key: "groq",       label: "Groq",           note: "Fast inference, great for quick section lookups" },
              { key: "openrouter", label: "OpenRouter",     note: "Access 100+ models with one API key" },
            ].map(({ key, label, note }) => (
              <div key={key} className="flex gap-2">
                <div
                  className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
                  style={{ background: PROVIDER_COLORS[key] || "var(--text-muted)" }}
                />
                <div>
                  <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{label}</span>
                  <span style={{ color: "var(--text-muted)" }}> — {note}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
