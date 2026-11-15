import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type GraphEdge, type GraphNode } from "./api";
import { Badge, Empty, Panel } from "./ui";

/**
 * Hand-rolled force-directed knowledge-graph explorer.
 *
 * A canvas simulation (Fruchterman-Reingold style repulsion + spring edges)
 * avoids a 300 KB graph library dependency while still giving real interactive
 * behaviour: drag nodes, pan, zoom, click to inspect.
 */

const KIND_COLOR: Record<string, string> = {
  concept: "#5b9cf5",
  heuristic: "#d9a441",
  fact: "#3fb98a",
  pattern: "#c084fc",
  user_preference: "#f472b6",
  idiom: "#22d3ee",
  default: "#8892a4",
};

type Sim = { id: number; x: number; y: number; vx: number; vy: number; node: GraphNode };

export function GraphView() {
  const [data, setData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>({ nodes: [], edges: [] });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const simRef = useRef<Sim[]>([]);
  const viewRef = useRef({ scale: 1, x: 0, y: 0 });
  const dragRef = useRef<{ node: Sim | null; panning: boolean; sx: number; sy: number }>({
    node: null,
    panning: false,
    sx: 0,
    sy: 0,
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const g = await api.graph();
      setData(g);
      const n = Math.max(1, g.nodes.length);
      simRef.current = g.nodes.map((node, i) => {
        const angle = (i / n) * Math.PI * 2;
        const radius = 120 + (i % 5) * 26;
        return { id: node.id, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius, vx: 0, vy: 0, node };
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 20000);
    return () => window.clearInterval(id);
  }, [load]);

  const neighbours = useMemo(() => {
    if (!selected) return new Set<number>();
    const s = new Set<number>([selected.id]);
    for (const e of data.edges) {
      if (e.src === selected.id) s.add(e.dst);
      if (e.dst === selected.id) s.add(e.src);
    }
    return s;
  }, [selected, data.edges]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let frame = 0;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const step = () => {
      const sims = simRef.current;
      const byId = new Map(sims.map((s) => [s.id, s]));
      frame += 1;
      // Repulsion
      for (let i = 0; i < sims.length; i++) {
        for (let j = i + 1; j < sims.length; j++) {
          const a = sims[i];
          const b = sims[j];
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 0.01) {
            dx = Math.random() - 0.5;
            dy = Math.random() - 0.5;
            d2 = 1;
          }
          const force = 4200 / d2;
          const d = Math.sqrt(d2);
          a.vx += (dx / d) * force;
          a.vy += (dy / d) * force;
          b.vx -= (dx / d) * force;
          b.vy -= (dy / d) * force;
        }
      }
      // Springs
      for (const e of data.edges) {
        const a = byId.get(e.src);
        const b = byId.get(e.dst);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.hypot(dx, dy) || 1;
        const target = 90;
        const force = (d - target) * 0.012;
        a.vx += (dx / d) * force;
        a.vy += (dy / d) * force;
        b.vx -= (dx / d) * force;
        b.vy -= (dy / d) * force;
      }
      // Centre gravity + integrate
      for (const s of sims) {
        s.vx -= s.x * 0.0016;
        s.vy -= s.y * 0.0016;
        if (dragRef.current.node === s) continue;
        s.vx *= 0.86;
        s.vy *= 0.86;
        s.x += s.vx;
        s.y += s.vy;
      }

      // Draw
      const rect = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);
      const view = viewRef.current;
      ctx.save();
      ctx.translate(rect.width / 2 + view.x, rect.height / 2 + view.y);
      ctx.scale(view.scale, view.scale);

      for (const e of data.edges) {
        const a = byId.get(e.src);
        const b = byId.get(e.dst);
        if (!a || !b) continue;
        const hot = selected && (e.src === selected.id || e.dst === selected.id);
        ctx.strokeStyle = hot ? "rgba(217,164,65,0.85)" : "rgba(120,132,158,0.20)";
        ctx.lineWidth = hot ? 1.8 : 1;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        if (hot) {
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          ctx.fillStyle = "rgba(217,164,65,0.9)";
          ctx.font = "9px ui-monospace, monospace";
          ctx.fillText(e.relation, mx + 3, my - 3);
        }
      }

      for (const s of sims) {
        const dim = selected && !neighbours.has(s.id);
        const r = 6 + Math.min(7, s.node.confidence * 8);
        ctx.beginPath();
        ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
        ctx.fillStyle = KIND_COLOR[s.node.kind] ?? KIND_COLOR.default;
        ctx.globalAlpha = dim ? 0.25 : 1;
        ctx.fill();
        if (s.node.status === "VERIFIED" && !dim) {
          ctx.beginPath();
          ctx.arc(s.x, s.y, r + 3, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(63,185,138,0.7)";
          ctx.lineWidth = 1.2;
          ctx.stroke();
        }
        if (s === dragRef.current.node) {
          ctx.beginPath();
          ctx.arc(s.x, s.y, r + 6, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(217,164,65,0.9)";
          ctx.stroke();
        }
        if (sims.length <= 42 || selected?.id === s.id || neighbours.has(s.id)) {
          ctx.globalAlpha = dim ? 0.25 : 0.92;
          ctx.fillStyle = "#cfd6e4";
          ctx.font = "9.5px ui-sans-serif, system-ui";
          const label = s.node.label.length > 26 ? `${s.node.label.slice(0, 26)}…` : s.node.label;
          ctx.fillText(label, s.x + r + 4, s.y + 3);
        }
        ctx.globalAlpha = 1;
      }
      ctx.restore();
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [data, selected, neighbours]);

  const hitTest = (clientX: number, clientY: number): Sim | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const view = viewRef.current;
    const x = (clientX - rect.left - rect.width / 2 - view.x) / view.scale;
    const y = (clientY - rect.top - rect.height / 2 - view.y) / view.scale;
    let best: Sim | null = null;
    let bestD = 14;
    for (const s of simRef.current) {
      const d = Math.hypot(s.x - x, s.y - y);
      if (d < bestD) {
        best = s;
        bestD = d;
      }
    }
    return best;
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_300px]">
      <Panel
        title="Knowledge graph"
        className="flex min-h-0 flex-col"
        right={
          <div className="flex items-center gap-1.5">
            <Badge tone="muted">{data.nodes.length} nodes</Badge>
            <Badge tone="muted">{data.edges.length} edges</Badge>
            <button
              onClick={() => void load()}
              className="rounded-md border border-[var(--color-edge)] px-2 py-0.5 text-[10px] text-[var(--color-muted)] hover:text-[var(--color-bright)]"
            >
              refresh
            </button>
          </div>
        }
      >
        <div className="relative min-h-[380px] flex-1 overflow-hidden rounded-lg border border-[var(--color-edge)] bg-[#080a0e]">
          <div className="pointer-events-none absolute inset-0 grid-fade opacity-40" />
          <canvas
            ref={canvasRef}
            className="absolute inset-0 h-full w-full cursor-grab active:cursor-grabbing"
            onMouseDown={(e) => {
              const hit = hitTest(e.clientX, e.clientY);
              if (hit) {
                dragRef.current = { node: hit, panning: false, sx: e.clientX, sy: e.clientY };
                setSelected(hit.node);
              } else {
                dragRef.current = { node: null, panning: true, sx: e.clientX, sy: e.clientY };
              }
            }}
            onMouseMove={(e) => {
              const d = dragRef.current;
              if (d.node) {
                const rect = e.currentTarget.getBoundingClientRect();
                const view = viewRef.current;
                d.node.x = (e.clientX - rect.left - rect.width / 2 - view.x) / view.scale;
                d.node.y = (e.clientY - rect.top - rect.height / 2 - view.y) / view.scale;
                d.node.vx = 0;
                d.node.vy = 0;
              } else if (d.panning) {
                viewRef.current.x += e.clientX - d.sx;
                viewRef.current.y += e.clientY - d.sy;
                d.sx = e.clientX;
                d.sy = e.clientY;
              }
            }}
            onMouseUp={() => {
              dragRef.current = { node: null, panning: false, sx: 0, sy: 0 };
            }}
            onMouseLeave={() => {
              dragRef.current = { node: null, panning: false, sx: 0, sy: 0 };
            }}
            onWheel={(e) => {
              e.preventDefault();
              const v = viewRef.current;
              v.scale = Math.max(0.3, Math.min(3, v.scale * (e.deltaY > 0 ? 0.92 : 1.08)));
            }}
          />
          {loading && data.nodes.length === 0 && (
            <div className="absolute inset-0 grid place-items-center text-[12px] text-[var(--color-muted)]">
              loading graph…
            </div>
          )}
          {!loading && data.nodes.length === 0 && (
            <div className="absolute inset-0 grid place-items-center px-6 text-center text-[12px] text-[var(--color-muted)]">
              The graph is empty. Run a sleep cycle to consolidate episodes into concepts.
            </div>
          )}
          <div className="absolute bottom-2 left-2 flex flex-wrap gap-2 rounded-md bg-black/40 px-2 py-1 text-[9px] text-[var(--color-muted)]">
            {Object.entries(KIND_COLOR)
              .filter(([k]) => k !== "default")
              .map(([k, c]) => (
                <span key={k} className="inline-flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} />
                  {k}
                </span>
              ))}
          </div>
        </div>
      </Panel>

      <Panel title="Inspector" className="min-h-0 overflow-y-auto">
        {selected ? (
          <div className="space-y-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[var(--color-muted)]">label</div>
              <div className="text-[13px] font-medium">{selected.label}</div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Badge tone="info">{selected.kind}</Badge>
              <Badge tone={selected.status === "VERIFIED" ? "good" : "bad"}>{selected.status}</Badge>
              <Badge tone="muted">conf {(selected.confidence * 100).toFixed(0)}%</Badge>
            </div>
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--color-muted)]">content</div>
              <p className="whitespace-pre-wrap rounded-md border border-[var(--color-edge)] bg-[#0d1015] p-2 text-[11.5px] leading-relaxed text-[var(--color-bright)]">
                {selected.content || "(no content)"}
              </p>
            </div>
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--color-muted)]">connections</div>
              <ul className="space-y-1 text-[11px]">
                {data.edges
                  .filter((e) => e.src === selected.id || e.dst === selected.id)
                  .map((e, i) => {
                    const otherId = e.src === selected.id ? e.dst : e.src;
                    const other = data.nodes.find((n) => n.id === otherId);
                    return (
                      <li key={i} className="flex items-center gap-1.5">
                        <span className="font-mono text-[10px] text-[var(--color-accent)]">{e.relation}</span>
                        <button
                          onClick={() => other && setSelected(other)}
                          className="min-w-0 flex-1 truncate text-left text-[var(--color-muted)] hover:text-[var(--color-bright)]"
                        >
                          {other?.label ?? `#${otherId}`}
                        </button>
                      </li>
                    );
                  })}
              </ul>
            </div>
          </div>
        ) : (
          <Empty>Click a node to inspect it. Drag to rearrange, scroll to zoom.</Empty>
        )}
      </Panel>
    </div>
  );
}
