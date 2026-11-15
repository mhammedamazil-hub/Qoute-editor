import { useMemo, useState } from "react";

import { useTelemetry } from "./api";
import { ChatView } from "./ChatView";
import { GraphView } from "./GraphView";
import { MemoryView } from "./MemoryView";
import { Overview } from "./Overview";
import { TrainingView } from "./TrainingView";
import { VisionView } from "./VisionView";
import { Badge } from "./ui";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "chat", label: "Copilot" },
  { id: "graph", label: "Knowledge" },
  { id: "memory", label: "Memory" },
  { id: "vision", label: "Vision" },
  { id: "training", label: "Learning" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const STATE_TONE: Record<string, string> = {
  WAKE: "text-[var(--color-good)]",
  SLEEP: "text-[var(--color-info)]",
  THINK: "text-[var(--color-accent)]",
  ACT: "text-[var(--color-accent)]",
  PERCEIVE: "text-[var(--color-info)]",
  REMEMBER: "text-[var(--color-good)]",
  COMPILE: "text-[var(--color-accent)]",
  GITHUB_TRAINING: "text-[var(--color-accent)]",
};

export default function App() {
  const [tab, setTab] = useState<TabId>("overview");
  const { status, live, lastEvent, refresh } = useTelemetry(4000);

  const state = status?.state ?? "WAKE";
  const healthDot = useMemo(() => {
    if (!status) return "bg-[var(--color-muted)]";
    return state === "WAKE" ? "bg-[var(--color-good)]" : "bg-[var(--color-accent)]";
  }, [status, state]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-[var(--color-edge)] px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <div className={`h-2.5 w-2.5 rounded-full ${healthDot} ${state === "WAKE" ? "" : "pulse"}`} />
          <div>
            <h1 className="text-[13px] font-semibold tracking-tight">
              MiniCoder <span className="text-[var(--color-muted)]">· Brain Dashboard</span>
            </h1>
            <p className="text-[10px] text-[var(--color-muted)]">
              compact multimodal cognitive system
            </p>
          </div>
        </div>

        <nav className="ml-2 flex flex-wrap gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-lg px-2.5 py-1.5 text-[11.5px] font-medium transition ${
                tab === t.id
                  ? "bg-[#1b2130] text-[var(--color-bright)]"
                  : "text-[var(--color-muted)] hover:text-[var(--color-bright)]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          <span className={`chip ${STATE_TONE[state] ?? ""}`}>{state}</span>
          <Badge tone={live ? "good" : "bad"}>{live ? "live" : "polling"}</Badge>
          {lastEvent && (
            <Badge tone="muted">
              {lastEvent.event.length > 26 ? `${lastEvent.event.slice(0, 26)}…` : lastEvent.event}
            </Badge>
          )}
          <Badge tone={status?.editor.online ? "good" : "muted"}>
            editor {status?.editor.online ? "on" : "off"}
          </Badge>
          <button
            onClick={() => void refresh()}
            className="rounded-md border border-[var(--color-edge)] px-2 py-1 text-[10px] text-[var(--color-muted)] hover:text-[var(--color-bright)]"
          >
            sync
          </button>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-hidden p-3">
        {tab === "overview" && <div className="h-full overflow-y-auto pr-1"><Overview status={status} /></div>}
        {tab === "chat" && <ChatView status={status} />}
        {tab === "graph" && <GraphView />}
        {tab === "memory" && <MemoryView />}
        {tab === "vision" && <VisionView />}
        {tab === "training" && (
          <div className="h-full overflow-y-auto pr-1">
            <TrainingView status={status} />
          </div>
        )}
      </main>

      <footer className="flex flex-wrap items-center gap-3 border-t border-[var(--color-edge)] px-4 py-1.5 text-[10px] text-[var(--color-muted)]">
        <span>SQLite WAL + sqlite-vec</span>
        <span>·</span>
        <span>{status ? `${status.brain.params.toLocaleString()} params` : "—"}</span>
        <span>·</span>
        <span>{status?.embedder ?? "—"}</span>
        <span className="ml-auto">
          Every number on this screen comes from the running process — nothing is mocked.
        </span>
      </footer>
    </div>
  );
}
