import { useEffect, useState } from "react";

import { type CognitionOverview, api } from "./api";
import { Badge, Bar, Empty, Panel, Stat } from "./ui";

/**
 * Cognition tab (Phase 4): what the system decided a request *was*, how well its
 * confidence matches measured correctness, what it was allowed to do, and what
 * the last sleep cycle actually measured.
 *
 * Every number comes from a recorded row (`calibration`, `audit_log`,
 * `sleep_cycles`). When a measurement does not exist the panel says so instead of
 * drawing a zero.
 */
export function CognitionView() {
  const [data, setData] = useState<CognitionOverview | null>(null);
  const [sleep, setSleep] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [c, s] = await Promise.all([api.cognitionOverview(), api.sleepAdaptive()]);
        if (!alive) return;
        setData(c);
        setSleep(s);
        setError("");
      } catch (e) {
        if (alive) setError(String(e));
      }
    };
    load();
    const id = window.setInterval(load, 8000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  if (error) {
    return (
      <div className="h-full overflow-y-auto pr-1">
        <Panel title="Cognition"><Empty>{error}</Empty></Panel>
      </div>
    );
  }
  if (!data) return <div className="p-6 text-[12px] text-[var(--color-muted)]">loading cognition…</div>;

  const cal = data.calibration;
  const hasCal = cal.n > 0;
  const adaptive = (sleep?.adaptive ?? {}) as Record<string, any>;
  const hygiene = adaptive.hygiene ?? {};
  const retention = adaptive.rotation_retention ?? {};
  const promotion = adaptive.promotion ?? {};
  const intents = Object.entries(data.intent_counts ?? {}).sort((a, b) => b[1] - a[1]);
  const intentMax = Math.max(1, ...intents.map(([, n]) => n));

  return (
    <div className="h-full space-y-3 overflow-y-auto pr-1">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat
          label="Calibration samples"
          value={cal.n}
          hint={hasCal ? `${cal.sources ? Object.keys(cal.sources).join(", ") : "recorded"}` : "no outcome measured yet"}
          tone={hasCal ? "accent" : "default"}
        />
        <Stat
          label="Brier score"
          value={hasCal ? Number(cal.brier).toFixed(3) : "—"}
          hint="lower is better · (confidence − outcome)²"
          tone={hasCal ? (cal.brier < 0.25 ? "good" : "bad") : "default"}
        />
        <Stat
          label="Refused actions"
          value={data.refused_actions}
          hint="consequential requests without authorisation"
          tone={data.refused_actions ? "bad" : "good"}
        />
        <Stat label="Verified skills" value={data.memory.skills} hint={`${data.memory.semantic_nodes} live memories`} />
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title="Reliability — predicted vs measured" right={<Badge tone={hasCal ? "info" : "muted"}>ECE {hasCal ? Number(cal.ece).toFixed(3) : "n/a"}</Badge>}>
          {hasCal ? (
            <div className="space-y-2">
              {(cal.buckets ?? []).map((b) => (
                <div key={b.range}>
                  <div className="flex justify-between text-[11px] text-[var(--color-muted)]">
                    <span>{b.range}</span>
                    <span className="font-mono">
                      said {b.predicted.toFixed(2)} · was {b.actual.toFixed(2)} · n={b.n}
                    </span>
                  </div>
                  <div className="mt-1 flex gap-1">
                    <Bar value={b.predicted} tone="accent" />
                    <Bar value={b.actual} tone="good" />
                  </div>
                </div>
              ))}
              <p className="pt-1 text-[11px] text-[var(--color-muted)]">
                Blue is confidence when the answer was given; green is what actually happened.
              </p>
            </div>
          ) : (
            <Empty>No measured outcomes yet. Confidence is shown as uncalibrated until an execution is verified.</Empty>
          )}
        </Panel>

        <Panel title="Intent mix" right={<Badge>{intents.reduce((a, [, n]) => a + n, 0)} decided</Badge>}>
          {intents.length ? (
            <div className="space-y-2">
              {intents.map(([name, n]) => (
                <div key={name}>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-[var(--color-bright)]">{name}</span>
                    <span className="font-mono text-[var(--color-muted)]">{n}</span>
                  </div>
                  <Bar value={n} max={intentMax} tone="info" />
                </div>
              ))}
            </div>
          ) : (
            <Empty>No consequential or typed requests recorded yet.</Empty>
          )}
        </Panel>
      </div>

      <Panel title="Adaptive sleep 2.0 — last cycle" right={adaptive.fingerprint ? <Badge tone="accent">fingerprint {adaptive.fingerprint}</Badge> : undefined}>
        {sleep?.available ? (
          <div className="grid gap-2 text-[12px] md:grid-cols-2">
            <div className="space-y-1">
              <Row k="Usefulness (mean)" v={hygiene.usefulness_mean ?? "—"} />
              <Row k="Weak nodes" v={hygiene.weak_nodes ?? "—"} />
              <Row k="Duplicate nodes archived" v={hygiene.archived_duplicates ?? "—"} />
              <Row k="Contradictions recorded" v={adaptive.contradictions?.recorded ?? "—"} />
              <Row k="Abstractions created" v={adaptive.abstractions?.created ?? "—"} />
            </div>
            <div className="space-y-1">
              <Row k="Rotation retention" v={retention.tested ? `${retention.passed}/${retention.tested}` : "—"} />
              <Row k="Skills unusable" v={adaptive.skills?.broken ?? "—"} />
              <Row k="Candidates promoted" v={promotion.promoted ?? "—"} />
              <Row k="Candidates held" v={promotion.held ?? "—"} />
              <Row k="Forgetting regret" v={adaptive.forgetting?.regret_rate ?? "—"} />
            </div>
          </div>
        ) : (
          <Empty>No completed sleep cycle recorded yet.</Empty>
        )}
      </Panel>

      <Panel title="Audit trail" right={<Badge tone="info">authorisation decisions</Badge>}>
        {data.audit.length ? (
          <table className="w-full text-left text-[11px]">
            <thead className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-muted)]">
              <tr>
                <th className="py-1">when</th>
                <th>action</th>
                <th>intent</th>
                <th>granted</th>
                <th>executed</th>
              </tr>
            </thead>
            <tbody>
              {data.audit.map((a, i) => (
                <tr key={`${a.ts}-${i}`} className="border-t border-[var(--color-edge)]">
                  <td className="py-1 font-mono text-[var(--color-muted)]">{a.ts.replace("T", " ").slice(0, 19)}</td>
                  <td>{a.action}</td>
                  <td>{a.intent || "—"}</td>
                  <td>
                    <Badge tone={a.authorized ? "good" : "bad"}>{a.authorized ? "yes" : "no"}</Badge>
                  </td>
                  <td className="text-[var(--color-muted)]">{a.detail?.executed ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty>No consequential action has been requested yet.</Empty>
        )}
      </Panel>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-[var(--color-muted)]">{k}</span>
      <span className="font-mono text-[var(--color-bright)]">{String(v)}</span>
    </div>
  );
}
