import type { ImageAdjustments, ImageElement, ImageMask } from '@/types/elements';

const MAX_UPLOAD_DIM = 2560;

/** Decodes an uploaded file, downscaling huge images to a safe size while retaining export quality. */
export async function decodeUpload(file: File): Promise<{ dataUrl: string; width: number; height: number }> {
  const allowed = ['image/jpeg', 'image/png', 'image/webp', 'image/svg+xml'];
  if (!allowed.includes(file.type)) throw new Error('Unsupported image type. Use JPG, PNG, WEBP or SVG.');
  const objectUrl = URL.createObjectURL(file);
  try {
    const img = await loadImage(objectUrl);
    let w = img.naturalWidth || img.width;
    let h = img.naturalHeight || img.height;
    if (!w || !h) throw new Error('Could not read image dimensions.');
    const isSvg = file.type === 'image/svg+xml';
    const scale = Math.min(1, MAX_UPLOAD_DIM / Math.max(w, h));
    if (scale === 1 && !isSvg && file.size < 6 * 1024 * 1024) {
      const dataUrl = await blobToDataUrl(file);
      return { dataUrl, width: w, height: h };
    }
    // Re-encode (also rasterizes SVG safely: no script execution because it is drawn to canvas).
    if (isSvg && Math.max(w, h) < 1024) {
      const s = 1024 / Math.max(w, h);
      w = Math.round(w * s);
      h = Math.round(h * s);
    } else {
      w = Math.round(w * scale);
      h = Math.round(h * scale);
    }
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Canvas unavailable');
    ctx.drawImage(img, 0, 0, w, h);
    const hasAlpha = file.type === 'image/png' || isSvg || file.type === 'image/webp';
    const dataUrl = hasAlpha ? canvas.toDataURL('image/png') : canvas.toDataURL('image/jpeg', 0.92);
    return { dataUrl, width: w, height: h };
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error('Failed to read file'));
    r.readAsDataURL(blob);
  });
}

export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.decoding = 'async';
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Failed to load image'));
    img.src = src;
  });
}

/* ---------- asset image cache ---------- */
const imageCache = new Map<string, HTMLImageElement>();
const pending = new Map<string, Promise<HTMLImageElement>>();

export function getCachedImage(assetId: string, src: string | undefined, onReady?: () => void): HTMLImageElement | null {
  const hit = imageCache.get(assetId);
  if (hit) return hit;
  if (!src) return null;
  if (!pending.has(assetId)) {
    const p = loadImage(src).then((img) => {
      imageCache.set(assetId, img);
      pending.delete(assetId);
      return img;
    });
    pending.set(assetId, p);
  }
  if (onReady) void pending.get(assetId)!.then(onReady).catch(() => undefined);
  return null;
}

/* ---------- processing ---------- */

export function adjustmentsToFilter(a: ImageAdjustments): string {
  const parts: string[] = [];
  const brightness = 1 + a.brightness + a.exposure * 0.6;
  if (brightness !== 1) parts.push(`brightness(${brightness.toFixed(3)})`);
  if (a.contrast !== 0) parts.push(`contrast(${(1 + a.contrast).toFixed(3)})`);
  if (a.saturation !== 0) parts.push(`saturate(${(1 + a.saturation).toFixed(3)})`);
  if (a.hue !== 0) parts.push(`hue-rotate(${a.hue}deg)`);
  if (a.grayscale > 0) parts.push(`grayscale(${a.grayscale.toFixed(3)})`);
  if (a.sepia > 0) parts.push(`sepia(${a.sepia.toFixed(3)})`);
  if (a.blur > 0) parts.push(`blur(${a.blur}px)`);
  return parts.length ? parts.join(' ') : 'none';
}

function roundedRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

