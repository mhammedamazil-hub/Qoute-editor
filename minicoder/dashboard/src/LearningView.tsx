import { useCallback, useEffect, useState } from "react";

import { api, type LearningOverviewResponse, type LearningSkillsResponse } from "./api";
import { Badge, Bar, Empty, Panel, Stat, fmtNum } from "./ui";

/**
 * Learning observability.
 *
 * Every number rendered here comes from a recorded measurement: the experiment
 * ledger, the replay table, the resource samples, or a benchmark report on
 * disk. Nothing is derived from an assumption about what the system "should"
 * have done, and failed experiments are shown as prominently as successful ones.
 */

const STATUS_TONE: Record<string, "good" | "bad" | "accent" | "info" | "muted"> = {
  promoted: "good",
  replay_passed: "info",
  candidate: "accent",
  replay_failed: "bad",
  rejected: "bad",
  solved: "good",
  exhausted: "bad",
  open: "accent",
  abandoned: "muted",
};

function pct(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  return `${Math.round(value * 100)}%`;
}

/** A small sparkline of pass/fail points, drawn from the replay table. */
function Sparkline({ points }: { points: Array<{ passed: number }> }) {
  if (!points.length) return <span className="text-[var(--color-muted)]">no runs</span>;
  return (
    <span className="inline-flex items-center gap-[3px]">
      {points.map((p, i) => (
        <span
          key={i}
          title={p.passed ? "passed" : "failed"}
          className={`inline-block h-2 w-2 rounded-sm ${
            p.passed ? "bg-[var(--color-good)]" : "bg-[var(--color-bad)]"
          }`}
        />
      ))}
    </span>
  );
}

