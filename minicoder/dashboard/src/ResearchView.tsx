import { useCallback, useEffect, useState } from "react";

import { api, type ResearchOverviewResponse } from "./api";
import { Badge, Bar, Empty, Panel, Stat, fmtNum } from "./ui";

/**
 * Phase 3 research view.
 *
 * Every figure is read from a recorded experiment report in datasets/research/. Where a
 * report is missing the panel says so instead of drawing a zero, because a zero that looks
 * like a measurement is the failure mode this whole phase exists to avoid.
 */

function pct(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  return `${Math.round(value * 100)}%`;
}

const ARM_NOTE: Record<string, string> = {
  A: "model alone — the baseline",
  B: "memory only, disjoint warm-up seed",
  C: "discover, no retention",
  D: "acquire, no consolidation",
  E: "full system",
  F1: "ablation: no composition",
  F2: "ablation: no binary operations",
  F3: "ablation: no row operations",
};

export function Research() {
  const [data, setData] = useState<ResearchOverviewResponse | null>(null);
  const [error, setError] = useState<string>("");

  const load = useCallback(async () => {
    try {
      setData(await api.researchOverview());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 15000);
    return () => clearInterval(timer);
  }, [load]);

  if (error) return <Empty>research reports unavailable — {error}</Empty>;
  if (!data) return <Empty>loading research reports…</Empty>;

  const acq = data.acquisition;
  const arms = acq.arms ?? [];

  return (
    <div className="space-y-4">
      <Panel title="Phase 3 — blind acquisition" right={
        acq.available
          ? <Badge tone={acq.production_unchanged ? "good" : "bad"}>
              {acq.production_unchanged ? "production memory untouched" : "production memory CHANGED"}
            </Badge>
          : <Badge tone="bad">no experiment recorded</Badge>
      }>
        {!acq.available ? (
          <Empty>no acquisition report — run `minicoder research run`</Empty>
        ) : (
          <>
            <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="experiment" value={acq.experiment_id ?? "—"} hint={`commit ${(acq.commit ?? "").slice(0, 7)}`} />
              <Stat label="seeds" value={acq.seeds?.join(", ") ?? "—"} hint={`${acq.tasks_per_seed ?? "—"} tasks per seed`} />
              <Stat label="generator" value={acq.generator ?? "—"} hint="hidden draws from a private salt" />
              <Stat label="tasks scored" value={fmtNum(arms[0]?.tasks ?? 0)} hint="per arm, impossible excluded" />
            </div>
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-muted)]">
                <tr>
                  <th className="py-1">arm</th>
                  <th>what it is</th>
                  <th>hidden pass</th>
                  <th className="w-40">rate</th>
                  <th>95% CI</th>
                  <th>dev</th>
                  <th>test-fitted</th>
                </tr>
              </thead>
              <tbody>
                {arms.map((row) => (
                  <tr key={row.arm} className="border-t border-[var(--color-line)]">
                    <td className="py-1 font-mono">{row.arm}</td>
                    <td className="text-[var(--color-muted)]">{ARM_NOTE[row.arm] ?? ""}</td>
                    <td>
                      {row.hidden_pass}/{row.tasks}
                    </td>
                    <td>
                      <span className="flex items-center gap-2">
                        <Bar value={row.rate} tone={row.arm === "A" ? "bad" : "accent"} />
                        <span className="w-12 text-right">{pct(row.rate)}</span>
                      </span>
                    </td>
                    <td className="text-[var(--color-muted)]">
                      [{row.ci_low?.toFixed(2) ?? "—"}, {row.ci_high?.toFixed(2) ?? "—"}]
                      {row.established ? "" : " observed"}
                    </td>
                    <td className="text-[var(--color-muted)]">{row.dev_pass}</td>
                    <td>
                      {row.test_fitted > 0
                        ? <Badge tone="bad">{row.test_fitted} failed hidden</Badge>
                        : <span className="text-[var(--color-muted)]">0</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Transfer — programs re-scored unchanged">
          {!data.transfer.available ? (
            <Empty>no transfer report</Empty>
          ) : (
            <div className="space-y-2">
              {Object.entries(data.transfer.summary ?? {}).map(([kind, row]) => (
                <div key={kind} className="flex items-center gap-3 text-sm">
                  <span className="w-32 font-mono">{kind}</span>
                  <Bar value={row.rate ?? 0} tone={(row.rate ?? 0) >= 0.9 ? "good" : "info"} />
                  <span className="w-14 text-right">{pct(row.rate)}</span>
                  <span className="text-[var(--color-muted)]">{row.passed}/{row.cases}</span>
                </div>
              ))}
              <div className="pt-1 text-xs text-[var(--color-muted)]">
                {data.transfer.families} consolidated procedures · distribution shifts integers and letters
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Retention and isolation">
          <div className="grid grid-cols-2 gap-3">
            <Stat
              label="retained (verified)"
              value={data.retention.available ? `${data.retention.verified_retained}/${data.retention.verified}` : "—"}
              hint="execution-based, fresh process"
            />
            <Stat
              label="retained (all)"
              value={data.retention.available ? `${data.retention.retained}/${data.retention.families}` : "—"}
              hint="includes never-verified programs"
            />
            <Stat
              label="escape probes"
              value={data.security.available ? `${data.security.escapes}/${data.security.probes}` : "—"}
              hint={data.security.modes?.join(" + ") || "modes unavailable"}
            />
            <Stat
              label="reuse cost"
              value={data.meta.cost_reduction != null ? pct(data.meta.cost_reduction) : "—"}
              hint={data.meta.arm_c != null ? `${data.meta.arm_c} → ${data.meta.arm_e} candidates` : "no meta report"}
            />
          </div>
          <div className="mt-3 text-xs text-[var(--color-muted)]">
            No meta-learning: later tasks of the same family cost {pct(0)}–{data.meta.later ?? "—"} vs{" "}
            {data.meta.first ?? "—"} candidates; the gain above is reuse, not a better strategy.
          </div>
        </Panel>
      </div>
    </div>
  );
}
