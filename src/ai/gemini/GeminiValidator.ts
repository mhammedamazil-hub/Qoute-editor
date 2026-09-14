import type { AnyElement, BackgroundFill, BlendMode, GlowEffect, GradientFill, ShadowEffect, ShapeElement, ShapeKind } from '@/types/elements';
import { BLEND_MODES } from '@/types/elements';
import type { SceneDocument } from '@/types/project';
import { isAllowedFont, nearestWeight } from '@/engine/fonts';
import { normalizeHex } from '@/engine/color';
import { createGradientLayer, createLight, createParticles, createQuoteMark, createShape, createText, DECORATIONS, QUOTE_MARK_GLYPHS } from '@/engine/elements/factory';
import { AI_DECORATION_KINDS, AI_ELEMENT_TYPES, AI_SHAPE_KINDS } from './GeminiSchemas';

type Rec = Record<string, unknown>;

const num = (v: unknown, fallback: number, min = -Infinity, max = Infinity): number => {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? parseFloat(v) : NaN;
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
};
const str = (v: unknown, fallback: string): string => (typeof v === 'string' ? v : fallback);
const bool = (v: unknown, fallback: boolean): boolean => (typeof v === 'boolean' ? v : fallback);
const hex = (v: unknown, fallback: string): string => normalizeHex(typeof v === 'string' ? v : '', fallback);
const isRec = (v: unknown): v is Rec => !!v && typeof v === 'object' && !Array.isArray(v);

function blend(v: unknown, fallback: BlendMode): BlendMode {
  return typeof v === 'string' && (BLEND_MODES as string[]).includes(v) ? (v as BlendMode) : fallback;
}

function gradient(v: unknown, fallback: GradientFill): GradientFill {
  if (!isRec(v)) return fallback;
  const type = v.type === 'radial' || v.type === 'conic' ? v.type : 'linear';
  const rawStops = Array.isArray(v.stops) ? v.stops.filter(isRec) : [];
  const stops = rawStops.map((s, i) => ({ offset: num(s.offset, i / Math.max(1, rawStops.length - 1), 0, 1), color: hex(s.color, '#ffffff'), opacity: num(s.opacity, 1, 0, 1) }));
  return {
    type,
    angle: num(v.angle, 90, -360, 720),
    cx: num(v.cx, 0.5, -1, 2),
    cy: num(v.cy, 0.5, -1, 2),
    radius: num(v.radius, 0.7, 0.05, 2),
    stops: stops.length >= 2 ? stops : fallback.stops,
  };
}

function glow(v: unknown, base: GlowEffect): GlowEffect {
  if (!isRec(v)) return base;
  return { enabled: true, color: hex(v.color, base.color), radius: num(v.radius, base.radius, 0, 200), intensity: num(v.intensity, base.intensity, 0, 1) };
}

function shadow(v: unknown, base: ShadowEffect): ShadowEffect {
  if (!isRec(v)) return base;
  return { enabled: true, x: num(v.x, base.x, -500, 500), y: num(v.y, base.y, -500, 500), blur: num(v.blur, base.blur, 0, 200), color: hex(v.color, base.color), opacity: num(v.opacity, base.opacity, 0, 1) };
}

/** Common, whitelisted base properties. */
function applyBase<T extends AnyElement>(el: T, r: Rec, cw: number, ch: number): T {
  const out: AnyElement = { ...el };
  if (typeof r.id === 'string' && /^[\w-]{1,64}$/.test(r.id)) out.id = r.id;
  if (typeof r.name === 'string') out.name = r.name.slice(0, 60);
  out.opacity = num(r.opacity, el.opacity, 0, 1);
  out.rotation = num(r.rotation, el.rotation, -360, 360);
  out.blendMode = blend(r.blendMode, el.blendMode);
  out.blur = num(r.blur, el.blur, 0, 100);
  out.glow = glow(r.glow, el.glow);
  out.shadow = shadow(r.shadow, el.shadow);
  // keep elements within a sane range around the canvas
  out.x = num(out.x, 0, -cw * 1.5, cw * 1.5);
  out.y = num(out.y, 0, -ch * 1.5, ch * 1.5);
  out.width = num(out.width, 100, 1, cw * 4);
  out.height = num(out.height, 100, 1, ch * 4);
  return out as T;
}

export interface ValidationResult {
  doc: SceneDocument;
  warnings: string[];
}

/**
 * Converts an untrusted AI JSON payload into a validated SceneDocument.
 * Unknown element types are dropped, values are clamped, fonts/blend modes whitelisted.
 * `existing` lets image elements be preserved during modifications.
 */