export function LearningView() {
  const [overview, setOverview] = useState<LearningOverviewResponse | null>(null);
  const [skills, setSkills] = useState<LearningSkillsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [ov, sk] = await Promise.all([api.learningOverview(), api.learningSkills()]);
      setOverview(ov);
      setSkills(sk);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 8000);
    return () => clearInterval(t);
  }, [load]);

  if (error && !overview) {
    return (
      <Empty>
        Could not reach the learning API: {error}. Start the server with
        <code className="mx-1 rounded bg-[var(--color-panel2)] px-1">minicoder serve</code>.
      </Empty>
    );
  }
  if (!overview) return <Empty>Loading recorded measurements…</Empty>;

  const c = overview.counts;
  const bench = overview.benchmark;
  const acc = overview.acceptance;
  const benchSummary = (bench.summary ?? {}) as Record<string, number>;
  const peakRss = Math.max(1, ...overview.resources.map((r) => Number(r.rss_mb) || 0));

  return (
    <div className="flex flex-col gap-3 p-3">
      {/* ---------------------------------------------------- acquisition */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Experiments" value={fmtNum(c.experiments)} hint={`${c.solved} solved`} />
        <Stat
          label="Awaiting verification"
          value={fmtNum(c.awaiting_verification)}
          hint="candidate, not yet replayed"
          tone={c.awaiting_verification > 0 ? "accent" : "default"}
        />
        <Stat
          label="Skills verified"
          value={fmtNum(c.promoted)}
          hint={`${c.replay_passed} passed replay`}
          tone="good"
        />
        <Stat
          label="Rejected"
          value={fmtNum(c.rejected)}
          hint="failed replay, refused"
          tone={c.rejected > 0 ? "bad" : "default"}
        />
        <Stat
          label="Failed attempts"
          value={fmtNum(c.failed_attempts)}
          hint={`of ${c.attempts} recorded`}
          tone={c.failed_attempts > 0 ? "bad" : "default"}
        />
        <Stat
          label="Dependencies"
          value={fmtNum(c.dependencies)}
          hint="skill → tool edges"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {/* --------------------------------------------------- benchmark */}
        <Panel
          title="Sealed benchmark"
          right={
            bench.available ? (
              <Badge tone={benchSummary.final_success >= benchSummary.n * 0.8 ? "good" : "accent"}>
                {benchSummary.final_success}/{benchSummary.n} solved
              </Badge>
            ) : (
              <Badge>not run</Badge>
            )
          }
        >
          {!bench.available ? (
            <Empty>{bench.reason}</Empty>
          ) : (
            <div className="flex flex-col gap-2">
              <div className="grid grid-cols-2 gap-2 text-[11px] md:grid-cols-4">
                <div>
                  <div className="text-[var(--color-muted)]">first attempt</div>
                  <div className="text-[13px]">{pct(benchSummary.first_attempt_rate)}</div>
                </div>
                <div>
                  <div className="text-[var(--color-muted)]">final</div>
                  <div className="text-[13px]">{pct(benchSummary.final_rate)}</div>
                </div>
                <div>
                  <div className="text-[var(--color-muted)]">replay</div>
                  <div className="text-[13px]">
                    {benchSummary.replay_passed ?? 0}/{benchSummary.replay_attempted ?? 0}
                  </div>
                </div>
                <div>
                  <div className="text-[var(--color-muted)]">peak RSS</div>
                  <div className="text-[13px]">{benchSummary.peak_rss_mb ?? "—"} MB</div>
                </div>
              </div>
              <div className="flex flex-col gap-1">
                {Object.entries(bench.by_category ?? {}).map(([cat, v]: [string, any]) => (
                  <div key={cat} className="flex items-center gap-2 text-[11px]">
                    <span className="w-32 shrink-0 truncate text-[var(--color-muted)]">{cat}</span>
                    <div className="flex-1">
                      <Bar value={v.final_rate} tone={v.final_rate >= 0.8 ? "good" : "accent"} />
                    </div>
                    <span className="w-12 text-right">
                      {v.solved}/{v.n}
                    </span>
                  </div>
                ))}
              </div>
              {(bench.failed ?? []).length > 0 && (
                <div className="rounded border border-[var(--color-edge)] p-2">
                  <div className="mb-1 text-[11px] font-medium text-[var(--color-bad)]">
                    Reported failures
                  </div>
                  {(bench.failed ?? []).map((f: any) => (
                    <div key={f.key} className="text-[11px] text-[var(--color-muted)]">
                      <span className="text-[var(--color-fg)]">{f.key}</span> — {f.reason}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Panel>

        {/* -------------------------------------------------- acceptance */}
        <Panel
          title="Acceptance criteria"
          right={
            acc.available ? (
              <Badge tone={acc.all_passed ? "good" : "bad"}>
                {acc.passed}/{acc.total} passed
              </Badge>
            ) : (
              <Badge>not run</Badge>
            )
          }
        >
          {!acc.available ? (
            <Empty>{acc.reason}</Empty>
          ) : (
            <div className="flex flex-col gap-1.5">
              {(acc.checks ?? []).map((chk: any) => (
                <div key={chk.n} className="flex items-start gap-2 text-[11px]">
                  <span
                    className={`mt-[3px] inline-block h-2 w-2 shrink-0 rounded-full ${
                      chk.passed ? "bg-[var(--color-good)]" : "bg-[var(--color-bad)]"
                    }`}
                  />
                  <div className="min-w-0">
                    <div>
                      {chk.n}. {chk.name}
                    </div>
                    <div className="truncate text-[var(--color-muted)]" title={chk.detail}>
                      {chk.detail}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {/* ---------------------------------------------- retention curve */}
        <Panel title="Retention & forgetting" right={<span className="text-[11px] text-[var(--color-muted)]">per skill, from replay table</span>}>
          {overview.retention.length === 0 ? (
            <Empty>No replay measurements yet.</Empty>
          ) : (
            <div className="flex flex-col gap-1.5">
              {overview.retention.map((r) => (
                <div key={r.slug} className="flex items-center gap-2 text-[11px]">
                  <span className="w-44 shrink-0 truncate" title={r.slug}>
                    {r.slug}
                  </span>
                  <div className="flex-1">
                    <Bar value={r.rate} tone={r.rate >= 0.8 ? "good" : r.rate >= 0.5 ? "accent" : "bad"} />
                  </div>
                  <span className="w-16 text-right text-[var(--color-muted)]">
                    {r.passed}/{r.runs}
                  </span>
                  <Sparkline points={r.points} />
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* ------------------------------------------------ failure classes */}
        <Panel title="Failure taxonomy" right={<span className="text-[11px] text-[var(--color-muted)]">latest experiment</span>}>
          {Object.keys(overview.failure_classes).length === 0 ? (
            <Empty>No attempts recorded yet.</Empty>
          ) : (
            <div className="flex flex-col gap-1">
              {Object.entries(overview.failure_classes).map(([cls, n]) => (
                <div key={cls} className="flex items-center gap-2 text-[11px]">
                  <span className="w-32 shrink-0">{cls}</span>
                  <div className="flex-1">
                    <Bar value={n} max={Math.max(...Object.values(overview.failure_classes))} tone={cls === "none" ? "good" : "bad"} />
                  </div>
                  <span className="w-8 text-right">{n}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      {/* ------------------------------------------------------ skill table */}
      <Panel
        title="Learned skills"
        right={<span className="text-[11px] text-[var(--color-muted)]">{skills?.learned.length ?? 0} candidates</span>}
      >
        {!skills || skills.learned.length === 0 ? (
          <Empty>
            Nothing learned yet. Run <code className="mx-1 rounded bg-[var(--color-panel2)] px-1">minicoder learn</code>
            or <code className="mx-1 rounded bg-[var(--color-panel2)] px-1">minicoder benchmark</code>.
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead className="text-[var(--color-muted)]">
                <tr>
                  <th className="py-1 pr-3">slug</th>
                  <th className="py-1 pr-3">task</th>
                  <th className="py-1 pr-3">status</th>
                  <th className="py-1 pr-3">steps</th>
                  <th className="py-1 pr-3">replays</th>
                  <th className="py-1">failures</th>
                </tr>
              </thead>
              <tbody>
                {skills.learned.map((s) => (
                  <tr key={s.id} className="border-t border-[var(--color-edge)]">
                    <td className="py-1 pr-3 font-mono">{s.slug}</td>
                    <td className="py-1 pr-3">{s.task_key ?? "—"}</td>
                    <td className="py-1 pr-3">
                      <Badge tone={STATUS_TONE[s.status] ?? "muted"}>{s.status}</Badge>
                    </td>
                    <td className="py-1 pr-3">{s.steps}</td>
                    <td className="py-1 pr-3">{s.replay_runs}</td>
                    <td className="py-1 text-[var(--color-bad)]">
                      {(s.replay_failures ?? []).length}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {/* ----------------------------------------------- experiment log */}
        <Panel title="Experiment history">
          {overview.experiments.length === 0 ? (
            <Empty>No experiments recorded.</Empty>
          ) : (
            <div className="max-h-72 overflow-auto">
              <table className="w-full text-left text-[11px]">
                <thead className="sticky top-0 bg-[var(--color-panel)] text-[var(--color-muted)]">
                  <tr>
                    <th className="py-1 pr-2">#</th>
                    <th className="py-1 pr-2">task</th>
                    <th className="py-1 pr-2">status</th>
                    <th className="py-1 pr-2">s</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.experiments.map((e) => (
                    <tr key={e.id} className="border-t border-[var(--color-edge)]">
                      <td className="py-1 pr-2">{e.id}</td>
                      <td className="py-1 pr-2 font-mono">{e.task_key}</td>
                      <td className="py-1 pr-2">
                        <Badge tone={STATUS_TONE[e.status] ?? "muted"}>{e.status}</Badge>
                      </td>
                      <td className="py-1 pr-2">{e.seconds}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        {/* -------------------------------------------- resources + ckpts */}
        <Panel title="Resources & checkpoints">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-[11px]">
              <span className="w-24 shrink-0 text-[var(--color-muted)]">RSS now</span>
              <div className="flex-1">
                <Bar value={Number(overview.resources[0]?.rss_mb ?? 0)} max={peakRss} tone="info" />
              </div>
              <span className="w-16 text-right">{overview.resources[0]?.rss_mb ?? "—"} MB</span>
            </div>
            <div className="flex items-center gap-2 text-[11px]">
              <span className="w-24 shrink-0 text-[var(--color-muted)]">peak (samples)</span>
              <div className="flex-1">
                <Bar value={peakRss} max={peakRss} tone="accent" />
              </div>
              <span className="w-16 text-right">{peakRss.toFixed(1)} MB</span>
            </div>
            <div className="text-[11px]">
              <div className="mb-1 text-[var(--color-muted)]">checkpoints</div>
              <div className="flex flex-wrap gap-1">
                {overview.checkpoints.map((k) => (
                  <Badge key={k} tone="info">
                    {k}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="text-[11px]">
              <div className="mb-1 text-[var(--color-muted)]">immutable baselines</div>
              <div className="flex flex-wrap gap-1">
                {overview.baselines.length === 0 ? (
                  <span className="text-[var(--color-muted)]">
                    none — create one with `minicoder safeguard baseline`
                  </span>
                ) : (
                  overview.baselines.map((b) => (
                    <Badge key={b} tone="good">
                      {b}
                    </Badge>
                  ))
                )}
              </div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
