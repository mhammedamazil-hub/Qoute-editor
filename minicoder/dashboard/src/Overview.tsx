import { useMemo } from "react";

import type { Status } from "./api";
import { Badge, Bar, Empty, Panel, Stat, fmtBytes, fmtNum } from "./ui";

const STATES: { key: string; label: string }[] = [
  { key: "WAKE", label: "Awake" },
  { key: "PERCEIVE", label: "Perceiving" },
  { key: "THINK", label: "Thinking" },
  { key: "ACT", label: "Acting" },
  { key: "REMEMBER", label: "Remembering" },
  { key: "SLEEP", label: "Sleeping" },
  { key: "COMPILE", label: "Compiling" },
  { key: "GITHUB_TRAINING", label: "GitHub training" },
];

export function Overview({ status }: { status: Status | null }) {
  const active = status?.state ?? "WAKE";
  const mem = status?.memory;
  const totalMemories = useMemo(() => {
    if (!mem) return 0;
    return mem.episodes + mem.semantic_nodes + mem.skills_verified + mem.visual_memories;
  }, [mem]);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Episodes" value={mem ? fmtNum(mem.episodes) : "—"} hint="autobiographical records" />
        <Stat label="Concepts" value={mem ? fmtNum(mem.semantic_nodes) : "—"} hint={`${mem?.semantic_edges ?? 0} relations`} />
        <Stat
          label="Verified skills"
          value={mem ? fmtNum(mem.skills_verified) : "—"}
          hint={`${mem?.skills_pending_export ?? 0} pending export`}
          tone="good"
        />
        <Stat label="Visual memories" value={mem ? fmtNum(mem.visual_memories) : "—"} hint="deduplicated by hash" />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Panel title="Lifecycle" className="lg:col-span-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {STATES.map((s) => {
              const on = active === s.key || (s.key === "WAKE" && active === "WAKE");
              return (
                <div
                  key={s.key}
                  className={`rounded-lg border px-2.5 py-1.5 text-[11px] transition ${
                    on
                      ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_16%,transparent)] text-[var(--color-accent)] pulse"
                      : "border-[var(--color-edge)] text-[var(--color-muted)]"
                  }`}
                >
                  {s.label}
                </div>
              );
            })}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <div>
              <div className="mb-1 flex justify-between text-[10px] text-[var(--color-muted)]">
                <span>working memory</span>
                <span>{mem ? `${(mem.working.load * 100).toFixed(0)}%` : "—"}</span>
              </div>
              <Bar value={mem?.working.load ?? 0} />
            </div>
            <div>
              <div className="mb-1 flex justify-between text-[10px] text-[var(--color-muted)]">
                <span>graph density</span>
                <span>{mem ? mem.semantic_graph.density.toFixed(4) : "—"}</span>
              </div>
              <Bar value={Math.min(1, (mem?.semantic_graph.density ?? 0) * 12)} tone="info" />
            </div>
            <div>
              <div className="mb-1 flex justify-between text-[10px] text-[var(--color-muted)]">
                <span>skills verified</span>
                <span>
                  {mem?.procedural.verified ?? 0}/{mem?.procedural.total ?? 0}
                </span>
              </div>
              <Bar
                value={(mem?.procedural.verified ?? 0) / Math.max(1, mem?.procedural.total ?? 1)}
                tone="good"
              />
            </div>
            <div>
              <div className="mb-1 flex justify-between text-[10px] text-[var(--color-muted)]">
                <span>conflicts open</span>
                <span>{mem?.conflicts_open ?? 0}</span>
              </div>
              <Bar value={Math.min(1, (mem?.conflicts_open ?? 0) / 5)} tone="bad" />
            </div>
          </div>
        </Panel>

        <Panel title="System">
          <dl className="space-y-2 text-[11.5px]">
            <Row k="total memories" v={fmtNum(totalMemories)} />
            <Row k="brain DB" v={fmtBytes(mem?.db_bytes ?? 0)} />
            <Row k="checkpoint" v={status ? `${fmtNum(status.brain.params)} params` : "—"} />
            <Row k="vocab" v={status ? fmtNum(status.brain.vocab) : "—"} />
            <Row k="embedder" v={status?.embedder ?? "—"} />
            <Row k="sleep cycles" v={status ? fmtNum(status.memory.sleep_cycles) : "—"} />
            <Row k="dataset shards" v={status ? fmtNum(status.memory.shards) : "—"} />
            <Row k="uptime" v={status ? `${Math.floor(status.uptime_seconds / 60)}m` : "—"} />
          </dl>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Badge tone={status?.editor.online ? "good" : "bad"}>
              editor {status?.editor.online ? "online" : "offline"}
            </Badge>
            <Badge tone={status?.sleep.busy ? "accent" : "muted"}>
              sleep {status?.sleep.busy ? "running" : "idle"}
            </Badge>
            <Badge tone="info">
              calibration n={status?.calibration.n ?? 0}
            </Badge>
          </div>
        </Panel>
      </div>

      <Panel title="Recent events" className="max-h-[260px] overflow-y-auto">
        {!status?.events.length ? (
          <Empty>No telemetry yet.</Empty>
        ) : (
          <ul className="space-y-1">
            {status.events
              .slice()
              .reverse()
              .map((e, i) => (
                <li key={i} className="flex items-center gap-2 text-[11px]">
                  <span className="font-mono text-[10px] text-[var(--color-muted)]">
                    {new Date(e.ts * 1000).toLocaleTimeString("en-GB", { hour12: false })}
                  </span>
                  <Badge tone="info">{e.state}</Badge>
                  <span className="truncate text-[var(--color-muted)]">{e.event}</span>
                </li>
              ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-[var(--color-muted)]">{k}</dt>
      <dd className="font-mono text-[var(--color-bright)]">{v}</dd>
    </div>
  );
}
