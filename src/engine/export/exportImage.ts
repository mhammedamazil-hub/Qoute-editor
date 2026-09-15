import { getContentGroup } from '../canvas/stageRegistry';
import { useEditorStore } from '@/store/editorStore';

export type ExportFormat = 'png' | 'jpeg' | 'webp';

export interface ExportOptions {
  width: number;
  height: number;
  format: ExportFormat;
  quality: number;
}

const MAX_EXPORT_PIXELS = 36_000_000; // ~6000×6000

/** Rasterizes the live scene group (never the transformer/guides) at the requested resolution. */
export async function renderExport(opts: ExportOptions): Promise<Blob> {
  const group = getContentGroup();
  if (!group) throw new Error('Canvas is not ready.');
  const { doc, zoom, pan } = useEditorStore.getState();
  const targetW = Math.round(opts.width), targetH = Math.round(opts.height);
  if (targetW * targetH > MAX_EXPORT_PIXELS) throw new Error('Export size too large for the browser. Try a smaller resolution.');
  const ratio = targetW / (doc.canvas.width * zoom);
  const mime = opts.format === 'png' ? 'image/png' : opts.format === 'jpeg' ? 'image/jpeg' : 'image/webp';
  const canvas = group.toCanvas({
    x: pan.x,
    y: pan.y,
    width: doc.canvas.width * zoom,
    height: doc.canvas.height * zoom,
    pixelRatio: ratio,
  });
  // Ensure exact output size (rounding safety) and opaque background for jpeg.
  const out = document.createElement('canvas');
  out.width = targetW;
  out.height = targetH;
  const ctx = out.getContext('2d');
  if (!ctx) throw new Error('Canvas unavailable');
  if (opts.format === 'jpeg') {
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, targetW, targetH);
  }
  ctx.drawImage(canvas, 0, 0, targetW, targetH);
  const blob = await new Promise<Blob | null>((resolve) => out.toBlob(resolve, mime, opts.quality));
  if (!blob) throw new Error('Failed to encode image.');
  if (mime !== 'image/png' && blob.type !== mime) {
    // Browser fell back to PNG (e.g. no webp encoder) — still return a valid file.
    return blob;
  }
  return blob;
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
