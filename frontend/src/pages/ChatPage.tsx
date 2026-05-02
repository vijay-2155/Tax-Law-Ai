import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import Markdown from "../components/Markdown";
import {
  Send, Loader2, Trash2, ExternalLink, ChevronDown,
  User, BookOpen, TrendingUp, FileText,
  Brain, Copy, RefreshCw, Check, MessageSquare, Plus, Globe,
  IndianRupee, Scale,
} from "lucide-react";
import { streamChat, getSettings, updateSettings, formatError, type ChatMessage, type ChatSource, type LLMSettings } from "../lib/api";
import { getHistory, saveSession, deleteSession, type ChatSession, type Message } from "../lib/history";
import ActToggle from "../components/ActToggle";



// ── Thinking panel ────────────────────────────────────────────────────────────

function ThinkingPanel({ thinking, streaming }: { thinking: string; streaming?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="mb-4 rounded-xl overflow-hidden"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)" }}
    >
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 w-full px-4 py-2.5 text-left text-xs transition-colors"
        style={{ color: "var(--text-muted)" }}
        onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
      >
        <Brain
          className={`w-3.5 h-3.5 ${streaming ? "animate-pulse" : ""}`}
          style={{ color: streaming ? "var(--accent-light)" : "var(--text-muted)" }}
        />
        <span className="font-medium">{streaming ? "Thinking…" : "Thought process"}</span>
        <ChevronDown
          className={`w-3 h-3 ml-auto transition-transform ${open ? "rotate-180" : ""}`}
          style={{ color: "var(--text-muted)" }}
        />
      </button>
      {open && (
        <div className="px-4 pb-3" style={{ borderTop: "1px solid var(--border-faint)" }}>
          <p
            className="text-xs font-mono leading-relaxed whitespace-pre-wrap pt-3 max-h-64 overflow-auto"
            style={{ color: "var(--text-muted)" }}
          >
            {thinking}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Source chips ──────────────────────────────────────────────────────────────

function SourceChips({ sources }: { sources: ChatSource[] }) {
  if (!sources.length) return null;
  const unique = sources.filter((s, i, arr) =>
    arr.findIndex(x => x.section === s.section && x.act_year === s.act_year) === i
  );
  const lawSources = unique.filter(s => s.act_year !== "web");
  const webSources = unique.filter(s => s.act_year === "web");
  return (
    <div className="flex flex-wrap gap-1.5 mt-4 pt-3" style={{ borderTop: "1px solid var(--border-faint)" }}>
      <span className="w-full text-xs mb-1" style={{ color: "var(--text-muted)" }}>Sources</span>
      {lawSources.slice(0, 8).map((s, i) => (
        <Link
          key={i}
          to={`/section/${s.act_year}/${s.section}`}
          className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg transition-all"
          style={{
            background: "var(--accent-dim)",
            color: "var(--accent-light)",
            border: "1px solid var(--border-accent)",
            fontFamily: "'JetBrains Mono', monospace",
          }}
          onMouseEnter={e => (e.currentTarget.style.background = "rgba(74,139,255,0.14)")}
          onMouseLeave={e => (e.currentTarget.style.background = "var(--accent-dim)")}
        >
          #{s.section}
          <span style={{ color: "var(--text-muted)", fontFamily: "inherit" }}>({s.act_year})</span>
          <ExternalLink className="w-2.5 h-2.5 opacity-70" />
        </Link>
      ))}
      {webSources.slice(0, 4).map((s, i) => (
        <a
          key={`web-${i}`}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          title={s.section_title}
          className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg transition-all max-w-[220px]"
          style={{
            background: "rgba(34,211,238,0.07)",
            color: "var(--text-secondary)",
            border: "1px solid rgba(34,211,238,0.2)",
          }}
          onMouseEnter={e => { e.currentTarget.style.background = "rgba(34,211,238,0.13)"; e.currentTarget.style.color = "var(--text-primary)"; }}
          onMouseLeave={e => { e.currentTarget.style.background = "rgba(34,211,238,0.07)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
        >
          <Globe className="w-2.5 h-2.5 shrink-0" style={{ color: "#22d3ee" }} />
          <span className="truncate">{s.section_title || "Web"}</span>
          <ExternalLink className="w-2.5 h-2.5 shrink-0 opacity-60" />
        </a>
      ))}
    </div>
  );
}

// ── Message bubbles ───────────────────────────────────────────────────────────

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end gap-3 group">
      <div className="max-w-[72%]">
        <div
          className="rounded-2xl rounded-br-md px-5 py-3.5 text-sm leading-relaxed"
          style={{
            background: "#eef2fb",
            color: "var(--text-primary)",
            border: "1px solid #dde3f0",
          }}
        >
          {content}
        </div>
      </div>
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5"
        style={{ background: "linear-gradient(135deg, #1a3a8f, #2452b8)" }}
      >
        <User className="w-4 h-4 text-white" />
      </div>
    </div>
  );
}

function AssistantBubble({
  msg, streamingThinking, onRegenerate,
}: {
  msg: Message; streamingThinking?: boolean; onRegenerate?: () => void;
}) {
  const hasThinking = !!(msg.thinking?.trim());
  const hasContent = !!(msg.content?.trim());
  const isError = msg.content?.includes("⚠️ Error:");
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex gap-3 group">
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5"
        style={{
          width: "32px", height: "32px",
          borderRadius: "50%",
          overflow: "hidden",
          flexShrink: 0,
          marginTop: "2px",
          border: "1.5px solid rgba(204,68,0,0.2)",
          boxShadow: "0 1px 6px rgba(204,68,0,0.12)",
        }}
      >
        <img src="/favicon.png" alt="AI" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </div>
      <div className="flex-1 min-w-0">
        {hasThinking && (
          <ThinkingPanel thinking={msg.thinking!} streaming={streamingThinking && !hasContent} />
        )}

        {hasContent ? (
          <div
            className={`prose-chat text-sm ${isError ? "p-4 rounded-2xl" : ""}`}
            style={isError ? {
              background: "rgba(248,113,113,0.08)",
              color: "var(--red)",
              border: "1px solid rgba(248,113,113,0.2)",
            } : {}}
          >
            <Markdown>{msg.content}</Markdown>
          </div>
        ) : !hasThinking ? (
          <span className="flex items-center gap-2 mt-1" style={{ color: "var(--text-muted)" }}>
            <span className="inline-flex gap-0.5">
              {[0, 150, 300].map(delay => (
                <span
                  key={delay}
                  className="w-1.5 h-1.5 rounded-full animate-bounce"
                  style={{ background: "var(--text-muted)", animationDelay: `${delay}ms` }}
                />
              ))}
            </span>
          </span>
        ) : null}

        {msg.sources && <SourceChips sources={msg.sources} />}

        {hasContent && (
          <div
            className="flex items-center gap-2 mt-3 pt-2 opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ borderTop: "1px solid var(--border-faint)" }}
          >
            <button
              title="Copy"
              onClick={handleCopy}
              className="p-1.5 rounded-md transition-colors"
              style={{ color: "var(--text-muted)" }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--text-primary)"; e.currentTarget.style.background = "var(--bg-hover)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--text-muted)"; e.currentTarget.style.background = "transparent"; }}
            >
              {copied
                ? <Check className="w-3.5 h-3.5" style={{ color: "var(--green)" }} />
                : <Copy className="w-3.5 h-3.5" />}
            </button>
            {onRegenerate && (
              <button
                title="Regenerate"
                onClick={onRegenerate}
                className="p-1.5 rounded-md transition-colors"
                style={{ color: "var(--text-muted)" }}
                onMouseEnter={e => { e.currentTarget.style.color = "var(--text-primary)"; e.currentTarget.style.background = "var(--bg-hover)"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "var(--text-muted)"; e.currentTarget.style.background = "transparent"; }}
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Model Selector ────────────────────────────────────────────────────────────

const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama", ollama_cloud: "Ollama Cloud",
  openai: "OpenAI", anthropic: "Anthropic",
  gemini: "Gemini", groq: "Groq", openrouter: "OpenRouter",
};

function ModelSelector({
  settings, onSelect, currentModel,
}: { settings: LLMSettings | null; onSelect: (p: string, m: string) => void; currentModel: string }) {
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

  const provider = settings.provider;
  const displayModel = currentModel || settings.model || "Select model";
  const labelModel = displayModel === "auto" ? "Auto" : displayModel;
  const shortModel = labelModel.length > 20 ? labelModel.slice(0, 20) + "…" : labelModel;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-all"
        style={{
          background: "var(--bg-hover)",
          color: "var(--text-secondary)",
          border: "1px solid var(--border-default)",
        }}
        onMouseEnter={e => (e.currentTarget.style.color = "var(--text-primary)")}
        onMouseLeave={e => (e.currentTarget.style.color = "var(--text-secondary)")}
      >
        <span className="font-medium" style={{ color: "var(--text-primary)" }}>
          {PROVIDER_LABELS[provider] ?? provider}
        </span>
        <span style={{ color: "var(--border-default)" }}>/</span>
        <span>{shortModel}</span>
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          className="absolute bottom-full mb-2 left-0 w-72 rounded-xl z-50 overflow-hidden"
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border-default)",
            boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
          }}
        >
          <div className="max-h-72 overflow-y-auto">
            {settings.available_providers.map(p => (
              <div key={p} style={{ borderBottom: "1px solid var(--border-faint)" }}>
                <div
                  className="px-3 py-1.5 flex items-center justify-between"
                  style={{ background: "var(--bg-card)" }}
                >
                  <span
                    className="text-[10px] font-bold uppercase tracking-widest"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {PROVIDER_LABELS[p] ?? p}
                  </span>
                  {p === settings.provider && (
                    <span className="text-[10px] font-semibold" style={{ color: "var(--accent-light)" }}>
                      Active
                    </span>
                  )}
                </div>
                {(settings.available_models[p] || []).map(m => (
                  <button
                    key={`${p}-${m}`}
                    onClick={() => { onSelect(p, m); setOpen(false); }}
                    className="w-full text-left px-3 py-2 text-xs transition-colors flex items-center justify-between gap-2"
                    style={{
                      background: (p === settings.provider && m === (currentModel || settings.model))
                        ? "var(--bg-active)"
                        : "transparent",
                      color: (p === settings.provider && m === (currentModel || settings.model))
                        ? "var(--accent-light)"
                        : "var(--text-secondary)",
                    }}
                    onMouseEnter={e => {
                      if (!(p === settings.provider && m === (currentModel || settings.model))) {
                        e.currentTarget.style.background = "var(--bg-hover)";
                        e.currentTarget.style.color = "var(--text-primary)";
                      }
                    }}
                    onMouseLeave={e => {
                      if (!(p === settings.provider && m === (currentModel || settings.model))) {
                        e.currentTarget.style.background = "transparent";
                        e.currentTarget.style.color = "var(--text-secondary)";
                      }
                    }}
                  >
                    <span className="truncate">{m === "auto" ? "Auto (Recommended)" : m}</span>
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

// ── Starter prompts ───────────────────────────────────────────────────────────

const STARTERS = [
  { icon: FileText,      text: "What is the TDS rate for contractors under the 2025 Act?" },
  { icon: BookOpen,      text: "Explain Section 80C deductions with applicable limits" },
  { icon: TrendingUp,    text: "What are capital gains exemptions for residential property?" },
  { icon: Scale,         text: "Compare advance tax provisions in 1961 vs 2025 Act" },
  { icon: IndianRupee,   text: "New tax regime vs old regime — which is better for salaried?" },
  { icon: BookOpen,      text: "What is the surcharge on income above ₹50 lakh?" },
];

// ── Think/content splitter ────────────────────────────────────────────────────

function splitThinkingFromContent(raw: string): { thinking: string; content: string } {
  const thinkTagRe = /<think>([\s\S]*?)<\/think>/gi;
  const thinkMatches = [...raw.matchAll(thinkTagRe)];
  if (thinkMatches.length > 0) {
    return {
      thinking: thinkMatches.map(m => m[1]).join("").trim(),
      content: raw.replace(thinkTagRe, "").trim(),
    };
  }
  return { thinking: "", content: raw };
}


// ── Main page ─────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [act, setAct] = useState<string>("both");
  const [streaming, setStreaming] = useState(false);
  const [streamingIdx, setStreamingIdx] = useState<number>(-1);
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [currentModel, setCurrentModel] = useState("");

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function autogrow(el: HTMLTextAreaElement | null) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => { setSessions(getHistory()); }, []);

  useEffect(() => {
    getSettings().then(s => { setSettings(s); setCurrentModel(s.model); }).catch(() => {});
  }, []);

  function handleNewChat() {
    setCurrentSessionId(null);
    setMessages([]);
    setInput("");
  }

  function loadSession(s: ChatSession) {
    if (streaming) return;
    setCurrentSessionId(s.id);
    setMessages(s.messages);
    setAct(s.act);
  }

  function handleDeleteSession(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    deleteSession(id);
    const updated = getHistory();
    setSessions(updated);
    if (currentSessionId === id) handleNewChat();
  }

  function saveCurrentToHistory(finalMessages: Message[]) {
    let id = currentSessionId;
    if (!id) {
      id = "session_" + Date.now();
      setCurrentSessionId(id);
    }
    const first = finalMessages[0]?.content || "";
    const title = first.slice(0, 40) + (first.length > 40 ? "…" : "") || "New Chat";
    saveSession({ id, title, act, messages: finalMessages, updatedAt: Date.now() });
    setSessions(getHistory());
  }

  async function handleLlmChange(provider: string, model: string) {
    setCurrentModel(model);
    if (settings) {
      await updateSettings({ provider, model }).catch(() => {});
      setSettings(prev => prev ? { ...prev, provider, model } : prev);
    }
  }

  async function generateResponse(q: string, history: ChatMessage[], assistantIdx: number, baseMessages: Message[]) {
    setStreaming(true);
    setStreamingIdx(assistantIdx);
    setMessages([...baseMessages, { role: "assistant", content: "", thinking: "" }]);

    try {
      let rawBuffer = "";
      let sources: ChatSource[] = [];
      let finalised = false;

      for await (const chunk of streamChat(q, act, history)) {
        rawBuffer += chunk;
        const doneMatch = rawBuffer.match(/(\n\n)(\{\s*"done"\s*:\s*true[\s\S]*\}\s*)$/);
        if (doneMatch && !finalised) {
          const splitAt = rawBuffer.lastIndexOf(doneMatch[0]);
          const textPart = rawBuffer.slice(0, splitAt);
          try {
            const meta = JSON.parse(doneMatch[2].trim());
            sources = meta.sources || [];
            rawBuffer = meta.error ? `⚠️ Error: ${meta.error}\n\nPlease check your LLM settings.` : textPart;
          } catch {
            rawBuffer = textPart;
          }
          finalised = true;
        }

        const { thinking, content } = splitThinkingFromContent(rawBuffer);
        setMessages(prev => {
          const updated = [...prev];
          updated[assistantIdx] = { role: "assistant", thinking, content, sources };
          return updated;
        });
      }

      setMessages(prev => {
        const updated = [...prev];
        updated[assistantIdx] = { ...updated[assistantIdx], sources };
        saveCurrentToHistory(updated);
        return updated;
      });
    } catch (e: any) {
      setMessages(prev => {
        const updated = [...prev];
        updated[assistantIdx] = { role: "assistant", content: `⚠️ Error: ${formatError(e.message)}`, thinking: "" };
        return updated;
      });
    } finally {
      setStreaming(false);
      setStreamingIdx(-1);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }

  async function sendMessage(text?: string) {
    const q = (text ?? input).trim();
    if (!q || streaming) return;

    const userMsg: Message = { role: "user", content: q };
    const baseMsgs = [...messages, userMsg];
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const history = messages.map(m => ({ role: m.role, content: m.content }));
    generateResponse(q, history, baseMsgs.length, baseMsgs);
  }

  async function handleRegenerate(index: number) {
    if (streaming) return;
    const userMsg = messages[index - 1];
    if (!userMsg || userMsg.role !== "user") return;

    const baseMsgs = messages.slice(0, index);
    const history = baseMsgs.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
    generateResponse(userMsg.content, history, index, baseMsgs);
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full w-full" style={{ background: "var(--bg-app)" }}>

      {/* ── History Sidebar ── */}
      <div
        className="w-60 flex flex-col shrink-0 h-full"
        style={{ background: "var(--bg-surface)", borderRight: "1px solid var(--border-subtle)" }}
      >
        {/* New chat button */}
        <div className="p-3" style={{ borderBottom: "1px solid var(--border-faint)" }}>
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-2 btn-primary text-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            New Chat
          </button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto py-2 px-2">
          {sessions.length === 0 ? (
            <div className="flex flex-col items-center pt-10 gap-2">
              <MessageSquare className="w-6 h-6" style={{ color: "var(--border-default)" }} />
              <p className="text-xs text-center" style={{ color: "var(--text-muted)" }}>
                No saved chats yet
              </p>
            </div>
          ) : (
            <div className="space-y-0.5">
              {sessions.map(s => {
                const isActive = s.id === currentSessionId;
                return (
                  <div
                    key={s.id}
                    onClick={() => loadSession(s)}
                    className="group flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-all text-sm"
                    style={{
                      background: isActive ? "var(--bg-active)" : "transparent",
                      borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                    }}
                    onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = "var(--bg-hover)"; }}
                    onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
                  >
                    <div className="flex flex-col overflow-hidden">
                      <span
                        className="truncate text-xs font-medium pr-1"
                        style={{ color: isActive ? "var(--text-primary)" : "var(--text-secondary)" }}
                      >
                        {s.title}
                      </span>
                      <span
                        className="text-[10px] mt-0.5 font-mono"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {new Date(s.updatedAt).toLocaleDateString()}
                      </span>
                    </div>
                    <button
                      onClick={(e) => handleDeleteSession(s.id, e)}
                      title="Delete"
                      className="shrink-0 p-1 rounded transition-all opacity-0 group-hover:opacity-100"
                      style={{ color: "var(--text-muted)" }}
                      onMouseEnter={e => { e.currentTarget.style.color = "var(--red)"; e.currentTarget.style.background = "rgba(248,113,113,0.08)"; }}
                      onMouseLeave={e => { e.currentTarget.style.color = "var(--text-muted)"; e.currentTarget.style.background = "transparent"; }}
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Main Chat Area ── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Top bar */}
        <div
          className="flex items-center justify-between px-6 py-3 shrink-0"
          style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-subtle)" }}
        >
          <div className="flex items-center gap-2.5">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center"
              style={{
                width: "28px", height: "28px",
                borderRadius: "10px",
                overflow: "hidden",
                border: "1px solid rgba(204,68,0,0.15)",
                boxShadow: "0 1px 6px rgba(204,68,0,0.1)",
              }}
            >
              <img src="/favicon.png" alt="ActInsight" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            </div>
            <span className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
              ActInsight AI
            </span>
          </div>
          <div className="flex items-center gap-3">
            <ActToggle value={act} onChange={setAct} />
            {!isEmpty && (
              <button
                onClick={handleNewChat}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all"
                style={{ color: "var(--text-muted)" }}
                onMouseEnter={e => { e.currentTarget.style.color = "var(--text-primary)"; e.currentTarget.style.background = "var(--bg-hover)"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "var(--text-muted)"; e.currentTarget.style.background = "transparent"; }}
              >
                <Trash2 className="w-3.5 h-3.5" />
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 pt-10">
          <div className="max-w-4xl mx-auto space-y-10 pb-32">
            {isEmpty ? (
              <div className="flex flex-col items-center justify-center h-full px-6 pb-24 fade-up">
                <div
                  style={{
                    width: "80px", height: "80px",
                    borderRadius: "20px",
                    overflow: "hidden",
                    border: "1px solid rgba(204,68,0,0.15)",
                    boxShadow: "0 4px 24px rgba(204,68,0,0.12)",
                    flexShrink: 0,
                    marginBottom: "20px",
                  }}
                >
                  <img src="/logo.png" alt="ActInsight" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                </div>
                <h1
                  className="text-2xl font-bold mb-1 text-center"
                  style={{ color: "var(--text-primary)", letterSpacing: "-0.02em", fontFamily: "'Noto Serif', serif" }}
                >
                  Ask anything about Indian Tax Law
                </h1>
                <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--accent-light)" }}>
                  ActInsight · Income Tax Intelligence
                </p>
                <p className="text-sm mb-10 max-w-md text-center leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  Grounded in IT Act 1961 &amp; IT Act 2025 — precise section citations, no hallucinations
                </p>
                <div className="grid grid-cols-2 gap-2.5 w-full max-w-2xl">
                  {STARTERS.map(({ icon: Icon, text }) => (
                    <button
                      key={text}
                      onClick={() => sendMessage(text)}
                      className="card-hover flex items-start gap-3 text-left text-sm px-4 py-3.5"
                      style={{ borderLeft: "2px solid rgba(204,68,0,0.25)" }}
                    >
                      <Icon className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "var(--accent)" }} />
                      <span className="leading-snug line-clamp-2" style={{ color: "var(--text-secondary)" }}>
                        {text}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg, i) =>
                  msg.role === "user"
                    ? <UserBubble key={i} content={msg.content} />
                    : <AssistantBubble
                        key={i}
                        msg={msg}
                        streamingThinking={streaming && i === streamingIdx}
                        onRegenerate={i === messages.length - 1 ? () => handleRegenerate(i) : undefined}
                      />
                )}
                <div ref={bottomRef} />
              </>
            )}
          </div>
        </div>

        {/* Input area */}
        <div className={`px-6 shrink-0 ${isEmpty ? "pb-24" : "pb-6"}`}>
          <div className="max-w-4xl mx-auto w-full">
            <div
              className="relative rounded-2xl transition-all"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border-default)",
                boxShadow: "0 2px 16px rgba(0,0,0,0.08)",
              }}
              onFocusCapture={e => (e.currentTarget.style.borderColor = "var(--border-accent)")}
              onBlurCapture={e => (e.currentTarget.style.borderColor = "var(--border-default)")}
            >
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => { setInput(e.target.value); autogrow(e.target); }}
                onKeyDown={handleKey}
                placeholder="Ask about any section, deduction, or tax provision…"
                rows={1}
                className="w-full bg-transparent resize-none px-5 pt-4 pb-3 text-sm leading-relaxed focus:outline-none"
                style={{
                  color: "var(--text-primary)",
                  minHeight: "52px",
                  maxHeight: "200px",
                }}
              />
              <div className="flex items-center justify-between px-3 pb-3 gap-2">
                <ModelSelector settings={settings} currentModel={currentModel} onSelect={handleLlmChange} />
                <div className="flex items-center gap-2">
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>⏎ send · ⇧⏎ newline</span>
                  <button
                    onClick={() => sendMessage()}
                    disabled={!input.trim() || streaming}
                    className="flex items-center justify-center w-9 h-9 rounded-xl transition-all"
                    style={{
                      background: input.trim() && !streaming ? "var(--accent)" : "var(--bg-hover)",
                      color: input.trim() && !streaming ? "#fff" : "var(--text-muted)",
                      boxShadow: input.trim() && !streaming ? "0 2px 12px var(--accent-glow)" : "none",
                    }}
                  >
                    {streaming
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : <Send className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </div>
            <p className="text-center text-xs mt-2" style={{ color: "var(--text-muted)" }}>
              AI may make errors. Always verify with a qualified CA / Tax Advocate before filing.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
