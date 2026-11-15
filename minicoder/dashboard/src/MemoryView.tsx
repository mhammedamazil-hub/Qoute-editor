import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import { Badge, Empty, Panel } from "./ui";

type Episode = {
  id: number;
  ts: string;
  modality: string;
  situation: string;
  objective: string;
  result: string;
  status: string;
  lessons: string;
  confidence: number;
  surprise: number;
  consolidated: number;
  source: string;
};

type SkillRow = {
  id: number;
  slug: string;
  name: string;
  description: string;
  domain: string;
  status: string;
  confidence: number;
  exported: number;
  verified_at: string | null;
  used_count: number;
};

const STATUS_TONE: Record<string, "good" | "bad" | "muted" | "accent"> = {
  VERIFIED: "good",
  FAILED: "bad",
  UNVERIFIED: "muted",
  QUARANTINED: "accent",
};

export function MemoryView() {
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [skills, setSkills] = useState<SkillRow[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Record<string, unknown[]> | null>(null);
  const [filter, setFilter] = useState<"all" | "VERIFIED" | "FAILED">("all");

  const load = useCallback(async () => {
    const [e, s] = await Promise.all([api.episodes(), api.skills()]);
    setEpisodes(e.items as unknown as Episode[]);
    setSkills(s.items as unknown as SkillRow[]);
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 8000);
    return () => window.clearInterval(id);
  }, [load]);

  const search = async () => {
    if (!query.trim()) return setResults(null);
    const r = await fetch(`/api/memory/search?q=${encodeURIComponent(query)}&limit=6`).then((x) => x.json());
    setResults(r);
  };

  const shown = episodes.filter((e) => filter === "all" || e.status === filter);

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 xl:grid-cols-2">
      <Panel
        title="Episodic memory"
        className="flex min-h-0 flex-col"
        right={
          <div className="flex items-center gap-1.5">
            {(["all", "VERIFIED", "FAILED"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-md px-2 py-0.5 text-[10px] ${
                  filter === f
                    ? "bg-[var(--color-accent)] text-[#1a1206]"
                    : "border border-[var(--color-edge)] text-[var(--color-muted)]"
                }`}
              >
                {f.toLowerCase()}
              </button>
            ))}
          </div>
        }
      >
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {shown.length === 0 && <Empty>No episodes yet. Chat with the brain or run the agent.</Empty>}
          {shown.map((e) => (
            <article key={e.id} className="rounded-lg border border-[var(--color-edge)] bg-[#0d1015] p-2.5">
              <header className="mb-1 flex flex-wrap items-center gap-1.5">
                <Badge tone={STATUS_TONE[e.status] ?? "muted"}>{e.status}</Badge>
                <Badge tone="info">{e.modality}</Badge>
                <span className="text-[10px] text-[var(--color-muted)]">
                  #{e.id} · {new Date(e.ts).toLocaleString("en-GB", { hour12: false })}
                </span>
                <span className="ml-auto text-[10px] text-[var(--color-muted)]">
                  conf {(e.confidence * 100).toFixed(0)}% · surprise {(e.surprise * 100).toFixed(0)}%
                </span>
              </header>
              <p className="text-[12px] leading-snug text-[var(--color-bright)]">{e.situation}</p>
              {e.result && <p className="mt-1 line-clamp-2 text-[11px] text-[var(--color-muted)]">{e.result}</p>}
              {e.lessons && (
                <p className="mt-1 border-l-2 border-[var(--color-accent)] pl-2 text-[11px] italic text-[var(--color-muted)]">
                  {e.lessons}
                </p>
              )}
            </article>
          ))}
        </div>
      </Panel>

      <div className="flex min-h-0 flex-col gap-3">
        <Panel title="Procedural memory (skills)">
          <div className="max-h-[320px] space-y-1.5 overflow-y-auto pr-1">
            {skills.length === 0 && <Empty>No skills staged yet.</Empty>}
            {skills.map((s) => (
              <div key={s.id} className="rounded-md border border-[var(--color-edge)] bg-[#0d1015] p-2">
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-[11px] text-[var(--color-bright)]">{s.slug}</span>
                  <Badge tone={STATUS_TONE[s.status] ?? "muted"}>{s.status}</Badge>
                  {s.exported ? <Badge tone="info">exported</Badge> : <Badge tone="accent">staged</Badge>}
                  <span className="ml-auto text-[10px] text-[var(--color-muted)]">
                    {s.domain} · used {s.used_count}
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-[11px] text-[var(--color-muted)]">{s.description}</p>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Recall probe">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void search();
            }}
            className="flex gap-2"
          >
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="search memories, e.g. 'flexbox overflow'"
              className="flex-1 rounded-md border border-[var(--color-edge)] bg-[#0d1015] px-2.5 py-1.5 text-[12px] outline-none focus:border-[var(--color-accent)]"
            />
            <button className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-[11px] font-semibold text-[#1a1206]">
              search
            </button>
          </form>
          <div className="mt-2 min-h-0 flex-1 space-y-2 overflow-y-auto">
            {results &&
              Object.entries(results).map(([key, rows]) => (
                <div key={key}>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--color-muted)]">
                    {key} ({rows.length})
                  </div>
                  {rows.slice(0, 4).map((r, i) => {
                    const row = r as Record<string, unknown>;
                    return (
                      <div key={i} className="mb-1 rounded border border-[var(--color-edge)] bg-[#0d1015] p-1.5 text-[11px]">
                        <span className="text-[var(--color-bright)]">
                          {String(row.label ?? row.situation ?? row.slug ?? row.description ?? "")}
                        </span>
                        {typeof row.score === "number" && (
                          <span className="ml-1.5 font-mono text-[10px] text-[var(--color-accent)]">
                            {row.score.toFixed(3)}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))}
            {!results && <Empty>Search to inspect what the brain can recall right now.</Empty>}
          </div>
        </Panel>
      </div>
    </div>
  );
}
