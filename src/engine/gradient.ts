import type { Fill, GradientFill, GradientStop } from '@/types/elements';
import { withAlpha } from './color';

export function makeGradient(partial: Partial<GradientFill> = {}): GradientFill {
  return {
    type: 'linear',
    angle: 90,
    cx: 0.5,
    cy: 0.5,
    radius: 0.7,
    stops: [
      { offset: 0, color: '#d9a441', opacity: 1 },
      { offset: 1, color: '#050608', opacity: 1 },
    ],
    ...partial,
  };
}

export function sortedStops(stops: GradientStop[]): GradientStop[] {
  return [...stops].sort((a, b) => a.offset - b.offset);
}

/** Points for a CSS-like angle (0deg = to top, 90deg = to right) within a w×h box. */
export function linearPoints(angle: number, w: number, h: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  const dx = Math.cos(rad), dy = Math.sin(rad);
  const half = (Math.abs(w * dx) + Math.abs(h * dy)) / 2;
  const cx = w / 2, cy = h / 2;
  return { x1: cx - dx * half, y1: cy - dy * half, x2: cx + dx * half, y2: cy + dy * half };
}

export function createCanvasGradient(ctx: CanvasRenderingContext2D, g: GradientFill, w: number, h: number): CanvasGradient {
  let grad: CanvasGradient;
  if (g.type === 'radial') {
    const r = Math.max(w, h) * g.radius;
    grad = ctx.createRadialGradient(g.cx * w, g.cy * h, 0, g.cx * w, g.cy * h, Math.max(1, r));
  } else if (g.type === 'conic' && 'createConicGradient' in ctx) {
    grad = (ctx as CanvasRenderingContext2D & { createConicGradient: (a: number, x: number, y: number) => CanvasGradient })
      .createConicGradient(((g.angle - 90) * Math.PI) / 180, g.cx * w, g.cy * h);
  } else {
    const p = linearPoints(g.angle, w, h);
    grad = ctx.createLinearGradient(p.x1, p.y1, p.x2, p.y2);
  }
  for (const s of sortedStops(g.stops)) grad.addColorStop(Math.min(1, Math.max(0, s.offset)), withAlpha(s.color, s.opacity));
  return grad;
}

/** CSS gradient string for UI previews. */
export function gradientToCss(g: GradientFill): string {
  const stops = sortedStops(g.stops).map((s) => `${withAlpha(s.color, s.opacity)} ${Math.round(s.offset * 100)}%`).join(', ');
  if (g.type === 'radial') return `radial-gradient(circle at ${g.cx * 100}% ${g.cy * 100}%, ${stops})`;
  if (g.type === 'conic') return `conic-gradient(from ${g.angle}deg at ${g.cx * 100}% ${g.cy * 100}%, ${stops})`;
  return `linear-gradient(${g.angle}deg, ${stops})`;
}

export function fillToCss(fill: Fill | null): string {
  if (!fill) return 'transparent';
  return fill.kind === 'solid' ? fill.color : gradientToCss(fill.gradient);
}

/** Konva fill props for Text/Shapes (conic falls back to linear). */
export function konvaFillProps(fill: Fill | null, w: number, h: number): Record<string, unknown> {
  if (!fill) return { fill: undefined };
  if (fill.kind === 'solid') return { fill: fill.color, fillPriority: 'color' };
  const g = fill.gradient;
  const colorStops = sortedStops(g.stops).flatMap((s) => [s.offset, withAlpha(s.color, s.opacity)]);
  if (g.type === 'radial') {
    const r = Math.max(w, h) * g.radius;
    return {
      fillPriority: 'radial-gradient',
      fillRadialGradientStartPoint: { x: g.cx * w, y: g.cy * h },
      fillRadialGradientEndPoint: { x: g.cx * w, y: g.cy * h },
      fillRadialGradientStartRadius: 0,
      fillRadialGradientEndRadius: Math.max(1, r),
      fillRadialGradientColorStops: colorStops,
    };
  }
  const p = linearPoints(g.angle, w, h);
  return {
    fillPriority: 'linear-gradient',
    fillLinearGradientStartPoint: { x: p.x1, y: p.y1 },
    fillLinearGradientEndPoint: { x: p.x2, y: p.y2 },
    fillLinearGradientColorStops: colorStops,
  };
}
