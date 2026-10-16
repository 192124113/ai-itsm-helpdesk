export interface Source {
  id: string;
  title: string;
  category: string;
  score: number;
  snippet: string;
}

export interface Step {
  step: string;
  status: "done" | "failed" | "skipped";
  detail: string;
  at: string;
}

export interface TicketRef {
  number: string;
  type: "incident" | "request";
  state?: string | null;
  link?: string | null;
}

export interface Analysis {
  intent: string;
  intent_label: string;
  category: string;
  subcategory: string;
  priority: string;
  impact: string;
  urgency: string;
  assignment_group: string;
  summary: string;
  suggested_resolution: string;
  confidence: number;
  classification_method: string;
  sources: Source[];
  rag_confidence: number | null;
  automation: {
    key: string;
    label: string;
    status: string;
    validated: boolean;
    api_call?: string;
    action_id?: string;
  } | null;
  servicenow: TicketRef | null;
  escalated: boolean;
  workflow: string;
  threshold: number;
}

export interface SoftwareRequest {
  request_id: string;
  software: string;
  version: string;
  user_id: string;
  status: string;
  job_id: string;
  target: string;
  created_at: string;
  updated_at: string;
}

export interface ChatEntry {
  id: string;
  created_at: string;
  user_id?: string;
  message: string;
  reply: string;
  analysis: Analysis;
  ticket: TicketRef | null;
  steps: Step[] | null;
  software_request: SoftwareRequest | null;
  escalation_suggested: boolean;
}

export interface Ticket {
  number: string;
  type: "incident" | "request";
  short_description: string;
  category: string;
  subcategory: string;
  priority: string;
  assignment_group: string;
  user_id: string;
  status: string;
  state_label?: string;
  ai_resolved: boolean;
  escalated: boolean;
  automation: boolean;
  created_at: string;
  link?: string;
}

export interface AutomationAction {
  id: string;
  automation: string;
  label: string;
  user_id: string;
  api_call: string;
  result: string;
  status: string;
  validated: boolean;
  ticket_number: string | null;
  started_at: string;
}

export interface AuditEntry {
  id: string;
  ts: string;
  event: string;
  actor: string;
  ref: string | null;
  details: Record<string, unknown>;
}

export interface Stats {
  tickets: {
    total: number;
    open: number;
    resolved: number;
    ai_resolved: number;
    escalated: number;
    incidents: number;
    requests: number;
  };
  software_requests: { total: number; by_status: Record<string, number> };
  automation: { total: number; success: number; failed: number; success_rate: number | null };
  conversations: { total: number; by_intent: Record<string, number> };
  automation_catalogue: { key: string; label: string; safe: boolean }[];
}

export interface Article {
  id: string;
  title: string;
  category: string;
  file: string;
  content: string;
  chunks: number;
}

export interface Hit {
  doc_id: string;
  title: string;
  category: string;
  heading: string;
  text: string;
  score: number;
}

export interface RagAnswer {
  answered: boolean;
  answer: string;
  sources: Source[];
  confidence: number;
  mode: string;
  relevance: number;
}

export interface User {
  user_id: string;
  name: string;
  department: string;
}

export interface Health {
  status: string;
  database: string;
  servicenow: string;
  llm: string;
  embedder: string;
  vector_store: string;
  knowledge_documents: number;
  knowledge_chunks: number;
  confidence_threshold: number;
}
