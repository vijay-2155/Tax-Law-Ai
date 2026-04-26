import { type ChatSource } from "./api";

// Assuming we mirror the Message type from ChatPage.tsx here
export interface Message {
  role: "user" | "assistant";
  content: string;         // final answer (no thinking)
  thinking?: string;       // raw thinking trace, optional
  sources?: ChatSource[];
  rewritten?: string | null;
}

export interface ChatSession {
  id: string;
  title: string;
  act: string;
  messages: Message[];
  updatedAt: number;
}

const STORAGE_KEY = "tax_validator_chat_history";

export function getHistory(): ChatSession[] {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    if (!data) return [];
    const parsed = JSON.parse(data) as ChatSession[];
    return parsed.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch (e) {
    console.error("Failed to load chat history", e);
    return [];
  }
}

export function saveSession(session: ChatSession) {
  try {
    const history = getHistory();
    const existingIndex = history.findIndex(s => s.id === session.id);
    if (existingIndex >= 0) {
      history[existingIndex] = session;
    } else {
      history.push(session);
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch (e) {
    console.error("Failed to save chat session", e);
  }
}

export function deleteSession(id: string) {
  try {
    const history = getHistory();
    const filtered = history.filter(s => s.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  } catch (e) {
    console.error("Failed to delete chat session", e);
  }
}
