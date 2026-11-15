import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type ChatReply, type Status } from "./api";
import { Badge, Bar, Empty, Panel, fmtNum } from "./ui";

type Turn = {
  id: string;
  role: "user" | "brain";
  text: string;
  reply?: ChatReply;
  pending?: boolean;
  error?: string;
};

const SUGGESTIONS = [
  "Create a cinematic poster about patience, 1080x1350, warm amber light and a gold hairline",
  "Apply the emerald palette and make it minimal",
  "Write a Python function `solve(nums)` that returns the sum of a list of integers",
  "What palette reads as premium?",
  "Inspect my screenshot for layout bugs",
];

const SOURCE_TONE: Record<string, "good" | "accent" | "info" | "bad" | "muted"> = {
  skill: "good",
  memory: "info",
  neural: "accent",
  tool: "good",
  refuse: "bad",
};

export function ChatView({ status }: { status: Status | null }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [allowActions, setAllowActions] = useState(true);
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy) return;
      const uid = crypto.randomUUID();
      setTurns((t) => [...t, { id: uid, role: "user", text: message }]);
      const placeholder = crypto.randomUUID();
      setTurns((t) => [...t, { id: placeholder, role: "brain", text: "", pending: true }]);
      setInput("");
      setBusy(true);
      try {
        const reply = await api.chat(message, allowActions);
        setTurns((t) =>
          t.map((x) => (x.id === placeholder ? { ...x, text: reply.answer, reply, pending: false } : x)),
        );
      } catch (err) {
        setTurns((t) =>
          t.map((x) =>
            x.id === placeholder
              ? { ...x, pending: false, error: err instanceof Error ? err.message : "request failed" }
              : x,
          ),
        );
      } finally {
        setBusy(false);
      }
    },
    [allowActions, busy],
  );

  const upload = useCallback(async (file: File) => {
    const uid = crypto.randomUUID();
    setTurns((t) => [...t, { id: uid, role: "user", text: `[image] ${file.name}` }]);
    setBusy(true);
    try {
      const report = await api.inspectImage(file);
      const summary = [
        report.description,
        report.findings?.length ? `Findings: ${report.findings.join("; ")}` : "",
      ]
        .filter(Boolean)
        .join("\n");
      setTurns((t) => [
        ...t,
        {
          id: crypto.randomUUID(),
          role: "brain",
          text: summary || "Image inspected.",
          reply: {
            answer: summary,
            source: report.ui_class ? "neural" : "memory",
            confidence: report.ui_class_confidence || 0.5,
            grounding: [{ type: "vision", class: report.ui_class, scores: report.class_scores }],
            steps: [],
            verified: Boolean(report.ui_class),
            elapsed_ms: 0,
          },
        },
      ]);
    } catch (err) {
      setTurns((t) => [
        ...t,
        { id: crypto.randomUUID(), role: "brain", text: "", error: err instanceof Error ? err.message : "upload failed" },
      ]);
    } finally {
      setBusy(false);
    }
  }, []);

  const modelChip = useMemo(() => {
    if (!status) return "connecting…";
    if (status.brain.backend === "untrained") return "no checkpoint";
    return `${fmtNum(status.brain.params)} params`;
  }, [status]);

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
      <Panel className="flex min-h-0 flex-col" title="Copilot">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge tone={status?.editor.online ? "good" : "bad"}>
            {status?.editor.online ? "editor connected" : "editor offline"}
          </Badge>
          <Badge tone="accent">{modelChip}</Badge>
          <Badge tone="info">{status?.embedder ?? "—"}</Badge>
          <label className="ml-auto flex cursor-pointer items-center gap-2 text-[11px] text-[var(--color-muted)]">
            <input
              type="checkbox"
              checked={allowActions}
              onChange={(e) => setAllowActions(e.target.checked)}
              className="accent-[var(--color-accent)]"
            />
            allow editor actions
          </label>
        </div>

        <div ref={scroller} className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {turns.length === 0 && (
            <div className="space-y-3">
              <Empty>
                Ask for a poster, a function, or upload a UI screenshot. Every canvas action is verified
                against the live editor store before it counts as done.
              </Empty>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => void send(s)}
                    className="rounded-full border border-[var(--color-edge)] bg-[#12151d] px-3 py-1.5 text-left text-[11px] text-[var(--color-muted)] transition hover:border-[var(--color-accent)] hover:text-[var(--color-bright)]"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn) => (
            <div key={turn.id} className={`slide-in ${turn.role === "user" ? "flex justify-end" : ""}`}>
              {turn.role === "user" ? (
                <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-[#1c2231] px-3.5 py-2 text-[13px] leading-relaxed">
                  {turn.text}
                </div>
              ) : (
                <div className="max-w-[92%] space-y-2">
                  {turn.pending ? (
                    <div className="flex items-center gap-2 text-[12px] text-[var(--color-muted)]">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--color-accent)]" />
                      thinking, retrieving and verifying…
                    </div>
                  ) : turn.error ? (
                    <div className="rounded-xl border border-[color-mix(in_oklab,var(--color-bad)_40%,transparent)] bg-[color-mix(in_oklab,var(--color-bad)_10%,transparent)] px-3 py-2 text-[12px] text-[var(--color-bad)]">
                      {turn.error}
                    </div>
                  ) : (
                    <>
                      <div className="whitespace-pre-wrap rounded-2xl rounded-bl-sm border border-[var(--color-edge)] bg-[#101319] px-3.5 py-2.5 text-[13px] leading-relaxed">
                        {turn.text}
                      </div>
                      {turn.reply && (
                        <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                          <Badge tone={SOURCE_TONE[turn.reply.source] ?? "muted"}>{turn.reply.source}</Badge>
                          <Badge tone={turn.reply.verified ? "good" : "muted"}>
                            {turn.reply.verified ? "verified" : "unverified"}
                          </Badge>
                          <Badge tone="muted">conf {(turn.reply.confidence * 100).toFixed(0)}%</Badge>
                          <Badge tone="muted">{turn.reply.elapsed_ms.toFixed(0)} ms</Badge>
                          {turn.reply.steps.length > 0 && (
                            <Badge tone="info">{turn.reply.steps.length} action(s)</Badge>
                          )}
                        </div>
                      )}
                      {turn.reply?.steps && turn.reply.steps.length > 0 && (
                        <ol className="space-y-1 rounded-xl border border-[var(--color-edge)] bg-[#0d1015] p-2">
                          {turn.reply.steps.map((s, i) => (
                            <li key={i} className="flex items-start gap-2 text-[11px]">
                              <span className={s.ok ? "text-[var(--color-good)]" : "text-[var(--color-bad)]"}>
                                {s.ok ? "✓" : "✗"}
                              </span>
                              <span className="font-mono text-[var(--color-muted)]">{s.tool}</span>
                              <span className="min-w-0 flex-1 truncate text-[var(--color-bright)]">{s.summary}</span>
                              <span className="text-[var(--color-muted)]">{s.ms.toFixed(0)}ms</span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
          className="mt-3 flex items-end gap-2"
        >
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void upload(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={busy}
            title="Inspect an image"
            className="rounded-lg border border-[var(--color-edge)] bg-[#12151d] px-3 py-2 text-[12px] text-[var(--color-muted)] transition hover:text-[var(--color-bright)] disabled:opacity-40"
          >
            image
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
            rows={1}
            placeholder="Tell the brain what to build, analyse or remember…"
            className="max-h-32 min-h-[42px] flex-1 resize-y rounded-lg border border-[var(--color-edge)] bg-[#0d1015] px-3 py-2.5 text-[13px] outline-none placeholder:text-[var(--color-muted)] focus:border-[var(--color-accent)]"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-lg bg-[var(--color-accent)] px-4 py-2.5 text-[12px] font-semibold text-[#1a1206] transition disabled:opacity-40"
          >
            {busy ? "…" : "Send"}
          </button>
        </form>
      </Panel>

      <div className="hidden min-h-0 flex-col gap-3 xl:flex">
        <Panel title="Working memory">
          {status ? (
            <div className="space-y-2">
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-lg">{status.memory.working.items}</span>
                <span className="text-[11px] text-[var(--color-muted)]">
                  / {status.memory.working.capacity} slots
                </span>
              </div>
              <Bar value={status.memory.working.load} />
              <div className="grid grid-cols-2 gap-2 pt-1 text-[11px] text-[var(--color-muted)]">
                <div>tokens {fmtNum(status.memory.working.tokens)}</div>
                <div>budget {fmtNum(status.memory.working.token_budget)}</div>
                <div>pinned {status.memory.working.pinned}</div>
                <div>load {(status.memory.working.load * 100).toFixed(0)}%</div>
              </div>
            </div>
          ) : (
            <Empty>waiting for telemetry…</Empty>
          )}
        </Panel>

        <Panel title="Calibration" right={<Badge tone="info">{status?.calibration.n ?? 0} samples</Badge>}>
          {status && status.calibration.n > 0 ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="text-[var(--color-muted)]">ECE</div>
                <div className="text-right font-mono">{status.calibration.ece.toFixed(3)}</div>
                <div className="text-[var(--color-muted)]">Brier</div>
                <div className="text-right font-mono">{status.calibration.brier.toFixed(3)}</div>
              </div>
              {status.calibration.buckets.map((b) => (
                <div key={b.range} className="space-y-1">
                  <div className="flex justify-between text-[10px] text-[var(--color-muted)]">
                    <span>{b.range}</span>
                    <span>
                      {b.predicted.toFixed(2)} → {b.actual.toFixed(2)} (n={b.n})
                    </span>
                  </div>
                  <Bar value={b.actual} tone={Math.abs(b.predicted - b.actual) < 0.15 ? "good" : "bad"} />
                </div>
              ))}
            </div>
          ) : (
            <Empty>no calibration samples yet — run some verified actions</Empty>
          )}
        </Panel>

        <Panel title="Live events" className="min-h-0 flex-1 overflow-hidden">
          <div className="max-h-[280px] space-y-1 overflow-y-auto">
            {(status?.events ?? [])
              .slice()
              .reverse()
              .slice(0, 14)
              .map((e, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px]">
                  <span className="font-mono text-[10px] text-[var(--color-muted)]">
                    {new Date(e.ts * 1000).toLocaleTimeString("en-GB", { hour12: false })}
                  </span>
                  <span className="font-mono text-[var(--color-accent)]">{e.state}</span>
                  <span className="min-w-0 flex-1 truncate text-[var(--color-muted)]">{e.event}</span>
                </div>
              ))}
            {!status?.events.length && <Empty>no events yet</Empty>}
          </div>
        </Panel>
      </div>
    </div>
  );
}