/** Draws the mask alpha into ctx (white = keep). Feather is a fraction of the mask's smaller dimension. */
function drawMask(ctx: CanvasRenderingContext2D, mask: ImageMask, w: number, h: number) {
  const mx = mask.x * w, my = mask.y * h, mw = Math.max(1, mask.w * w), mh = Math.max(1, mask.h * h);
  const minDim = Math.min(mw, mh);
  const featherPx = mask.feather * minDim * 0.5;
  ctx.save();
  ctx.fillStyle = '#fff';
  if (mask.type === 'linear') {
    const rad = ((mask.angle - 90) * Math.PI) / 180;
    const dx = Math.cos(rad), dy = Math.sin(rad);
    const half = (Math.abs(mw * dx) + Math.abs(mh * dy)) / 2;
    const cx = mx + mw / 2, cy = my + mh / 2;
    const g = ctx.createLinearGradient(cx - dx * half, cy - dy * half, cx + dx * half, cy + dy * half);
    const f = Math.max(0.001, mask.feather);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(Math.max(0, 1 - f), 'rgba(255,255,255,1)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(mx, my, mw, mh);
    ctx.restore();
    return;
  }
  if ((mask.type === 'circle' || mask.type === 'ellipse') && featherPx > 0) {
    // Analytic radial falloff for perfectly smooth feather.
    const cx = mx + mw / 2, cy = my + mh / 2;
    const rx = mw / 2, ry = mh / 2;
    ctx.translate(cx, cy);
    ctx.scale(rx / Math.max(rx, ry), ry / Math.max(rx, ry));
    const R = Math.max(rx, ry);
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, R);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(Math.max(0, 1 - mask.feather), 'rgba(255,255,255,1)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(0, 0, R, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    return;
  }
  // Rect / rounded rect / hard circle: blur the shape for feathering.
  if (featherPx > 0 && 'filter' in ctx) ctx.filter = `blur(${featherPx.toFixed(1)}px)`;
  const inset = featherPx;
  const ix = mx + inset, iy = my + inset, iw = Math.max(1, mw - inset * 2), ih = Math.max(1, mh - inset * 2);
  if (mask.type === 'circle' || mask.type === 'ellipse') {
    ctx.beginPath();
    ctx.ellipse(ix + iw / 2, iy + ih / 2, iw / 2, ih / 2, 0, 0, Math.PI * 2);
    ctx.fill();
  } else if (mask.type === 'roundedRect') {
    roundedRectPath(ctx, ix, iy, iw, ih, mask.cornerRadius * Math.min(iw, ih) * 0.5);
    ctx.fill();
  } else {
    ctx.fillRect(ix, iy, iw, ih);
  }
  ctx.restore();
}

export interface ProcessedImage {
  canvas: HTMLCanvasElement;
  key: string;
}

export function processKey(el: ImageElement, w: number, h: number): string {
  return JSON.stringify([el.assetId, el.crop, el.adjustments, el.mask, Math.round(w), Math.round(h)]);
}

/** Produces a processed offscreen canvas (cropped, filtered, masked) at the given pixel size. */
export function processImage(img: HTMLImageElement, el: ImageElement, w: number, h: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(w));
  canvas.height = Math.max(1, Math.round(h));
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;
  const nw = img.naturalWidth, nh = img.naturalHeight;
  const sx = el.crop.x * nw, sy = el.crop.y * nh, sw = Math.max(1, el.crop.w * nw), sh = Math.max(1, el.crop.h * nh);
  ctx.save();
  const filter = adjustmentsToFilter(el.adjustments);
  if ('filter' in ctx) ctx.filter = filter;
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  ctx.restore();
  if (el.mask.type !== 'none') {
    const maskCanvas = document.createElement('canvas');
    maskCanvas.width = canvas.width;
    maskCanvas.height = canvas.height;
    const mctx = maskCanvas.getContext('2d');
    if (mctx) {
      drawMask(mctx, el.mask, canvas.width, canvas.height);
      ctx.save();
      ctx.globalCompositeOperation = el.mask.invert ? 'destination-out' : 'destination-in';
      ctx.drawImage(maskCanvas, 0, 0);
      ctx.restore();
    }
  }
  return canvas;
}
