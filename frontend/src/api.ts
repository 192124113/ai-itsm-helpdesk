import type {
  Article, AuditEntry, AutomationAction, ChatEntry, Health, Hit, RagAnswer,
  SoftwareRequest, Stats, Ticket, TicketRef, User,
} from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  users: () => request<User[]>("/api/users"),
  resetDemo: () => request<{ status: string }>("/api/demo/reset", { method: "POST" }),

  chat: (user_id: string, message: string) =>
    request<ChatEntry>("/api/chat", { method: "POST", body: JSON.stringify({ user_id, message }) }),
  history: (user_id: string) =>
    request<ChatEntry[]>(`/api/chat/history?user_id=${encodeURIComponent(user_id)}`),
  analyses: () => request<ChatEntry[]>("/api/analyses"),
  escalate: (user_id: string, message: string, chat_id: string) =>
    request<{ ticket: TicketRef; reply: string }>("/api/tickets/escalate", {
      method: "POST",
      body: JSON.stringify({ user_id, message, chat_id }),
    }),

  tickets: () => request<Ticket[]>("/api/tickets"),
  dashboard: () => request<Stats>("/api/dashboard"),
  actions: () => request<AutomationAction[]>("/api/automation/actions"),
  audit: () => request<AuditEntry[]>("/api/audit?limit=25"),
  softwareRequests: () => request<SoftwareRequest[]>("/api/software/requests"),

  articles: () => request<Article[]>("/api/kb/articles"),
  kbSearch: (q: string) => request<Hit[]>(`/api/kb/search?q=${encodeURIComponent(q)}&k=5`),
  kbAsk: (question: string) =>
    request<RagAnswer>("/api/kb/ask", { method: "POST", body: JSON.stringify({ question }) }),
};
