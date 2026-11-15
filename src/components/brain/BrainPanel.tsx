/**
 * MiniCoder Brain — cognitive dashboard overlay.
 * Talks to the local `minicoder serve` FastAPI backend (same origin).
 * Offline-first: if the backend isn't running the panel says so honestly.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Brain,
  CircleDot,
  Database,
  Download,
  MessageSquare,
  Moon,
  Network,
  Search,
  Send,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { useUIStore, toast } from '@/store/uiStore';
import {
  brainClient,
  connectTelemetry,
  BrainOfflineError,
  type BrainStatus,
  type ChatResponse,
  type Episode,
  type GraphPayload,
  type Skill,
  type SleepReport,
} from '@/ai/brain/client';

type Tab = 'overview' | 'chat' | 'memory' | 'skills' | 'sleep' | 'graph';

const STATE_STYLES: Record<string, string> = {
  awake: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/30',
  thinking: 'bg-amber-400/15 text-amber-300 border-amber-400/30',
  tool_execution: 'bg-cyan-400/15 text-cyan-300 border-cyan-400/30',
  sleeping: 'bg-violet-400/15 text-violet-300 border-violet-400/30',
  github_training: 'bg-blue-400/15 text-blue-300 border-blue-400/30',
};

const TABS: { id: Tab; label: string; icon: typeof Brain }[] = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'memory', label: 'Memory', icon: Database },
  { id: 'skills', label: 'Skills', icon: Wrench },
  { id: 'sleep', label: 'Sleep', icon: Moon },
  { id: 'graph', label: 'Knowledge Graph', icon: Network },
];

function Card({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-line bg-ink-900/70 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">{label}</p>
      <p className={cn('mono-num mt-1 text-xl font-bold', accent ? 'text-accent' : 'text-ink-100')}>{value}</p>
      {sub && <p className="mt-0.5 text-[10px] text-ink-400">{sub}</p>}
    </div>
  );
}

function OfflineNote() {
  return (
    <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-[12px] text-amber-200">
      <p className="font-semibold">Brain backend offline</p>
      <p className="mt-1 text-amber-200/80">
        Start it with <code className="rounded bg-black/30 px-1">minicoder serve --port 8765</code> (or
        <code className="rounded bg-black/30 px-1 ml-1">minicoder chat</code> for the terminal), then reload. The
        editor itself works fully offline — only the live brain needs the Python backend.
      </p>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-ink-400">{children}</h3>;
}

/* ------------------------------------------------------------------ */
/* Overview                                                           */
/* ------------------------------------------------------------------ */
function OverviewTab({ status, onSleep, sleeping, events, onExport }: {
  status: BrainStatus | null;
  onSleep: () => void;
  sleeping: boolean;
  events: string[];
  onExport: () => void;
}) {
  if (!status) return <OfflineNote />;
  const c = status.memory_counts;
  const wm = status.working_memory;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <Card label="Episodic memory" value={c.episodes ?? 0} sub={`${c.episodes_active ?? 0} active`} accent />
        <Card label="Concepts" value={c.concepts ?? 0} />
        <Card label="Relations" value={c.relations ?? 0} />
        <Card label="Skills verified" value={c.skills_verified ?? 0} sub={`${c.skills ?? 0} total registered`} accent />
        <Card label="Sleep runs" value={c.sleep_runs ?? 0} />
        <Card label="Provenance rows" value={c.provenance ?? 0} />
        <Card label="Vector rows" value={c.vectors ?? 0} />
        <Card label="WM capacity" value={`${Math.round(wm.load * 100)}%`} sub={`${wm.items}/${wm.capacity} slots`} />
      </div>

      <div>
        <SectionTitle>Working memory load</SectionTitle>
        <div className="h-2.5 w-full overflow-hidden rounded-full bg-ink-800">
          <div
            className={cn('h-full rounded-full transition-all duration-700', wm.load > 0.85 ? 'bg-rose-400' : wm.load > 0.6 ? 'bg-amber-400' : 'bg-emerald-400')}
            style={{ width: `${Math.round(wm.load * 100)}%` }}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-primary" onClick={onSleep} disabled={sleeping}>
          <Moon size={14} /> {sleeping ? 'Sleeping…' : 'Trigger Sleep'}
        </button>
        <button type="button" className="btn" onClick={onExport}>
          <Download size={14} /> Export snapshot
        </button>
        <span className="text-[11px] text-ink-400">provider: {String(status.provider.default)}</span>
      </div>

      <div className="rounded-xl border border-line bg-ink-900/70 p-3 text-[11px] text-ink-300">
        <SectionTitle>Hardware profile</SectionTitle>
        <code className="block whitespace-pre-wrap break-all text-[10px] text-ink-400">
          {JSON.stringify(status.hardware, null, 0).slice(0, 400)}
        </code>
      </div>

      <div>
        <SectionTitle>Live telemetry</SectionTitle>
        <div className="max-h-36 overflow-y-auto rounded-xl border border-line bg-black/40 p-2 font-mono text-[10px] leading-relaxed text-emerald-300/80">
          {events.length === 0 ? <p className="text-ink-500">waiting for telemetry…</p> : events.map((e, i) => <p key={i}>{e}</p>)}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Chat                                                               */
/* ------------------------------------------------------------------ */
interface ChatMsg { role: 'user' | 'brain'; text: string; meta?: ChatResponse }

function ChatTab({ offline }: { offline: boolean }) {
  const [messages, setMessages] = useState<ChatMsg[]>([
    { role: 'brain', text: "I'm the MiniCoder brain: memory-grounded, offline, and honest about what I don't know. Ask me anything — I'll cite what I remember. Say `sleep` to make me consolidate." },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text }]);
    setBusy(true);
    try {
      const res = await brainClient.chat(text);
      setMessages((m) => [...m, { role: 'brain', text: res.reply, meta: res }]);
    } catch (e) {
      const msg = e instanceof BrainOfflineError ? 'Brain backend offline — start `minicoder serve` first.' : (e as Error).message;
      setMessages((m) => [...m, { role: 'brain', text: msg }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.map((m, i) => (
          <div key={i} className={cn('max-w-[85%] rounded-2xl px-3 py-2 text-[13px] leading-snug', m.role === 'user' ? 'ml-auto bg-accent text-white' : 'bg-ink-800 text-ink-100')}>
            <p className="whitespace-pre-wrap">{m.text}</p>
            {m.meta && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-white/10 pt-1.5 text-[10px] text-ink-400">
                <span className="rounded-full bg-black/30 px-2 py-0.5">route: {m.meta.route}</span>
                <span className="rounded-full bg-black/30 px-2 py-0.5">confidence: {m.meta.confidence.toFixed(2)}</span>
                {m.meta.citations.slice(0, 4).map((c) => (
                  <span key={c} className="rounded-full bg-black/30 px-2 py-0.5 font-mono">{c}</span>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <p className="text-[11px] text-ink-500">brain is thinking…</p>}
        <div ref={endRef} />
      </div>
      <div className="mt-3 flex items-center gap-2">
        <input
          className="h-10 flex-1 rounded-xl border border-line bg-ink-900 px-3 text-[13px] text-ink-100 outline-none placeholder:text-ink-500 focus:border-accent disabled:opacity-50"
          placeholder={offline ? 'Backend offline…' : 'Ask the brain… (e.g. "what do you remember about css grid?")'}
          value={input}
          disabled={offline || busy}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void send(); }}
          aria-label="Message the brain"
        />
        <button type="button" className="icon-btn h-10 w-10 border border-line" onClick={() => void send()} disabled={offline || busy || !input.trim()} aria-label="Send">
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Memory                                                             */
/* ------------------------------------------------------------------ */
function MemoryTab({ offline }: { offline: boolean }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<{ score: number; episode: Episode }[] | null>(null);
  const [recent, setRecent] = useState<Episode[]>([]);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRecent = useCallback(() => {
    brainClient.episodes(10).then(setRecent).catch(() => setRecent([]));
  }, []);
  useEffect(() => { loadRecent(); }, [loadRecent]);

  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setBusy(true); setError(null);
    try {
      setResults(await brainClient.searchEpisodes(q, 8));
    } catch (e) {
      setError(e instanceof BrainOfflineError ? 'offline' : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remember = async () => {
    const text = note.trim();
    if (!text) return;
    try {
      await brainClient.remember(text, ['manual']);
      setNote('');
      toast('Remembered with provenance', 'success');
      loadRecent();
    } catch {
      toast('Could not store memory — backend offline?', 'error');
    }
  };

  if (offline) return <OfflineNote />;
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto">
      <div>
        <SectionTitle>Search memory</SectionTitle>
        <div className="flex items-center gap-2">
          <div className="flex h-9 flex-1 items-center gap-2 rounded-lg border border-line bg-ink-900 px-2">
            <Search size={14} className="text-ink-500" />
            <input
              className="h-full flex-1 bg-transparent text-[12px] outline-none placeholder:text-ink-500"
              placeholder="semantic + keyword search…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void runSearch()}
            />
          </div>
          <button type="button" className="btn h-9" onClick={() => void runSearch()} disabled={busy}>Go</button>
        </div>
        {error && <p className="mt-1 text-[11px] text-rose-300">{error}</p>}
        {results && (
          <ul className="mt-2 space-y-1.5">
            {results.length === 0 && <li className="text-[11px] text-ink-500">no matches — honest empty result</li>}
            {results.map(({ score, episode }) => (
              <li key={episode.id} className="rounded-lg border border-line bg-ink-900/70 px-3 py-2 text-[11px]">
                <div className="flex items-center gap-2">
                  <span className="mono-num text-accent">{score.toFixed(2)}</span>
                  <span className={cn('rounded-full px-1.5 py-0.5 text-[9px] font-bold',
                    episode.verification_status === 'VERIFIED' ? 'bg-emerald-400/15 text-emerald-300' :
                    episode.verification_status === 'FAILED' ? 'bg-rose-400/15 text-rose-300' : 'bg-ink-700 text-ink-300')}>
                    {episode.verification_status}
                  </span>
                  <span className="ml-auto font-mono text-[9px] text-ink-500">{episode.id}</span>
                </div>
                <p className="mt-1 text-ink-200">{episode.situation}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <SectionTitle>Teach it something</SectionTitle>
        <div className="flex items-start gap-2">
          <textarea
            className="min-h-[64px] flex-1 resize-y rounded-lg border border-line bg-ink-900 p-2 text-[12px] outline-none placeholder:text-ink-500 focus:border-accent"
            placeholder="e.g. My deployment target is a Debian laptop on the LAN, Node 22…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <button type="button" className="btn btn-primary h-9" onClick={() => void remember()} disabled={!note.trim()}>Remember</button>
        </div>
      </div>

      <div>
        <SectionTitle>Recent episodes</SectionTitle>
        <ul className="space-y-1.5">
          {recent.map((ep) => (
            <li key={ep.id} className="flex items-start gap-2 rounded-lg border border-line bg-ink-900/70 px-3 py-2 text-[11px]">
              <CircleDot size={12} className="mt-0.5 shrink-0 text-ink-500" />
              <div className="min-w-0">
                <p className="text-ink-200">{ep.situation}</p>
                <p className="mt-0.5 font-mono text-[9px] text-ink-500">{ep.modality} · {new Date(ep.created_at).toLocaleString()} · {ep.id}</p>
              </div>
            </li>
          ))}
          {recent.length === 0 && <li className="text-[11px] text-ink-500">nothing remembered yet</li>}
        </ul>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Skills                                                             */
/* ------------------------------------------------------------------ */
function SkillsTab({ offline }: { offline: boolean }) {
  const [filter, setFilter] = useState<'ALL' | 'VERIFIED' | 'UNVERIFIED' | 'FAILED'>('VERIFIED');
  const [skills, setSkills] = useState<Skill[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (offline) return;
    brainClient.skills(filter === 'ALL' ? undefined : filter).then(setSkills).catch(() => setSkills([]));
  }, [offline, filter]);

  if (offline) return <OfflineNote />;
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto">
      <div className="flex items-center gap-1.5">
        {(['VERIFIED', 'UNVERIFIED', 'FAILED', 'ALL'] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={cn('rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-wider',
              filter === f ? 'border-accent bg-accent/15 text-accent' : 'border-line text-ink-400 hover:text-ink-200')}
          >
            {f}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-ink-500">{skills.length} skill{skills.length === 1 ? '' : 's'}</span>
      </div>
      <p className="text-[10px] text-ink-500">Only VERIFIED skills (100% of gates passing) are ever compiled into GitHub training data.</p>
      <ul className="space-y-2">
        {skills.map((s) => (
          <li key={s.id} className="rounded-xl border border-line bg-ink-900/70">
            <button type="button" className="flex w-full items-center gap-3 px-3 py-2.5 text-left" onClick={() => setExpanded(expanded === s.id ? null : s.id)}>
              <span className={cn('h-2 w-2 shrink-0 rounded-full',
                s.verification_status === 'VERIFIED' ? 'bg-emerald-400' : s.verification_status === 'FAILED' ? 'bg-rose-400' : 'bg-amber-400')} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-semibold text-ink-100">{s.name}</span>
                <span className="mt-0.5 block text-[10px] text-ink-400">{s.domain} · conf {s.confidence.toFixed(2)} · used {s.times_used}×</span>
              </span>
              <span className="font-mono text-[9px] text-ink-500">{s.id.slice(0, 12)}</span>
            </button>
            {expanded === s.id && (
              <div className="border-t border-line px-3 py-2 text-[11px] text-ink-300">
                <p>{s.description}</p>
                {s.reasoning_trace.length > 0 && (
                  <ol className="mt-2 list-decimal space-y-0.5 pl-4 text-[10px] text-ink-400">
                    {s.reasoning_trace.map((line, i) => <li key={i}>{line}</li>)}
                  </ol>
                )}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {s.verification.map((v) => (
                    <span key={v.name} className={cn('rounded-full px-2 py-0.5 font-mono text-[9px]',
                      v.passed ? 'bg-emerald-400/10 text-emerald-300' : 'bg-rose-400/10 text-rose-300')}>
                      {v.name}: {v.passed ? 'pass' : `fail (${v.exit_code})`}
                    </span>
                  ))}
                </div>
                {s.final_output && (
                  <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-black/40 p-2 font-mono text-[10px] text-ink-200">{s.final_output}</pre>
                )}
              </div>
            )}
          </li>
        ))}
        {skills.length === 0 && <li className="text-[11px] text-ink-500">no {filter.toLowerCase()} skills</li>}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Sleep                                                              */
/* ------------------------------------------------------------------ */
function SleepTab({ offline, onSleep, sleeping, report }: {
  offline: boolean; onSleep: () => void; sleeping: boolean; report: SleepReport | null;
}) {
  if (offline) return <OfflineNote />;
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto">
      <div className="rounded-xl border border-violet-400/20 bg-violet-400/5 p-4 text-[12px] text-ink-200">
        <p className="flex items-center gap-2 font-semibold text-violet-200"><Moon size={14} /> Computational sleep</p>
        <p className="mt-1 text-[11px] text-ink-300">
          Replays and ranks episodes → consolidates lessons &amp; graph links → discovers cross-modal patterns →
          resolves conflicts → archives low-priority memories (decay-scored, recoverable) → compiles VERIFIED
          skills into a JSONL training shard → dispatches to GitHub CI for adapter training. All seven stages are
          real; anything not verified is reported, never faked.
        </p>
        <button type="button" className="btn btn-primary mt-3" onClick={onSleep} disabled={sleeping}>
          <Zap size={14} /> {sleeping ? 'Sleeping — consolidating…' : 'Run full sleep cycle now'}
        </button>
      </div>

      {report ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-[10px] text-ink-400">
            <span className="rounded-full border border-line px-2 py-0.5">run {report.id}</span>
            <span>{new Date(report.started_at).toLocaleString()}</span>
            <span className="rounded-full border border-line px-2 py-0.5">trigger: {report.trigger}</span>
            <span className={cn('rounded-full border px-2 py-0.5',
              report.github_dispatch === 'dispatched' ? 'border-emerald-400/40 text-emerald-300' :
              report.github_dispatch === 'pending_dispatch' ? 'border-amber-400/40 text-amber-300' : 'border-line text-ink-300')}>
              github: {report.github_dispatch}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Card label="Replayed" value={report.episodes_reviewed} />
            <Card label="Lessons" value={report.lessons_consolidated} />
            <Card label="Concepts linked" value={report.concepts_linked} />
            <Card label="Merged dupes" value={report.duplicates_merged} />
            <Card label="Conflicts" value={report.conflicts_flagged} />
            <Card label="Archived" value={report.episodes_archived} />
            <Card label="Skills compiled" value={report.skills_compiled} accent />
            <Card label="Shard examples" value={report.shard_examples} accent />
          </div>
          {report.shard_path && (
            <div className="rounded-lg border border-line bg-ink-900/70 p-2 font-mono text-[10px] text-ink-300 break-all">
              shard: {report.shard_path}<br />sha256: {report.shard_sha256}
            </div>
          )}
          {report.weakness_domains.length > 0 && (
            <div>
              <SectionTitle>Weakness domains (from failure patterns)</SectionTitle>
              <div className="flex flex-wrap gap-1.5">
                {report.weakness_domains.map((d) => (
                  <span key={d} className="rounded-full bg-rose-400/10 px-2.5 py-1 text-[10px] font-semibold text-rose-300">{d}</span>
                ))}
              </div>
            </div>
          )}
          {report.notes.length > 0 && (
            <div>
              <SectionTitle>Consolidation notes</SectionTitle>
              <ul className="list-disc space-y-1 pl-4 text-[11px] text-ink-300">{report.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </div>
          )}
          {report.unresolved.length > 0 && (
            <div>
              <SectionTitle>Unresolved / flagged for you</SectionTitle>
              <ul className="list-disc space-y-1 pl-4 text-[11px] text-amber-200/90">{report.unresolved.map((u, i) => <li key={i}>{u}</li>)}</ul>
            </div>
          )}
        </div>
      ) : (
        <p className="text-[11px] text-ink-500">No sleep has run yet — the button above runs the real seven-stage cycle.</p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Knowledge graph                                                    */
/* ------------------------------------------------------------------ */
const KIND_COLORS: Record<string, string> = {
  concept: '#7dd3fc', fact: '#6ee7b7', preference: '#fcd34d',
  heuristic: '#f9a8d4', skill: '#c4b5fd',
};

function GraphTab({ offline }: { offline: boolean }) {
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (offline) return;
    brainClient.graph(150).then(setGraph).catch((e) => setError((e as Error).message));
  }, [offline]);

  const layout = useMemo(() => {
    if (!graph) return null;
    const n = graph.nodes.length;
    const R = 130, C = 160;
    const pos = new Map<string, { x: number; y: number }>();
    graph.nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / Math.max(1, n) - Math.PI / 2;
      const jitter = (i % 3) * 14;
      pos.set(node.id, { x: C + (R - jitter) * Math.cos(angle), y: C + (R - jitter) * Math.sin(angle) });
    });
    return pos;
  }, [graph]);

  if (offline) return <OfflineNote />;
  if (error) return <p className="text-[11px] text-rose-300">graph error: {error}</p>;
  if (!graph) return <p className="text-[11px] text-ink-500">loading graph…</p>;
  if (graph.nodes.length === 0) return <p className="text-[11px] text-ink-500">the graph is empty — it grows as you chat and sleep.</p>;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3 text-[10px] text-ink-400">
        <span>{graph.total_nodes} nodes · {graph.total_edges} edges</span>
        {Object.entries(KIND_COLORS).map(([kind, color]) => (
          <span key={kind} className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: color }} />{kind}</span>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-line bg-black/30">
        <svg viewBox="0 0 320 320" className="h-full w-full" role="img" aria-label="Concept knowledge graph">
          {graph.edges.map((e, i) => {
            const a = layout?.get(e.src); const b = layout?.get(e.dst);
            if (!a || !b) return null;
            return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#475569" strokeOpacity={0.55} strokeWidth={0.6} />;
          })}
          {graph.nodes.map((node) => {
            const p = layout?.get(node.id); if (!p) return null;
            const r = 3 + node.confidence * 4;
            return (
              <g key={node.id}>
                <title>{`${node.label} (${node.kind}, conf ${node.confidence.toFixed(2)})`}</title>
                <circle cx={p.x} cy={p.y} r={r} fill={KIND_COLORS[node.kind] ?? '#94a3b8'} fillOpacity={0.9} stroke="#0f172a" strokeWidth={0.6} />
                {node.confidence >= 0.6 && (
                  <text x={p.x} y={p.y - r - 1.5} textAnchor="middle" fontSize={4.5} fill="#e2e8f0" stroke="none">
                    {node.label.slice(0, 26)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      <p className="text-[9px] text-ink-500">Deterministic circular projection of the live NetworkX graph (SQLite-backed). Hover any node for confidence + kind. Edges are typed relations: solves · causes · depends_on · contradicts · visually_resembles.</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Panel shell                                                        */
/* ------------------------------------------------------------------ */
export function BrainPanel() {
  const brainOpen = useUIStore((s) => s.brainOpen);
  const setBrainOpen = useUIStore((s) => s.setBrainOpen);
  const [tab, setTab] = useState<Tab>('overview');
  const [status, setStatus] = useState<BrainStatus | null>(null);
  const [offline, setOffline] = useState(false);
  const [events, setEvents] = useState<string[]>([]);
  const [sleeping, setSleeping] = useState(false);
  const [report, setReport] = useState<SleepReport | null>(null);

  const pushEvent = useCallback((note: string) => {
    setEvents((ev) => [...ev.slice(-9), `${new Date().toLocaleTimeString()} · ${note}`]);
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await brainClient.status());
      setOffline(false);
    } catch (e) {
      if (e instanceof BrainOfflineError) setOffline(true);
    }
  }, []);

  useEffect(() => {
    if (!brainOpen) return;
    void refreshStatus();
    brainClient.sleepReport().then(setReport).catch(() => undefined);
    const poll = window.setInterval(() => void refreshStatus(), 2500);
    const unsubscribe = connectTelemetry(
      (s) => { setStatus(s); setOffline(false); },
      pushEvent,
    );
    return () => { window.clearInterval(poll); unsubscribe(); };
  }, [brainOpen, refreshStatus, pushEvent]);

  useEffect(() => {
    if (!brainOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setBrainOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [brainOpen, setBrainOpen]);

  const runSleep = useCallback(async () => {
    setSleeping(true);
    pushEvent('sleep requested via UI');
    try {
      const result = await brainClient.sleep('ui_requested');
      setReport(result);
      pushEvent(`sleep done: ${result.skills_compiled} skills compiled, ${result.episodes_archived} archived`);
      toast(`Sleep complete — ${result.shard_examples} training examples compiled`, 'success');
      setTab('sleep');
    } catch (e) {
      toast(e instanceof BrainOfflineError ? 'Brain backend offline' : `Sleep failed: ${(e as Error).message.slice(0, 120)}`, 'error');
    } finally {
      setSleeping(false);
      void refreshStatus();
    }
  }, [pushEvent, refreshStatus]);

  const exportSnapshot = useCallback(async () => {
    try {
      const out = await brainClient.exportSnapshot();
      toast('Snapshot exported', 'success', out.path.slice(-80));
      pushEvent(`snapshot exported (${Math.round(out.size_bytes / 1024)} KB)`);
    } catch {
      toast('Snapshot export failed — backend offline?', 'error');
    }
  }, [pushEvent]);

  if (!brainOpen) return null;
  const state = status?.state ?? 'offline';

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink-950 text-ink-100" role="dialog" aria-modal="true" aria-label="MiniCoder Brain">
      <header className="safe-top flex h-14 shrink-0 items-center gap-3 border-b border-line bg-ink-900/80 px-3 sm:px-4">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent/15 text-accent">
          <Brain size={20} />
        </span>
        <span className="min-w-0">
          <span className="block text-[13px] font-bold leading-tight">MiniCoder Brain</span>
          <span className="hidden text-[10px] text-ink-400 sm:block">compact cognitive core · offline-first · memory-grounded</span>
        </span>
        <span className={cn('ml-2 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider', STATE_STYLES[state] ?? 'border-line text-ink-300')}>
          {state.replace('_', ' ')}
        </span>
        <button type="button" className="icon-btn ml-auto" onClick={() => setBrainOpen(false)} aria-label="Close brain panel">
          <X size={18} />
        </button>
      </header>

      {offline && (
        <div className="border-b border-amber-400/30 bg-amber-400/10 px-4 py-1.5 text-center text-[10px] text-amber-200">
          Backend offline — editor unaffected. Run <code>minicoder serve</code> to wake the brain.
        </div>
      )}

      <nav className="flex h-11 shrink-0 items-stretch gap-1 overflow-x-auto border-b border-line bg-ink-900/50 px-2" aria-label="Brain sections">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            aria-selected={tab === id}
            className={cn('flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 text-[11px] font-semibold',
              tab === id ? 'border-accent text-accent' : 'border-transparent text-ink-400 hover:text-ink-200')}
          >
            <Icon size={13} /> {label}
          </button>
        ))}
      </nav>

      <main className="min-h-0 flex-1 overflow-hidden p-3 sm:p-4">
        <div className="mx-auto h-full max-w-5xl overflow-hidden">
          {tab === 'overview' && <div className="h-full overflow-y-auto"><OverviewTab status={status} onSleep={() => void runSleep()} sleeping={sleeping} events={events} onExport={() => void exportSnapshot()} /></div>}
          {tab === 'chat' && <ChatTab offline={offline} />}
          {tab === 'memory' && <MemoryTab offline={offline} />}
          {tab === 'skills' && <SkillsTab offline={offline} />}
          {tab === 'sleep' && <SleepTab offline={offline} onSleep={() => void runSleep()} sleeping={sleeping} report={report} />}
          {tab === 'graph' && <GraphTab offline={offline} />}
        </div>
      </main>
    </div>
  );
}
