/* MiniCoder Brain API client — talks to `minicoder serve` (FastAPI).
 * Every call fails soft: the panel detects offline state and says so,
 * instead of pretending to work. */

export interface BrainStatus {
  state: 'awake' | 'thinking' | 'tool_execution' | 'sleeping' | 'github_training' | string;
  started_at: string;
  provider: { default: string; gemini_configured: boolean; llama_cpp_available: boolean; note: string };
  working_memory: { load: number; items: number; capacity: number };
  memory_counts: Record<string, number>;
  hardware: Record<string, unknown>;
}

export interface Episode {
  id: string; situation: string; modality: string; objective: string; result: string;
  verification_status: 'VERIFIED' | 'UNVERIFIED' | 'FAILED' | string;
  lessons: string[]; tags: string[]; confidence: number; created_at: string;
}

export interface Skill {
  id: string; name: string; description: string; domain: string;
  verification_status: 'VERIFIED' | 'UNVERIFIED' | 'FAILED' | string;
  confidence: number; times_used: number; created_at: string;
  reasoning_trace: string[]; final_output: string;
  verification: { name: string; command: string; exit_code: number; passed: boolean }[];
}

export interface ChatResponse {
  reply: string; route: string; confidence: number;
  citations: string[]; episode_id: string | null;
}

export interface SleepReport {
  id: string; trigger: string; started_at: string; finished_at: string;
  episodes_reviewed: number; lessons_consolidated: number; concepts_linked: number;
  duplicates_merged: number; conflicts_flagged: number; episodes_archived: number;
  skills_compiled: number; skills_reverified: number; shard_path: string | null;
  shard_examples: number; shard_sha256: string | null; github_dispatch: string;
  weakness_domains: string[]; unresolved: string[]; notes: string[];
}

export interface GraphPayload {
  nodes: { id: string; label: string; kind: string; confidence: number }[];
  edges: { src: string; dst: string; relation: string; confidence: number }[];
  total_nodes: number; total_edges: number;
}

export class BrainOfflineError extends Error {
  constructor(message = 'Brain backend unreachable') { super(message); this.name = 'BrainOfflineError'; }
}

const BASE = '/api/brain';

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch (e) {
    throw new BrainOfflineError(e instanceof Error ? e.message : String(e));
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Brain API ${res.status}: ${detail.slice(0, 300)}`);
  }
  return (await res.json()) as T;
}

export const brainClient = {
  status: () => api<BrainStatus>('/status'),
  chat: (message: string) => api<ChatResponse>('/chat', { method: 'POST', body: JSON.stringify({ message }) }),
  stats: () => api<Record<string, number>>('/memory/stats'),
  episodes: (limit = 12, status?: string) =>
    api<Episode[]>(`/memory/episodes?limit=${limit}${status ? `&status=${status}` : ''}`),
  searchEpisodes: (q: string, topK = 6) =>
    api<{ score: number; episode: Episode }[]>(`/memory/search?q=${encodeURIComponent(q)}&top_k=${topK}`),
  remember: (situation: string, tags: string[]) =>
    api<Episode>('/memory/remember', { method: 'POST', body: JSON.stringify({ situation, tags }) }),
  skills: (status?: string) =>
    api<Skill[]>(`/skills${status ? `?status=${status}` : ''}`),
  sleep: (trigger = 'ui_requested') =>
    api<SleepReport>('/sleep', { method: 'POST', body: JSON.stringify({ trigger }) }),
  sleepReport: () => api<SleepReport>('/sleep/report'),
  graph: (limit = 150) => api<GraphPayload>(`/graph?limit=${limit}`),
  exportSnapshot: () => api<{ path: string; size_bytes: number }>('/snapshot/export', { method: 'POST' }),
};

/** Connect the telemetry socket; returns an unsubscribe function. Fails silently into offline mode. */
export function connectTelemetry(onStatus: (s: BrainStatus) => void, onNote: (note: string) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  try {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${window.location.host}/ws/telemetry`);
  } catch {
    onNote('telemetry socket unavailable');
    return () => undefined;
  }
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data as string) as BrainStatus & { type?: string };
      if (data && data.type === 'status') onStatus(data);
    } catch { /* ignore malformed frames */ }
  };
  ws.onopen = () => onNote('telemetry connected');
  ws.onerror = () => onNote('telemetry socket offline (backend not running?)');
  ws.onclose = () => { if (!closed) onNote('telemetry disconnected'); };
  return () => {
    closed = true;
    ws?.close();
  };
}
