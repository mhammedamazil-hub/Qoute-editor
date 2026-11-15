import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";
import { Badge, Empty, Panel } from "./ui";

type VisualRow = {
  id: number;
  ts: string;
  sha256: string;
  width: number;
  height: number;
  ocr_text: string;
  description: string;
  labels: string;
  status: string;
  source: string;
};

type Report = Record<string, any>;

export function VisionView() {
  const [items, setItems] = useState<VisualRow[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    const r = await api.visual();
    setItems(r.items as unknown as VisualRow[]);
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(id);
  }, [load]);

  const inspect = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      setReport(await api.inspectImage(file));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "inspection failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="flex min-h-0 flex-col gap-3">
        <Panel className="flex-1" title="Image viewer">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              const f = e.dataTransfer.files?.[0];
              if (f) void inspect(f);
            }}
            className={`relative grid min-h-[340px] place-items-center rounded-lg border-2 border-dashed p-6 transition ${
              dragging
                ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_8%,transparent)]"
                : "border-[var(--color-edge)] bg-[#0a0c11]"
            }`}
          >
            {report ? (
              <div className="w-full">
                <div className="mb-2 flex flex-wrap items-center gap-1.5">
                  <Badge tone="info">
                    {report.width}×{report.height}
                  </Badge>
                  {report.ui_class && <Badge tone="good">{report.ui_class}</Badge>}
                  {typeof report.ui_class_confidence === "number" && report.ui_class_confidence > 0 && (
                    <Badge tone="accent">{(report.ui_class_confidence * 100).toFixed(0)}% confident</Badge>
                  )}
                  <Badge tone="muted">{report.boxes?.length ?? 0} regions</Badge>
                  {report.ocr_text && <Badge tone="muted">OCR {report.ocr_text.length} chars</Badge>}
                </div>
                <div className="relative overflow-hidden rounded-md border border-[var(--color-edge)] bg-[#05070a]">
                  <img
                    src={`data:image/png;base64,${report._preview ?? ""}`}
                    alt=""
                    className="hidden"
                  />
                  <ImageWithBoxes
                    url={`/api/vision/${report._id}/image`}
                    boxes={report.boxes ?? []}
                    width={report.width}
                    height={report.height}
                    preview={report._preview}
                  />
                </div>
                <p className="mt-2 text-[12px] leading-relaxed text-[var(--color-bright)]">{report.description}</p>
                {report.findings?.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {report.findings.map((f: string, i: number) => (
                      <li key={i} className="text-[11.5px] text-[var(--color-accent)]">
                        • {f}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <div className="text-center">
                <p className="text-[13px] text-[var(--color-bright)]">Drop a screenshot to inspect it</p>
                <p className="mt-1 text-[11.5px] text-[var(--color-muted)]">
                  OCR, layout region detection, overflow / contrast / truncation findings and neural UI
                  classification — all offline.
                </p>
                <button
                  onClick={() => fileRef.current?.click()}
                  className="mt-3 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-[12px] font-semibold text-[#1a1206]"
                >
                  Choose image
                </button>
              </div>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void inspect(f);
                e.target.value = "";
              }}
            />
            {busy && (
              <div className="absolute inset-0 grid place-items-center bg-black/50 text-[12px] text-[var(--color-bright)]">
                inspecting…
              </div>
            )}
          </div>
          {error && <p className="mt-2 text-[11.5px] text-[var(--color-bad)]">{error}</p>}
        </Panel>
      </div>

      <div className="flex min-h-0 flex-col gap-3">
        <Panel title="Neural classification">
          {report?.class_scores && Object.keys(report.class_scores).length > 0 ? (
            <div className="space-y-1.5">
              {Object.entries(report.class_scores as Record<string, number>)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <div key={k}>
                    <div className="flex justify-between text-[10.5px]">
                      <span className="text-[var(--color-muted)]">{k}</span>
                      <span className="font-mono">{(v * 100).toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[#1a1f2b]">
                      <div
                        className="h-full rounded-full bg-[var(--color-info)]"
                        style={{ width: `${v * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
            </div>
          ) : (
            <Empty>Drop an image to see per-class probabilities.</Empty>
          )}
        </Panel>

        <Panel title="Visual memory" className="min-h-0 flex-1 overflow-y-auto">
          {items.length === 0 ? (
            <Empty>No stored images yet.</Empty>
          ) : (
            <div className="grid grid-cols-3 gap-1.5">
              {items.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setReport({ ...(JSON.parse(JSON.stringify({}))) , _id: v.id, width: v.width, height: v.height, description: v.description, ocr_text: v.ocr_text, boxes: [], findings: [] })}
                  className="group relative aspect-square overflow-hidden rounded border border-[var(--color-edge)]"
                  title={v.description}
                >
                  <img
                    src={`/api/vision/${v.id}/image`}
                    alt=""
                    className="h-full w-full object-cover transition group-hover:scale-105"
                    loading="lazy"
                  />
                </button>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

/** Draws detected regions on top of the image, scaled to the rendered size. */
function ImageWithBoxes({
  url,
  boxes,
  width,
  height,
  preview,
}: {
  url: string;
  boxes: { x: number; y: number; w: number; h: number; color?: number[] }[];
  width: number;
  height: number;
  preview?: string;
}) {
  const [src, setSrc] = useState<string>(preview ? `data:image/png;base64,${preview}` : url);
  useEffect(() => {
    if (preview) {
      setSrc(`data:image/png;base64,${preview}`);
      return;
    }
    setSrc(url);
  }, [url, preview]);
  return (
    <div className="relative">
      <img src={src} alt="inspected" className="block w-full" />
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="pointer-events-none absolute inset-0 h-full w-full"
        preserveAspectRatio="none"
      >
        {boxes.slice(0, 24).map((b, i) => (
          <rect
            key={i}
            x={b.x}
            y={b.y}
            width={b.w}
            height={b.h}
            fill="none"
            stroke="#d9a441"
            strokeWidth={Math.max(1, width / 400)}
            opacity={0.85}
          />
        ))}
      </svg>
    </div>
  );
}
