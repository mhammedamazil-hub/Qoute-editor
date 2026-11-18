import { useEffect, useState } from "react";

import { type GeneralizationOverview, api } from "./api";
import { Badge, Bar, Empty, Panel, Stat } from "./ui";

/**
 * Generalization tab (Phase 4): every axis of change measured separately against
 * a frozen baseline.
 *
 * Averaging the axes would hide the failure that matters, so each row keeps its
 * own numbers. The leakage panel reports the run's own integrity check: if
 * production memory or the skill library changed during the run, it says so here.
 */
export function GeneralizationView() {
  const [data, setData] = useState<GeneralizationOverview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .generalizationOverview()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  if (error) {
    return (
      <div className="h-full overflow-y-auto pr-1">
        <Panel title="Generalization"><Empty>{error}</Empty></Panel>
      </div>
    );
  }
  if (!data) return <div className="p-6 text-[12px] text-[var(--color-muted)]">loading generalization…</div>;
  if (!data.available) {
    return (
      <div className="h-full overflow-y-auto pr-1">
        <Panel title="Generalization">
          <Empty>No generalization report yet — run <code>python -m minicoder.cli generalize</code>.</Empty>
        </Panel>
      </div>
    );
  }

  const overall = data.overall ?? {};
  const leak = data.leakage ?? {};
  return (
    <div className="h-full space-y-3 overflow-y-auto pr-1">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat label="Frozen baseline" value={fmt(overall.baseline)} hint="library pinned at freeze time" />
        <Stat label="System" value={fmt(overall.system)} hint={`${overall.tasks ?? 0} tasks across ${data.axes.length} axes`} tone="accent" />
        <Stat label="Lift" value={fmt((overall.system ?? 0) - (overall.baseline ?? 0))} hint="mean across axes" tone={(overall.system ?? 0) > (overall.baseline ?? 0) ? "good" : "default"} />
        <Stat label="Leakage" value={leak.ok ? "clean" : "found"} hint={leak.ok ? "production untouched" : "see findings below"} tone={leak.ok ? "good" : "bad"} />
      </div>

      <Panel title="Axes of change" right={<Badge tone="info">seed {data.seed ?? "—"} · fp {data.fingerprint || "—"}</Badge>}>
        <div className="space-y-2">
          {data.axes.map((a) => (
            <div key={a.axis}>
              <div className="flex items-baseline justify-between text-[11px]">
                <span className="text-[var(--color-bright)]">
                  {a.axis} <span className="text-[var(--color-muted)]">· {a.description}</span>
                </span>
                <span className="font-mono text-[var(--color-muted)]">
                  base {fmt(a.baseline)} → system {fmt(a.system)} ({a.tasks} task{a.tasks === 1 ? "" : "s"})
                </span>
              </div>
              <div className="mt-1 flex gap-1">
                <Bar value={a.baseline} tone="info" />
                <Bar value={a.system} tone={a.lift > 0 ? "good" : "accent"} />
              </div>
              <div className="mt-0.5 text-[10px] text-[var(--color-muted)]">{a.families.join(", ")}</div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Integrity of the run">
        {leak.ok ? (
          <div className="space-y-1 text-[12px]">
            <p className="text-[var(--color-good)]">No leakage detected.</p>
            <p className="text-[var(--color-muted)]">
              Production counters unchanged · library unchanged · {leak.hidden_keys_scanned ?? 0} hidden
              identifiers scanned · private store outside the repository · baseline {leak.baseline_hash}.
            </p>
          </div>
        ) : (
          <div className="space-y-1 text-[12px]">
            {(leak.findings ?? []).map((f) => (
              <p key={f} className="text-[var(--color-bad)]">{f}</p>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Per-task results">
        <table className="w-full text-left text-[11px]">
          <thead className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-muted)]">
            <tr>
              <th className="py-1">axis</th>
              <th>family</th>
              <th>baseline</th>
              <th>system</th>
              <th>note</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((r) => (
              <tr key={r.key} className="border-t border-[var(--color-edge)]">
                <td className="py-1 text-[var(--color-muted)]">{r.axis}</td>
                <td>{r.family}</td>
                <td><Badge tone={r.baseline === "pass" ? "good" : "bad"}>{r.baseline}</Badge></td>
                <td><Badge tone={r.system === "pass" ? "good" : "bad"}>{r.system}</Badge></td>
                <td className="text-[var(--color-muted)]">{r.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

function fmt(n: number | undefined) {
  return typeof n === "number" && Number.isFinite(n) ? n.toFixed(3) : "—";
}
