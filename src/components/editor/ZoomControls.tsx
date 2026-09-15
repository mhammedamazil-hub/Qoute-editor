import { Maximize2, Minus, Plus } from 'lucide-react';
import { useEditorStore } from '@/store/editorStore';
import { getStage } from '@/engine/canvas/stageRegistry';

export function zoomTo(newZoom: number) {
  const s = useEditorStore.getState();
  const stage = getStage();
  const w = stage?.width() ?? 800, h = stage?.height() ?? 600;
  const center = { x: w / 2, y: h / 2 };
  const world = { x: (center.x - s.pan.x) / s.zoom, y: (center.y - s.pan.y) / s.zoom };
  const z = Math.min(8, Math.max(0.05, newZoom));
  s.setZoom(z, { x: center.x - world.x * z, y: center.y - world.y * z });
}

export function fitToScreen(padding = 48) {
  const s = useEditorStore.getState();
  const stage = getStage();
  if (!stage) return;
  const w = stage.width(), h = stage.height();
  const z = Math.max(0.02, Math.min((w - padding * 2) / s.doc.canvas.width, (h - padding * 2) / s.doc.canvas.height));
  s.setZoom(z, { x: (w - s.doc.canvas.width * z) / 2, y: (h - s.doc.canvas.height * z) / 2 });
}

export function ZoomControls({ compact = false }: { compact?: boolean }) {
  const zoom = useEditorStore((s) => s.zoom);
  return (
    <div className="flex items-center gap-0.5" role="group" aria-label="Zoom">
      <button className="icon-btn h-7 w-7" title="Zoom out (−)" aria-label="Zoom out" onClick={() => zoomTo(zoom / 1.2)}><Minus size={14} /></button>
      <button className="h-7 min-w-[52px] rounded-md px-1.5 font-mono text-[11px] text-ink-200 hover:bg-ink-800" title="Zoom to 100%" onClick={() => zoomTo(1)}>{Math.round(zoom * 100)}%</button>
      <button className="icon-btn h-7 w-7" title="Zoom in (+)" aria-label="Zoom in" onClick={() => zoomTo(zoom * 1.2)}><Plus size={14} /></button>
      <button className="icon-btn h-7 w-7" title="Fit to screen (Shift+1)" aria-label="Fit to screen" onClick={() => fitToScreen(compact ? 16 : 48)}><Maximize2 size={14} /></button>
    </div>
  );
}
