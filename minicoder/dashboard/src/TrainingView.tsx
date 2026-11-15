import { useCallback, useEffect, useState } from "react";

import { api, type Status } from "./api";
import { Badge, Bar, Empty, Panel, Stat, fmtNum } from "./ui";

type EvalSuite = {
  name: string;
  metrics: Record<string, unknown>;
  seconds: number;
  skipped?: string;
};

export function TrainingView({ status }: { status: Status | null }) {
  const [report, setReport] = useState<Record<string, EvalSuite> | null>(null);
  const [training, setTraining] = useState<Record<string, unknown> | null>(null);
  const [sleeping, setSleeping] = useState(false);
  const [sleepMsg, setSleepMsg] = useState<string | null>(null);
  const [episodes, setEpisodes] = useState<Record<string, unknown>[]>([]);
  const [runningEval, setRunningEval] = useState(false);

  const load = useCallback(async () => {
    const [ev, tr, sr] = await Promise.all([api.evalReport(), api.training(), api.sleepReports()]);
    setReport((ev.results as unknown as Record<string, EvalSuite>) ?? null);
    setTraining(tr);
    setEpisodes(sr.items);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runSleep = async () => {
    setSleeping(true);
    setSleepMsg("sleeping: replay → consolidate → compile → dispatch…");
    try {
      const r = await api.sleep(false, false);
      setSleepMsg(
        `cycle ${r.cycle_id} finished in ${Number(r.duration_seconds).toFixed(1)}s — ` +
          `${(r.promoted as string[])?.length ?? 0} promotion(s)`,
      );
      await load();
    } catch (err) {
      setSleepMsg(err instanceof Error ? err.message : "sleep failed");
    } finally {
      setSleeping(false);
    }
  };

  const runEval = async () => {
    setRunningEval(true);
    try {
      // The API exposes the last report; evaluation itself runs from the CLI so
      // it never blocks the dashboard's event loop with 30 s of CPU work.
      await load();
    } finally {
      setRunningEval(false);
    }
  };

  const coding = report?.coding?.metrics as
    | { indist?: { exact_match: number; n: number }; holdout?: { exact_match: number; n: number }; token_level?: { indist: { token_accuracy: number }; holdout: { token_accuracy: number } } }
    | undefined;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Coding pass@1 (in-dist)"
          value={coding?.indist ? `${(coding.indist.exact_match * 100).toFixed(0)}%` : "—"}
          hint={coding?.indist ? `n=${coding.indist.n} sandbox-verified` : "run minicoder eval"}
          tone="good"
        />
        <Stat
          label="Coding pass@1 (holdout)"
          value={coding?.holdout ? `${(coding.holdout.exact_match * 100).toFixed(0)}%` : "—"}
          hint={coding?.holdout ? `n=${coding.holdout.n} sealed tasks` : "—"}
        />
        <Stat
          label="Holdout token acc"
          value={
            coding?.token_level ? `${(coding.token_level.holdout.token_accuracy * 100).toFixed(0)}%` : "—"
          }
          hint="graded partial credit"
          tone="accent"
        />
        <Stat label="Sleep cycles" value={fmtNum(status?.memory.sleep_cycles ?? 0)} hint={`${status?.memory.shards ?? 0} shards`} />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel
          title="Benchmark suites"
          right={
            <button
              onClick={() => void runEval()}
              disabled={runningEval}
              className="rounded-md border border-[var(--color-edge)] px-2 py-0.5 text-[10px] text-[var(--color-muted)] hover:text-[var(--color-bright)]"
            >
              {runningEval ? "loading…" : "reload"}
            </button>
          }
        >
          {!report ? (
            <Empty>
              No evaluation report yet. Run <code className="text-[var(--color-accent)]">minicoder eval</code> to
              generate measured numbers.
            </Empty>
          ) : (
            <div className="space-y-2">
              {Object.entries(report).map(([name, suite]) => (
                <div key={name} className="rounded-lg border border-[var(--color-edge)] bg-[#0d1015] p-2.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-medium">{name}</span>
                    <span className="ml-auto text-[10px] text-[var(--color-muted)]">{suite.seconds.toFixed(1)}s</span>
                  </div>
                  {suite.skipped ? (
                    <div className="mt-1 text-[11px] text-[var(--color-muted)]">skipped: {suite.skipped}</div>
                  ) : (
                    <Metrics metrics={suite.metrics} />
                  )}
                </div>
              ))}
            </div>
          )}
        </Panel>

        <div className="space-y-3">
          <Panel
            title="Sleep engine"
            right={<Badge tone={status?.sleep.busy ? "accent" : "muted"}>{status?.sleep.busy ? "running" : "idle"}</Badge>}
          >
            <p className="mb-3 text-[11.5px] leading-relaxed text-[var(--color-muted)]">
              Runs the seven stages: prioritised replay, consolidation, cross-modal patterns, conflict
              resolution, decay-based forgetting, skill→dataset compilation, and GitHub dispatch.
            </p>
            <button
              onClick={() => void runSleep()}
              disabled={sleeping || status?.sleep.busy}
              className="w-full rounded-lg bg-[var(--color-accent)] py-2 text-[12px] font-semibold text-[#1a1206] disabled:opacity-40"
            >
              {sleeping ? "sleeping…" : "Trigger sleep"}
            </button>
            {sleepMsg && <p className="mt-2 text-[11px] text-[var(--color-muted)]">{sleepMsg}</p>}
            <div className="mt-3 space-y-1">
              {episodes.slice(0, 4).map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <Badge tone={r.status === "ok" ? "good" : r.status === "running" ? "accent" : "bad"}>
                    {String(r.status)}
                  </Badge>
                  <span className="text-[var(--color-muted)]">cycle {String(r.id)}</span>
                  <span className="ml-auto text-[10px] text-[var(--color-muted)]">{String(r.trigger)}</span>
                </div>
              ))}
              {episodes.length === 0 && <Empty>no cycles yet</Empty>}
            </div>
          </Panel>

          <Panel title="Adapters & shards">
            {!training ? (
              <Empty>loading…</Empty>
            ) : (
              <div className="space-y-2 text-[11px]">
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--color-muted)]">
                    checkpoints
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(training.checkpoints as string[])?.slice(0, 8).map((c) => (
                      <Badge key={c} tone="info">
                        {c}
                      </Badge>
                    )) ?? <span className="text-[var(--color-muted)]">none</span>}
                  </div>
                </div>
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--color-muted)]">
                    dataset shards
                  </div>
                  {((training.shards as Record<string, unknown>[]) ?? []).slice(0, 5).map((s, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="truncate font-mono text-[10.5px] text-[var(--color-bright)]">
                        {String(s.path).split("/").pop()}
                      </span>
                      <span className="ml-auto text-[10px] text-[var(--color-muted)]">
                        {String(s.examples)} ex
                      </span>
                      <Badge tone={s.pushed ? "good" : "muted"}>{s.pushed ? "pushed" : "local"}</Badge>
                    </div>
                  ))}
                  {((training.shards as unknown[]) ?? []).length === 0 && (
                    <span className="text-[var(--color-muted)]">none yet</span>
                  )}
                </div>
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--color-muted)]">
                    training runs
                  </div>
                  {((training.runs as Record<string, unknown>[]) ?? []).slice(0, 4).map((r, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Badge tone={r.gate_passed ? "good" : "bad"}>
                        {r.gate_passed ? "gate passed" : "gate rejected"}
                      </Badge>
                      <span className="truncate text-[10px] text-[var(--color-muted)]">
                        {String(r.notes).slice(0, 70)}
                      </span>
                    </div>
                  ))}
                  {((training.runs as unknown[]) ?? []).length === 0 && (
                    <span className="text-[var(--color-muted)]">none yet</span>
                  )}
                </div>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Metrics({ metrics }: { metrics: Record<string, unknown> }) {
  const flat: { key: string; value: string; ratio?: number }[] = [];
  const walk = (prefix: string, obj: unknown) => {
    if (obj === null || obj === undefined) return;
    if (typeof obj === "number") {
      const ratio = obj >= 0 && obj <= 1 ? obj : undefined;
      flat.push({ key: prefix, value: Number.isInteger(obj) ? String(obj) : obj.toFixed(3), ratio });
      return;
    }
    if (typeof obj === "string" || typeof obj === "boolean") {
      flat.push({ key: prefix, value: String(obj) });
      return;
    }
    if (Array.isArray(obj)) return;
    if (typeof obj === "object") {
      for (const [k, v] of Object.entries(obj as Record<string, unknown>)) walk(prefix ? `${prefix}.${k}` : k, v);
    }
  };
  walk("", metrics);
  return (
    <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1">
      {flat.slice(0, 12).map((f) => (
        <div key={f.key} className="text-[10.5px]">
          <div className="flex justify-between gap-2">
            <span className="truncate text-[var(--color-muted)]">{f.key}</span>
            <span className="font-mono text-[var(--color-bright)]">{f.value}</span>
          </div>
          {f.ratio !== undefined && <Bar value={f.ratio} tone={f.ratio >= 0.7 ? "good" : f.ratio >= 0.4 ? "accent" : "bad"} />}
        </div>
      ))}
    </div>
  );
}
