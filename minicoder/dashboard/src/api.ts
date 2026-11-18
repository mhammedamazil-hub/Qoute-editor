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

/**
 * Authorization (Phase 5).
 *
 * Consequences need an *operator token* plus a single-use *grant*.  Neither is
 * a cookie: the token is a capability the operator pastes once per browser
 * session (sessionStorage), and a grant is minted per action and consumed by the
 * server.  Nothing here can authorize anything on its own — the server rejects
 * every mutation that does not present both.
 */
const TOKEN_KEY = "nace.operator.token";

export function getToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage disabled: the dashboard stays read-only */
  }
}

export type GrantNeeded = { action: string; resource: string; scope: string };

export class ApiError extends Error {
  status: number;
  code: string;
  requiresGrant: GrantNeeded | null;

  constructor(status: number, body: string) {
    let code = "";
    let detail = "";
    let requiresGrant: GrantNeeded | null = null;
    try {
      const parsed = JSON.parse(body);
      code = String(parsed.error || "");
      detail = String(parsed.detail || "");
      if (parsed.requires_grant) requiresGrant = parsed.requires_grant as GrantNeeded;
    } catch {
      detail = body;
    }
    super(detail || code || `HTTP ${status}`);
    this.status = status;
    this.code = code;
    this.requiresGrant = requiresGrant;
  }
}

function authHeaders(base: Record<string, string> = {}): Record<string, string> {
  const token = getToken();
  return token ? { ...base, authorization: `Bearer ${token}` } : base;
}

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: authHeaders({ accept: "application/json" }) });
  const text = await r.text();
  if (!r.ok) throw new ApiError(r.status, text);
  return JSON.parse(text) as T;
}

async function jpost<T>(url: string, body: unknown, grants: string[] = []): Promise<T> {
  const headers: Record<string, string> = authHeaders({ "content-type": "application/json" });
  if (grants.length) headers["x-nace-grant"] = grants[0];
  const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
  const text = await r.text();
  if (!r.ok) throw new ApiError(r.status, text);
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export type SecurityStatus = {
  authenticated: boolean;
  principal: string;
  grants: Record<string, number>;
  audit: { chain_ok: boolean; length: number; head: string; counts: Record<string, number> };
  policy: { tools: number; grant_required_classes: string[]; actions: string[] };
  cors: { origins: string[]; origin_regex: string | null; note: string };
};


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


export type CalibrationBucket = { range: string; n: number; predicted: number; actual: number };

export type CognitionOverview = {
  calibration: {
    n: number;
    ece: number;
    brier: number;
    buckets: CalibrationBucket[];
    sources: Record<string, number>;
    mean_predicted: number | null;
    mean_actual: number | null;
  };
  calibration_history: { ts: string; predicted: number; outcome: number; source: string }[];
  intent_counts: Record<string, number>;
  audit: {
    ts: string;
    action: string;
    intent: string;
    authorized: boolean;
    allowed: boolean;
    detail: Record<string, any>;
  }[];
  refused_actions: number;
  memory: { episodes: number; semantic_nodes: number; skills: number };
  capabilities: Record<string, any>;
};

export type GeneralizationAxis = {
  axis: string;
  description: string;
  tasks: number;
  baseline: number;
  system: number;
  lift: number;
  families: string[];
};

export type GeneralizationOverview = {
  available: boolean;
  axes: GeneralizationAxis[];
  overall: { tasks?: number; baseline?: number; system?: number };
  leakage: {
    ok: boolean;
    findings: string[];
    production_unchanged: boolean;
    library_unchanged: boolean;
    hidden_keys_scanned: number;
    baseline_hash: string;
  };
  fingerprint: string;
  seed: number | null;
  seconds: number;
  results: {
    axis: string;
    key: string;
    family: string;
    baseline: string;
    system: string;
    notes: string;
  }[];
};

export const api = {
  status: () => jget<Status>("/api/status"),
  health: () => jget<{ ok: boolean; db: string; state: string }>("/api/health"),
  chat: (message: string, allowActions = true, grants: string[] = []) =>
    jpost<ChatReply>("/api/chat", { message, allow_actions: allowActions }, grants),
  securityStatus: () => jget<SecurityStatus>("/api/security/status"),
  securityInventory: () =>
    jget<{ tools: { tool: string; class: string }[]; actions: string[] }>("/api/security/inventory"),
  grant: (action: string, scope = "", resource?: string) =>
    jpost<{ grant: { id: string; action: string; scope: string; expires_at: string } }>(
      "/api/security/grant",
      { action, scope, resource },
    ),
  securityAudit: (limit = 25) =>
    jget<{ items: Record<string, unknown>[]; chain: { ok: boolean; length: number } }>(
      `/api/security/audit?limit=${limit}`,
    ),
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
  // mutation helpers that need a grant minted by the caller
  grantFor: async (action: string, scope = "", resource?: string) => {
    const r = await jpost<{ grant: { id: string } }>("/api/security/grant", { action, scope, resource });
    return r.grant.id;
  },
  learningOverview: () => jget<LearningOverviewResponse>("/api/learning/overview"),
  researchOverview: () => jget<ResearchOverviewResponse>("/api/research/overview"),
  cognitionOverview: () => jget<CognitionOverview>("/api/cognition/overview"),
  generalizationOverview: () => jget<GeneralizationOverview>("/api/generalization/overview"),
  sleepAdaptive: () => jget<Record<string, any>>("/api/sleep/adaptive"),
  learningSkills: () => jget<LearningSkillsResponse>("/api/learning/skills"),
  learningExperiments: () => jget<{ experiments: Record<string, unknown>[] }>(
    "/api/learning/experiments",
  ),
  inspectImage: async (file: File, grants: string[] = []) => {
    const fd = new FormData();
    fd.append("file", file);
    const headers: Record<string, string> = authHeaders();
    if (grants.length) headers["x-nace-grant"] = grants[0];
    const r = await fetch("/api/vision/inspect", { method: "POST", body: fd, headers });
    const text = await r.text();
    if (!r.ok) throw new ApiError(r.status, text);
    return JSON.parse(text) as Record<string, any>;
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
