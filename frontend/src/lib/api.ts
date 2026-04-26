const BASE = "/api";

export interface SearchResult {
  section: string;
  section_title: string;
  act_year: string;
  chapter: string;
  chapter_title: string;
  income_head: string;
  score: number;
  preview: string;
  page_start: number;
}

export interface Chunk {
  chunk_id: string;
  section: string;
  section_title: string;
  act_year: string;
  chapter: string;
  chapter_title: string;
  part: string;
  income_head: string;
  chunk_index: number;
  chunk_type: string;   // "section" | "subsection"
  text: string;
  page_start: number;
  page_end: number;
  score?: number;
}

export interface SectionDetail {
  section: string;
  section_title: string;
  act_year: string;
  chapter: string;
  chapter_title: string;
  income_head: string;
  page_start: number;
  page_end: number;
  chunk_count: number;
  chunks: Chunk[];
  summary?: string;
  examples?: string;
}

export interface ChatSource {
  section: string | null;
  section_title: string;
  act_year: string;   // "1961" | "2025" | "web"
  income_head: string;
  chunk_type: string; // "section" | "subsection" | "web"
  score: number;
  url?: string;       // present when chunk_type === "web"
}

export interface IncomeHead {
  name: string;
  section_count: number;
  slug: string;
}

export interface LLMSettings {
  provider: string;
  model: string;
  api_key: string;
  base_url: string;
  provider_api_keys: Record<string, string>;
  available_providers: string[];
  available_models: Record<string, string[]>;
}

/**
 * Parses raw LLM / API error blobs into human-readable messages.
 */
export function formatError(msg: string): string {
  if (!msg) return "An unexpected error occurred.";
  
  // Extract 'message' from JSON-like blobs
  const match = msg.match(/'message':\s*'([^']+)'/) || msg.match(/"message":\s*"([^"]+)"/);
  if (match && match[1]) return match[1];

  // Map common technical errors
  if (msg.includes("RESOURCE_EXHAUSTED")) return "API quota exceeded (Rate Limit). Please wait a few seconds or upgrade your plan.";
  if (msg.includes("Request too large") || msg.includes("TPM") || msg.includes("limit_exceeded")) {
    return "The combined length of law sections is too large for your current model quota. Try asking a more specific question or upgrade your LLM tier.";
  }
  if (msg.includes("API_KEY_INVALID") || msg.includes("invalid_api_key")) return "Invalid API Key. Please check your credentials in settings.";
  if (msg.includes("ECONNREFUSED")) return "Cannot connect to local Ollama. Please ensure it is running (`ollama serve`).";
  if (msg.includes("model not found") || msg.includes("404")) return "The selected model is missing. Please download it or choose another.";
  
  return msg;
}

// ── Search ──────────────────────────────────────────────────────────────────

export async function searchSections(
  q: string,
  act = "2025",
  topK = 10,
): Promise<{ results: SearchResult[]; total: number }> {
  const res = await fetch(`${BASE}/sections/search?q=${encodeURIComponent(q)}&act=${act}&top_k=${topK}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function autocomplete(
  q: string,
  act = "2025",
): Promise<{ suggestions: { section: string; section_title: string; act_year: string; income_head: string }[] }> {
  const res = await fetch(`${BASE}/sections/autocomplete?q=${encodeURIComponent(q)}&act=${act}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Section detail ───────────────────────────────────────────────────────────

export async function getSection(act: string, number: string): Promise<SectionDetail> {
  const res = await fetch(`${BASE}/sections/${act}/${encodeURIComponent(number)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSectionMapping(act: string, number: string) {
  const res = await fetch(`${BASE}/sections/${act}/${encodeURIComponent(number)}/mapping`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface EquivalentMeta {
  section: string;
  section_title: string;
  act_year: string;
  income_head: string;
  chapter_title: string;
  confidence: number;
  preview: string;
}

export interface SectionEquivalent {
  source: { section: string; section_title: string; act_year: string; income_head: string; chapter_title: string };
  equivalent: EquivalentMeta | null;
  analysis: string | null;
}

export async function getSectionEquivalent(act: string, number: string): Promise<SectionEquivalent> {
  const res = await fetch(`${BASE}/sections/${act}/${encodeURIComponent(number)}/equivalent`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSectionSummary(act: string, number: string, force = false): Promise<{ summary: string }> {
  const url = `${BASE}/sections/${act}/${encodeURIComponent(number)}/summary${force ? "?force=true" : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Income Heads ─────────────────────────────────────────────────────────────

export async function getHeads(act = "2025"): Promise<{ heads: IncomeHead[] }> {
  const res = await fetch(`${BASE}/heads?act=${act}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSectionsByHead(
  headSlug: string,
  act = "2025",
  limit = 50,
): Promise<{ sections: SearchResult[]; total: number; head: string }> {
  const res = await fetch(`${BASE}/heads/${headSlug}/sections?act=${act}&limit=${limit}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export async function* streamChat(
  question: string,
  actYear: string,
  chatHistory: ChatMessage[],
): AsyncGenerator<string> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, act_year: actYear, chat_history: chatHistory }),
  });
  if (!res.ok) throw new Error(await res.text());

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    yield decoder.decode(value, { stream: true });
  }
}

// ── Settings ─────────────────────────────────────────────────────────────────

export async function getSettings(): Promise<LLMSettings> {
  const res = await fetch(`${BASE}/settings`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateSettings(data: Partial<LLMSettings>): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function testConnection(): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${BASE}/settings/test`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