export function validateDesignSpec(input: unknown, existing: SceneDocument | null, fallbackSize: { width: number; height: number }): ValidationResult {
  const warnings: string[] = [];
  if (!isRec(input)) throw new Error('AI response was not a JSON object.');
  const canvasRec = isRec(input.canvas) ? input.canvas : {};
  const cw = Math.round(num(canvasRec.width, fallbackSize.width, 64, 8000));
  const ch = Math.round(num(canvasRec.height, fallbackSize.height, 64, 8000));

  let background: BackgroundFill = existing?.canvas.background ?? { kind: 'solid', color: '#050608' };
  if (isRec(input.background)) {
    const b = input.background;
    if (b.type === 'gradient') background = { kind: 'gradient', gradient: gradient(b.gradient, { type: 'linear', angle: 180, cx: 0.5, cy: 0.5, radius: 0.7, stops: [{ offset: 0, color: '#111', opacity: 1 }, { offset: 1, color: '#000', opacity: 1 }] }) };
    else if (b.type === 'solid' || typeof b.color === 'string') background = { kind: 'solid', color: hex(b.color, '#050608') };
  }

  const rawElements = Array.isArray(input.elements) ? input.elements.filter(isRec) : [];
  const elements: AnyElement[] = [];
  const existingById = new Map((existing?.elements ?? []).map((e) => [e.id, e]));

  for (const r of rawElements) {
    const type = str(r.type, '');
    if (!(AI_ELEMENT_TYPES as readonly string[]).includes(type)) {
      warnings.push(`Skipped unknown element type "${type}".`);
      continue;
    }
    switch (type) {
      case 'background': {
        if (typeof r.color === 'string') background = { kind: 'solid', color: hex(r.color, '#050608') };
        else if (r.gradient) background = { kind: 'gradient', gradient: gradient(r.gradient, { type: 'linear', angle: 180, cx: 0.5, cy: 0.5, radius: 0.7, stops: [{ offset: 0, color: '#111', opacity: 1 }, { offset: 1, color: '#000', opacity: 1 }] }) };
        break;
      }
      case 'light': {
        const radius = num(r.radius, 350, 20, 3000);
        const cx = num(r.x, cw * 0.8), cy = num(r.y, ch * 0.15);
        const el = createLight(hex(r.color, '#d89b35'), {
          x: cx - radius, y: cy - radius, width: radius * 2, height: radius * 2,
          intensity: num(r.intensity, 0.55, 0, 1), softness: num(r.softness, 0.8, 0, 1), blendMode: 'screen',
        });
        elements.push(applyBase(el, r, cw, ch));
        break;
      }
      case 'gradient': {
        const el = createGradientLayer(undefined, { x: num(r.x, 0), y: num(r.y, 0), width: num(r.width, cw, 1), height: num(r.height, ch, 1) });
        el.gradient = gradient(r.gradient, el.gradient);
        elements.push(applyBase(el, r, cw, ch));
        break;
      }
      case 'text': {
        const family = str(r.fontFamily, 'Playfair Display');
        const fontFamily = isAllowedFont(family) ? family : 'Playfair Display';
        if (!isAllowedFont(family)) warnings.push(`Font "${family}" replaced with Playfair Display.`);
        const el = createText({
          name: str(r.name, 'Text'),
          content: str(r.content, 'Your quote goes here').slice(0, 1000),
          fontFamily,
          fontSize: num(r.fontSize, 60, 6, 600),
          fontWeight: nearestWeight(fontFamily, num(r.fontWeight, 500, 100, 900)),
          italic: bool(r.italic, false),
          letterSpacing: num(r.letterSpacing, 0, -20, 80),
          lineHeight: num(r.lineHeight, 1.25, 0.6, 3),
          align: r.align === 'center' || r.align === 'right' ? r.align : 'left',
          fill: { kind: 'solid', color: hex(r.color, '#f5f1e7') },
          x: num(r.x, cw * 0.12), y: num(r.y, ch * 0.35), width: num(r.width, cw * 0.72, 20, cw * 2), height: num(r.height, 100, 1),
        });
        elements.push(applyBase(el, r, cw, ch));
        break;
      }
      case 'quoteMark': {
        const glyph = str(r.glyph, '\u201C');
        const family = str(r.fontFamily, 'Playfair Display');
        const fontSize = num(r.fontSize, 200, 20, 800);
        const el = createQuoteMark({
          content: QUOTE_MARK_GLYPHS.includes(glyph) ? glyph : '\u201C',
          fontFamily: isAllowedFont(family) ? family : 'Playfair Display',
          fontSize,
          fill: { kind: 'solid', color: hex(r.color, '#d9a441') },
          x: num(r.x, cw * 0.1), y: num(r.y, ch * 0.25), width: fontSize * 0.8, height: fontSize * 0.8,
        });
        elements.push(applyBase(el, r, cw, ch));
        break;
      }
      case 'shape': {
        const kind = str(r.shape, 'rect');
        if (!(AI_SHAPE_KINDS as readonly string[]).includes(kind)) {
          warnings.push(`Skipped unknown shape "${kind}".`);
          break;
        }
        const fillPatch: Partial<ShapeElement> = r.fill === null ? { fill: null } : typeof r.fill === 'string' ? { fill: { kind: 'solid', color: hex(r.fill, '#d9a441') } } : {};
        const el = createShape(kind as ShapeKind, {
          x: num(r.x, 0), y: num(r.y, 0), width: num(r.width, 200, 1), height: num(r.height, 200, 1),
          ...fillPatch,
          stroke: hex(r.stroke, '#d9a441'),
          strokeWidth: num(r.strokeWidth, typeof r.stroke === 'string' ? 1 : 0, 0, 80),
          cornerRadius: num(r.cornerRadius, 24, 0, 1000),
          sides: Math.round(num(r.sides, 6, 3, 16)),
          innerRatio: num(r.innerRatio, kind === 'star' ? 0.5 : 0.9, 0.05, 0.995),
          arcAngle: num(r.arcAngle, 240, 10, 360),
          spacing: num(r.spacing, 60, 4, 400),
        });
        elements.push(applyBase(el, r, cw, ch));
        break;
      }
      case 'line': {
        const w = num(r.width, 400, 1), h = num(r.height, 2, 1);
        const vertical = h > w;
        const sw = num(r.strokeWidth, vertical ? w : h, 0.5, 40);
        const el = createShape('line', {
          name: str(r.name, vertical ? 'Vertical Line' : 'Line'),
          x: num(r.x, 0), y: num(r.y, 0),
          width: vertical ? Math.max(1, sw) : w,
          height: vertical ? h : Math.max(1, sw),
          stroke: hex(r.color ?? r.stroke, '#d9a441'),
          strokeWidth: sw,
        });
        elements.push(applyBase(el, r, cw, ch));
        break;
      }
      case 'particle': {
        const el = createParticles({ x: 0, y: 0, width: cw, height: ch, count: Math.round(num(r.count, 50, 1, 600)), color: hex(r.color, '#f0c96a'), minSize: num(r.minSize, 1, 0.5, 20), maxSize: num(r.maxSize, 4, 0.5, 40), opacity: 0.5 });
        elements.push(applyBase(el, r, cw, ch));
        break;
      }
      case 'decoration': {
        const kind = str(r.kind, '');
        const def = DECORATIONS.find((d) => d.id === kind);
        if (!def || !(AI_DECORATION_KINDS as readonly string[]).includes(kind)) {
          warnings.push(`Skipped unknown decoration "${kind}".`);
          break;
        }
        const el = def.create(cw, ch);
        if (typeof r.x === 'number') el.x = r.x;
        if (typeof r.y === 'number') el.y = r.y;
        if (typeof r.width === 'number') el.width = r.width;
        if (typeof r.height === 'number') el.height = r.height;
        if (typeof r.color === 'string') {
          const c = hex(r.color, '#d9a441');
          if (el.type === 'shape') { el.stroke = c; if (el.fill) el.fill = { kind: 'solid', color: c }; }
          else if (el.type === 'quoteMark' || el.type === 'text') el.fill = { kind: 'solid', color: c };
          else if (el.type === 'particles') el.color = c;
        }
        elements.push(applyBase(el, r, cw, ch));
        break;
      }
      case 'image': {
        const prev = typeof r.id === 'string' ? existingById.get(r.id) : undefined;
        if (!prev || prev.type !== 'image') {
          warnings.push('Skipped image element that does not reference an existing image.');
          break;
        }
        const el = { ...prev, x: num(r.x, prev.x), y: num(r.y, prev.y), width: num(r.width, prev.width, 1), height: num(r.height, prev.height, 1) };
        elements.push(applyBase(el, { ...r, id: prev.id }, cw, ch));
        break;
      }
      case 'group':
        warnings.push('Group elements from AI are flattened.');
        break;
    }
  }

  // Ensure unique ids (AI may repeat them).
  const seen = new Set<string>();
  for (const el of elements) {
    if (seen.has(el.id)) el.id = `${el.id}-${Math.random().toString(36).slice(2, 6)}`;
    seen.add(el.id);
    el.parentId = null;
  }

  if (!elements.length) throw new Error('AI returned a design without any elements.');
  if (existing && existing.elements.some((e) => e.type === 'text') && !elements.some((e) => e.type === 'text')) {
    throw new Error('AI removed all text from the design — rejected to protect your content.');
  }

  return { doc: { canvas: { width: cw, height: ch, background }, elements }, warnings };
}
