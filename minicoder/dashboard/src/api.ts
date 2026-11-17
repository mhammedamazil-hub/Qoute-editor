/**
 * API client + live telemetry hook.
 *
 * All requests are relative URLs so the dashboard works unchanged behind the
 * sandbox preview proxy and when served by the FastAPI process itself.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type Status = {
  state: string;
  uptime_seconds: number;
  brain: { backend: string; params: number; vocab: number; max_seq_len: number; meta: Record<string, unknown> };
  memory: {
    episodes: number;
    semantic_nodes: number;
    semantic_edges: number;
    skills_verified: number;
    skills_pending_export: number;
    visual_memories: number;
    embeddings: number;
    sleep_cycles: number;
    shards: number;
    conflicts_open: number;
    db_bytes: number;
    working: { items: number; capacity: number; tokens: number; token_budget: number; load: number; pinned: number };
    semantic_graph: { nodes: number; edges: number; verified: number; density: number; components: number };
    procedural: { total: number; verified: number; quarantined: number; pending_export: number };
    visual: { count: number };
  };
  calibration: { n: number; ece: number; brier: number; buckets: { range: string; n: number; predicted: number; actual: number }[] };
  sleep: { busy: boolean; cycles: number };
  editor: { online: boolean };
  embedder: string;
  events: { ts: number; state: string; event: string; data: Record<string, unknown> }[];
};

export type ChatReply = {
  answer: string;
  source: string;
  confidence: number;
  grounding: Record<string, unknown>[];
  steps: { tool: string; ok: boolean; summary: string; checks: string[]; ms: number }[];
  verified: boolean;
  elapsed_ms: number;
};

export type GraphNode = { id: number; label: string; kind: string; status: string; confidence: number; content: string };
export type GraphEdge = { src: number; dst: number; relation: string; weight: number };

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { accept: "application/json" } });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

async function jpost<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await r.text();
  if (!r.ok) throw new Error(text || `${r.status}`);
  return text ? (JSON.parse(text) as T) : ({} as T);
}


export type ResearchArm = {
  arm: string;
  tasks: number;
  hidden_pass: number;
  rate: number;
  ci_low: number | null;
  ci_high: number | null;
  established: boolean;
  dev_pass: number;
  test_fitted: number;
  mean_candidates: number;
};

export type ResearchOverviewResponse = {
  acquisition: {
    available: boolean;
    experiment_id?: string | null;
    commit?: string | null;
    generated_at?: string | null;
    seeds?: number[];
    tasks_per_seed?: number | null;
    generator?: string | null;
    production_unchanged?: boolean | null;
    arms: ResearchArm[];
  };
  transfer: {
    available: boolean;
    summary: Record<string, { cases: number; passed: number; rate: number | null }>;
    families: number;
  };
  retention: {
    available: boolean;
    retained: number;
    families: number;
    verified: number;
    verified_retained: number;
  };
  meta: {
    available: boolean;
    cost_reduction: number | null;
    arm_c: number | null;
    arm_e: number | null;
    first: number | null;
    later: number | null;
  };
  security: { available: boolean; probes: number; escapes: number; modes: string[] };
};

export type LearningOverviewResponse = {
  counts: Record<string, number>;
  experiments: Array<Record<string, any>>;
  attempts: Array<Record<string, any>>;
  candidates: Array<Record<string, any>>;
  replays: Array<Record<string, any>>;
  resources: Array<Record<string, any>>;
  failure_classes: Record<string, number>;
  retention: Array<{
    slug: string;
    runs: number;
    passed: number;
    rate: number;
    points: Array<{ ts: string; passed: number }>;
  }>;
  benchmark: Record<string, any>;
  acceptance: Record<string, any>;
  checkpoints: string[];
  baselines: string[];
};

export type LearningSkillsResponse = {
  learned: Array<Record<string, any>>;
  seeded: Array<Record<string, any>>;
  dependencies: Array<Record<string, any>>;
};

export const api = {
  status: () => jget<Status>("/api/status"),
  health: () => jget<{ ok: boolean; db: string; state: string }>("/api/health"),
  chat: (message: string, allowActions = true) =>
    jpost<ChatReply>("/api/chat", { message, allow_actions: allowActions }),
  graph: () => jget<{ nodes: GraphNode[]; edges: GraphEdge[] }>("/api/graph"),
  episodes: () => jget<{ items: Record<string, unknown>[] }>("/api/episodes?limit=40"),
  skills: () => jget<{ items: Record<string, unknown>[]; stats: Record<string, number> }>("/api/skills"),
  visual: () => jget<{ items: Record<string, unknown>[] }>("/api/vision?limit=24"),
  evalReport: () => jget<{ available: boolean; results?: Record<string, { metrics: Record<string, unknown>; skipped?: string }> }>("/api/eval"),
  sleep: (push = false, train = false) => jpost<Record<string, unknown>>("/api/sleep", { trigger: "dashboard", push, train }),
  sleepReports: () => jget<{ items: Record<string, unknown>[] }>("/api/sleep/reports"),
  training: () => jget<Record<string, unknown>>("/api/training"),
  tools: () => jget<{ tools: { name: string; description: string }[]; error?: string }>("/api/editor/tools"),
  callTool: (tool: string, args: Record<string, unknown>) =>
    jpost<{ ok: boolean; result: Record<string, unknown>; checks: string[] }>("/api/editor/tool", { tool, args }),
  snapshots: () => jpost<{ path: string; bytes: number }>("/api/export/snapshot", {}),
  learningOverview: () => jget<LearningOverviewResponse>("/api/learning/overview"),
  researchOverview: () => jget<ResearchOverviewResponse>("/api/research/overview"),
  learningSkills: () => jget<LearningSkillsResponse>("/api/learning/skills"),
  learningExperiments: () => jget<{ experiments: Record<string, unknown>[] }>(
    "/api/learning/experiments",
  ),
  inspectImage: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/vision/inspect", { method: "POST", body: fd });
    if (!r.ok) throw new Error(await r.text());
    return (await r.json()) as Record<string, any>;
  },
};

/** Polls status and subscribes to the WebSocket for live state transitions. */
export function useTelemetry(intervalMs = 4000) {
  const [status, setStatus] = useState<Status | null>(null);
  const [live, setLive] = useState(false);
  const [lastEvent, setLastEvent] = useState<{ state: string; event: string } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.status());
    } catch {
      /* server restarting; the next tick recovers */
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, intervalMs);
    return () => window.clearInterval(id);
  }, [refresh, intervalMs]);

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/telemetry`);
    wsRef.current = ws;
    ws.onopen = () => setLive(true);
    ws.onclose = () => setLive(false);
    ws.onerror = () => setLive(false);
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(String(msg.data));
        if (data.event && data.event !== "connected") setLastEvent({ state: data.state, event: data.event });
        if (data.event === "status" || data.event === "connected") return;
        void refresh();
      } catch {
        /* ignore malformed frames */
      }
    };
    const ping = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("status");
    }, 25000);
    return () => {
      window.clearInterval(ping);
      ws.close();
    };
  }, [refresh]);

  return { status, live, lastEvent, refresh };
}
