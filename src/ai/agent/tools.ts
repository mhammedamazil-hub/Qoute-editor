/**
 * QuoteCraft AI tool layer — "the AI can control everything".
 *
 * Every capability of the editor is exposed as a Gemini function declaration and
 * executed against the real stores, so the assistant manipulates the *actual*
 * layers (never flattened images) and every action stays undoable.
 */

import type { GeminiFunctionDeclaration } from '@/ai/gemini/GeminiClient';
import { GeminiClient } from '@/ai/gemini/GeminiClient';
import { GeminiDesignService } from '@/ai/gemini/GeminiDesignService';
import { AI_DECORATION_KINDS } from '@/ai/gemini/GeminiSchemas';
import { BACKGROUND_ID, useEditorStore } from '@/store/editorStore';
import { useProjectStore } from '@/store/projectStore';
import { useSettingsStore } from '@/store/settingsStore';
import { useUIStore } from '@/store/uiStore';
import type { AnyElement, BlendMode, GradientType, ShapeKind, TextAlign, TextElement } from '@/types/elements';
import { BLEND_MODES } from '@/types/elements';
import { CANVAS_PRESETS } from '@/types/project';
import { PALETTES, findPalette, paletteLightsFor } from '@/engine/palettes';
import {
  DECORATIONS,
  QUOTE_MARK_GLYPHS,
  createGradientLayer,
  createLight,
  createParticles,
  createQuoteMark,
  createShape,
  createText,
} from '@/engine/elements/factory';
import { FONT_FAMILIES, isAllowedFont, nearestWeight } from '@/engine/fonts';
import { downloadBlob, renderExport, type ExportFormat } from '@/engine/export/exportImage';
import { TEMPLATES } from '@/components/templates/templates';

/* ------------------------------------------------------------------ *
 * arg helpers
 * ------------------------------------------------------------------ */

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

function num(v: unknown, fallback: number, min = -Infinity, max = Infinity): number {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? parseFloat(v) : NaN;
  return Number.isFinite(n) ? clamp(n, min, max) : fallback;
}

function str(v: unknown, fallback = ''): string {
  return typeof v === 'string' ? v : fallback;
}

function bool(v: unknown, fallback = false): boolean {
  return typeof v === 'boolean' ? v : fallback;
}

function hex(v: unknown, fallback: string): string {
  if (typeof v !== 'string') return fallback;
  const s = v.trim();
  return /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(s) ? s : fallback;
}

function fontFamily(v: unknown, fallback = 'Playfair Display'): string {
  const f = str(v, fallback);
  return isAllowedFont(f) ? f : fallback;
}

function shapeKind(v: unknown): ShapeKind | null {
  const s = str(v, '');
  const allowed = ['rect', 'roundedRect', 'circle', 'ellipse', 'triangle', 'polygon', 'star', 'line', 'arrow', 'ring', 'arc', 'cornerFrame', 'grid', 'dots', 'crosshair', 'plus'];
  return allowed.includes(s) ? (s as ShapeKind) : null;
}

function blend(v: unknown): BlendMode | undefined {
  const s = str(v, '');
  return (BLEND_MODES as string[]).includes(s) ? (s as BlendMode) : undefined;
}

function align(v: unknown): TextAlign | undefined {
  const s = str(v, '');
  return s === 'left' || s === 'center' || s === 'right' ? s : undefined;
}

/* ------------------------------------------------------------------ *
 * element targeting
 * ------------------------------------------------------------------ */

interface MatchArgs {
  ids?: unknown;
  types?: unknown;
  nameContains?: unknown;
  textContains?: unknown;
  selection?: unknown;
  all?: unknown;
}

function matchElements(args: MatchArgs): AnyElement[] {
  const state = useEditorStore.getState();
  const ids = Array.isArray(args.ids) ? args.ids.map(String) : [];
  if (ids.length) {
    return state.doc.elements.filter((e) => ids.includes(e.id));
  }
  if (args.all === true) return state.doc.elements;
  let out = state.doc.elements;
  if (Array.isArray(args.types) && args.types.length) {
    const types = args.types.map(String);
    out = out.filter((e) => types.includes(e.type));
  }
  const nameContains = str(args.nameContains, '').toLowerCase();
  if (nameContains) out = out.filter((e) => e.name.toLowerCase().includes(nameContains));
  const textContains = str(args.textContains, '').toLowerCase();
  if (textContains) out = out.filter((e) => (e.type === 'text' || e.type === 'quoteMark' ? e.content.toLowerCase().includes(textContains) : false));
  if (args.selection === true) out = out.filter((e) => state.selectedIds.includes(e.id));
  return out;
}

/** Whitelisted element patch so the model can't corrupt layer data. */
function buildElementPatch(patch: Record<string, unknown>): Partial<AnyElement> {
  const out: Record<string, unknown> = {};
  const numbers = ['x', 'y', 'width', 'height', 'rotation', 'opacity', 'blur', 'letterSpacing', 'lineHeight', 'fontSize', 'fontWeight', 'strokeWidth', 'cornerRadius', 'sides', 'innerRatio', 'arcAngle', 'spacing', 'count', 'minSize', 'maxSize', 'scaleX', 'scaleY', 'intensity', 'softness'];
  for (const key of numbers) {
    if (patch[key] !== undefined) out[key] = num(patch[key], 0);
  }
  const strings = ['name', 'content', 'stroke'];
  for (const key of strings) {
    if (typeof patch[key] === 'string') out[key] = patch[key];
  }
  if (typeof patch.fontFamily === 'string') out.fontFamily = fontFamily(patch.fontFamily);
  if (patch.align !== undefined) out.align = align(patch.align) ?? 'left';
  if (patch.blendMode !== undefined) out.blendMode = blend(patch.blendMode) ?? 'normal';
  if (typeof patch.color === 'string') out.fill = { kind: 'solid', color: hex(patch.color, '#f5f1e7') };
  if (typeof patch.fill === 'string') out.fill = { kind: 'solid', color: hex(patch.fill, '#d9a441') };
  if (patch.fill === null) out.fill = null;
  if (patch.visible !== undefined) out.visible = bool(patch.visible, true);
  if (patch.locked !== undefined) out.locked = bool(patch.locked, false);
  if (patch.italic !== undefined) out.italic = bool(patch.italic);
  if (patch.underline !== undefined) out.underline = bool(patch.underline);
  if (patch.dashed !== undefined) out.dashed = bool(patch.dashed);
  if (patch.glow && typeof patch.glow === 'object') {
    const g = patch.glow as Record<string, unknown>;
    out.glow = {
      enabled: g.enabled === undefined ? true : bool(g.enabled, true),
      color: hex(g.color, '#d9a441'),
      radius: num(g.radius, 24, 0, 200),
      intensity: num(g.intensity, 0.8, 0, 1),
    };
  }
  if (patch.shadow && typeof patch.shadow === 'object') {
    const s = patch.shadow as Record<string, unknown>;
    out.shadow = {
      enabled: s.enabled === undefined ? true : bool(s.enabled, true),
      x: num(s.x, 0, -200, 200),
      y: num(s.y, 12, -200, 200),
      blur: num(s.blur, 30, 0, 200),
      color: hex(s.color, '#000000'),
      opacity: num(s.opacity, 0.6, 0, 1),
    };
  }
  return out as Partial<AnyElement>;
}

function gradientArgs(raw: unknown) {
  if (!raw || typeof raw !== 'object') return undefined;
  const g = raw as Record<string, unknown>;
  const stops = Array.isArray(g.stops)
    ? (g.stops as Record<string, unknown>[])
        .slice(0, 6)
        .map((s) => ({ offset: num(s.offset, 0, 0, 1), color: hex(s.color, '#d9a441'), opacity: num(s.opacity, 1, 0, 1) }))
    : undefined;
  const type = str(g.type, 'linear');
  return {
    type: (type === 'radial' || type === 'conic' ? type : 'linear') as GradientType,
    angle: num(g.angle, 180, -360, 360),
    cx: num(g.cx, 0.5, 0, 1),
    cy: num(g.cy, 0.5, 0, 1),
    radius: num(g.radius, 1, 0.05, 2),
    stops: stops && stops.length >= 2 ? stops : undefined,
  };
}

/* ------------------------------------------------------------------ *
 * tool results
 * ------------------------------------------------------------------ */

export interface ToolOutcome {
  ok: boolean;
  summary: string;
  data?: Record<string, unknown>;
}

export interface ToolContext {
  apiKey: string;
  model: string;
  signal?: AbortSignal;
  onStatus?: (status: string) => void;
}

const ok = (summary: string, data?: Record<string, unknown>): ToolOutcome => ({ ok: true, summary, data });
const fail = (summary: string): ToolOutcome => ({ ok: false, summary });

function commitKey() {
  return `ai:${Date.now().toString(36)}`;
}

/* ------------------------------------------------------------------ *
 * app state snapshot — the model's eyes
 * ------------------------------------------------------------------ */

export function designSnapshot(verbose = false): Record<string, unknown> {
  const s = useEditorStore.getState();
  const settings = useSettingsStore.getState();
  const elements = s.doc.elements.map((e) => ({
    id: e.id,
    type: e.type,
    name: e.name,
    x: Math.round(e.x),
    y: Math.round(e.y),
    w: Math.round(e.width),
    h: Math.round(e.height),
    ...(e.type === 'text' || e.type === 'quoteMark'
      ? {
          text: verbose ? e.content : e.content.slice(0, 70),
          font: e.fontFamily,
          size: e.fontSize,
          weight: e.fontWeight,
          align: e.align,
          color: e.fill.kind === 'solid' ? e.fill.color : e.fill.gradient.stops[0]?.color,
        }
      : {}),
    ...(e.type === 'shape' ? { shape: e.shape, stroke: e.stroke, fill: e.fill?.kind === 'solid' ? e.fill.color : null } : {}),
    ...(e.type === 'light' ? { color: e.color, intensity: e.intensity } : {}),
    ...(e.parentId ? { group: e.parentId } : {}),
    ...(Math.round(e.opacity * 100) !== 100 ? { opacity: Math.round(e.opacity * 100) / 100 } : {}),
  }));

  return {
    app: 'QuoteCraft',
    canvas: { width: s.doc.canvas.width, height: s.doc.canvas.height, background: s.doc.canvas.background },
    layerCount: elements.length,
    layers: elements,
    selection: s.selectedIds,
    selectedNames: s.doc.elements.filter((e) => s.selectedIds.includes(e.id)).map((e) => e.name),
    zoom: Math.round(s.zoom * 100) / 100,
    tool: s.tool,
    projectName: s.projectName,
    previewMode: s.previewMode,
    ui: {
      theme: settings.theme,
      accent: settings.accent,
      density: settings.uiDensity,
      snapping: settings.snapping,
      showGuides: settings.showGuides,
      reduceMotion: settings.reduceMotion,
    },
    available: {
      fonts: FONT_FAMILIES,
      shapes: ['rect', 'roundedRect', 'circle', 'ellipse', 'triangle', 'polygon', 'star', 'line', 'arrow', 'ring', 'arc', 'cornerFrame', 'grid', 'dots', 'crosshair', 'plus'],
      decorations: AI_DECORATION_KINDS,
      palettes: PALETTES.map((p) => ({ id: p.id, label: p.label })),
      templates: TEMPLATES.map((t) => ({ id: t.id, name: t.name, width: t.width, height: t.height })),
      canvasPresets: CANVAS_PRESETS.map((p) => ({ id: p.id, label: `${p.label} ${p.width}x${p.height}` })),
      quoteGlyphs: QUOTE_MARK_GLYPHS,
    },
  };
}

/* ------------------------------------------------------------------ *
 * executor
 * ------------------------------------------------------------------ */

export async function executeTool(name: string, args: Record<string, unknown>, ctx: ToolContext): Promise<ToolOutcome> {
  const ed = useEditorStore.getState();
  const canvas = ed.doc.canvas;
  const key = commitKey();

  switch (name) {
    /* ---------- perception ---------- */
    case 'get_app_state':
      return ok('Read the current design state.', { state: designSnapshot(bool(args.detailed)) });

    case 'list_templates':
      return ok(`${TEMPLATES.length} templates available.`, {
        templates: TEMPLATES.map((t) => ({ id: t.id, name: t.name, description: t.description, size: `${t.width}x${t.height}` })),
      });

    /* ---------- document ---------- */
    case 'new_project': {
      const preset = CANVAS_PRESETS.find((p) => p.id === str(args.preset));
      const w = preset?.width ?? num(args.width, canvas.width, 100, 8000);
      const h = preset?.height ?? num(args.height, canvas.height, 100, 8000);
      const palette = findPalette(str(args.palette));
      ed.newDocument(w, h, palette ? palette.background : { kind: 'solid', color: hex(args.background, '#050608') });
      return ok(`Started a new ${w}×${h} project.`, { width: w, height: h });
    }

    case 'set_canvas_size': {
      const preset = CANVAS_PRESETS.find((p) => p.id === str(args.preset));
      const w = preset?.width ?? num(args.width, canvas.width, 100, 8000);
      const h = preset?.height ?? canvas.height;
      const height = preset?.height ?? num(args.height, canvas.height, 100, 8000);
      ed.setCanvas({ width: w, height: preset?.height ?? height }, 'ai-canvas');
      return ok(`Canvas resized to ${w}×${h}.`, { width: w, height: h });
    }

    case 'set_background': {
      const g = gradientArgs(args.gradient);
      if (g) {
        const bg = { kind: 'gradient' as const, gradient: { type: g.type, angle: g.angle, cx: g.cx, cy: g.cy, radius: g.radius, stops: g.stops ?? [{ offset: 0, color: hex(args.color, '#d9a441'), opacity: 1 }, { offset: 1, color: '#050608', opacity: 1 }] } };
        ed.setBackground(bg, 'ai-background');
        return ok('Background set to a gradient.');
      }
      ed.setBackground({ kind: 'solid', color: hex(args.color, '#050608') }, 'ai-background');
      return ok(`Background set to ${hex(args.color, '#050608')}.`);
    }

    case 'apply_palette': {
      const palette = findPalette(str(args.palette));
      if (!palette) return fail(`Unknown palette. Use one of: ${PALETTES.map((p) => p.id).join(', ')}`);
      ed.setBackground(palette.background, 'ai-palette');
      const lights = paletteLightsFor(palette, canvas.width, canvas.height);
      const lightEls = lights.map((l, i) =>
        createLight(l.color, {
          name: `${palette.label} Light ${i + 1}`,
          x: l.x - l.radius / 2,
          y: l.y - l.radius / 2,
          width: l.radius,
          height: l.radius,
          intensity: l.intensity,
          softness: l.softness,
          blendMode: palette.light ? 'normal' : 'screen',
        }),
      );
      const shouldRestyle = args.restyleText !== false;
      const patches: { id: string; patch: Partial<AnyElement> }[] = [];
      if (shouldRestyle) {
        for (const e of ed.doc.elements) {
          if (e.type !== 'text' && e.type !== 'quoteMark') continue;
          const isAuthor = /author|attribution|signature/i.test(e.name) || e.fontSize < canvas.width * 0.03;
          patches.push({ id: e.id, patch: { fill: { kind: 'solid', color: isAuthor ? palette.author : palette.text } } });
        }
      }
      // Insert lights directly under the text layers (above the background).
      const firstTextIdx = ed.doc.elements.findIndex((e) => e.type === 'text');
      const insertAt = firstTextIdx < 0 ? ed.doc.elements.length : firstTextIdx;
      const nextElements = [...ed.doc.elements];
      nextElements.splice(insertAt, 0, ...lightEls);
      ed.replaceElements(nextElements, 'ai-palette');
      if (patches.length) ed.updateElements(patches, 'ai-palette-text');
      return ok(`Applied the “${palette.label}” palette (background, ${lightEls.length} lights${patches.length ? ', text colours' : ''}).`, { palette: palette.id, added: lightEls.length });
    }

    case 'apply_template': {
      const tpl = TEMPLATES.find((t) => t.id === str(args.id));
      if (!tpl) return fail(`Unknown template. Available: ${TEMPLATES.map((t) => t.id).join(', ')}`);
      ed.loadDocument(tpl.build(), {}, { name: tpl.name });
      useEditorStore.setState({ saveStatus: 'unsaved' });
      if (str(args.quote)) {
        const texts = useEditorStore.getState().doc.elements.filter((e) => e.type === 'text');
        const main = texts.sort((a, b) => (b.width * b.height) - (a.width * a.height))[0];
        if (main) useEditorStore.getState().updateElement(main.id, { content: str(args.quote) } as Partial<AnyElement>);
      }
      return ok(`Loaded the “${tpl.name}” template.`);
    }

    /* ---------- layer creation ---------- */
    case 'add_text': {
      const role = str(args.role, 'quote');
      const cw = canvas.width;
      const defaults: Record<string, Partial<Parameters<typeof createText>[0]>> = {
        quote: { name: 'Quote', fontFamily: 'Playfair Display', fontSize: Math.round(cw * 0.056), lineHeight: 1.24, width: Math.round(cw * 0.74), height: Math.round(cw * 0.3) },
        author: { name: 'Author', fontFamily: 'Inter', fontSize: Math.round(cw * 0.021), fontWeight: 500, letterSpacing: 4, height: 34, width: Math.round(cw * 0.6) },
        heading: { name: 'Heading', fontFamily: 'Bebas Neue', fontSize: Math.round(cw * 0.11), letterSpacing: 6, height: Math.round(cw * 0.12), width: Math.round(cw * 0.8) },
        caption: { name: 'Caption', fontFamily: 'Inter', fontSize: Math.round(cw * 0.018), height: 30, width: Math.round(cw * 0.6) },
        label: { name: 'Label', fontFamily: 'Space Grotesk', fontSize: Math.round(cw * 0.016), letterSpacing: 8, height: 28, width: Math.round(cw * 0.5) },
      };
      const d: Partial<TextElement> = defaults[role] ?? defaults.quote ?? {};
      const width = num(args.width, d.width ?? 500, 20, canvas.width * 2);
      const height = num(args.height, d.height ?? 120, 1, canvas.height * 2);
      const isAuthorLike = role === 'author' || role === 'caption' || role === 'label';
      const el = createText({
        ...d,
        content: str(args.content, role === 'quote' ? 'Your quote goes here' : 'TEXT'),
        fontFamily: fontFamily(args.fontFamily, d.fontFamily),
        fontSize: num(args.fontSize, d.fontSize ?? 60, 6, 900),
        fontWeight: nearestWeight(fontFamily(args.fontFamily, d.fontFamily), num(args.fontWeight, d.fontWeight ?? 500, 100, 900)),
        italic: bool(args.italic, false),
        letterSpacing: num(args.letterSpacing, d.letterSpacing ?? 0, -20, 120),
        lineHeight: num(args.lineHeight, d.lineHeight ?? 1.24, 0.7, 3),
        align: align(args.align) ?? d.align ?? 'left',
        fill: { kind: 'solid', color: hex(args.color, isAuthorLike ? '#d9a441' : '#f5f1e7') },
        x: num(args.x, Math.round(canvas.width * 0.13)),
        y: num(args.y, Math.round(canvas.height * 0.4)),
        width,
        height,
        opacity: num(args.opacity, 1, 0, 1),
        rotation: num(args.rotation, 0, -360, 360),
        name: str(args.name, d.name ?? 'Text'),
      } as Partial<Parameters<typeof createText>[0]>);
      ed.addElement(el);
      return ok(`Added ${el.name} “${el.content.slice(0, 40)}${el.content.length > 40 ? '…' : ''}” at (${Math.round(el.x)}, ${Math.round(el.y)}).`, { id: el.id });
    }

    case 'add_quote_mark': {
      const glyphArg = str(args.glyph, '\u201C');
      const glyph = QUOTE_MARK_GLYPHS.includes(glyphArg) ? glyphArg : '\u201C';
      const fontSize = num(args.fontSize, Math.round(canvas.width * 0.17), 20, 900);
      const el = createQuoteMark({
        content: glyph,
        fontFamily: fontFamily(args.fontFamily, 'Playfair Display'),
        fontSize,
        width: fontSize * 0.7,
        height: fontSize * 0.7,
        fill: { kind: 'solid', color: hex(args.color, '#d9a441') },
        x: num(args.x, Math.round(canvas.width * 0.11)),
        y: num(args.y, Math.round(canvas.height * 0.26)),
        opacity: num(args.opacity, 0.92, 0, 1),
        rotation: num(args.rotation, 0, -360, 360),
      });
      ed.addElement(el);
      return ok(`Added a ${fontSize}px quote mark.`, { id: el.id });
    }

    case 'add_shape': {
      const kind = shapeKind(args.shape);
      if (!kind) return fail('Unknown shape kind.');
      const el = createShape(kind, {
        x: num(args.x, Math.round(canvas.width * 0.15)),
        y: num(args.y, Math.round(canvas.height * 0.15)),
        width: num(args.width, Math.round(canvas.width * 0.5), 1, canvas.width * 2),
        height: num(args.height, kind === 'line' || kind === 'arrow' ? 2 : Math.round(canvas.width * 0.5), 1, canvas.height * 2),
        fill: args.fill === null ? null : typeof args.fill === 'string' ? { kind: 'solid', color: hex(args.fill, '#d9a441') } : undefined,
        stroke: hex(args.stroke, args.fill === null ? '#d9a441' : 'transparent'),
        strokeWidth: num(args.strokeWidth, args.fill === null ? 1.5 : 0, 0, 80),
        cornerRadius: num(args.cornerRadius, kind === 'roundedRect' ? 24 : 0, 0, 2000),
        sides: Math.round(num(args.sides, 6, 3, 24)),
        innerRatio: num(args.innerRatio, kind === 'star' ? 0.5 : 0.9, 0.05, 0.99),
        arcAngle: num(args.arcAngle, 240, 10, 360),
        spacing: num(args.spacing, 60, 4, 500),
        opacity: num(args.opacity, 1, 0, 1),
        rotation: num(args.rotation, 0, -360, 360),
        blendMode: blend(args.blendMode) ?? 'normal',
        name: str(args.name, undefined as unknown as string) || undefined,
      } as Partial<Parameters<typeof createShape>[1]>);
      ed.addElement(el);
      return ok(`Added a ${kind} at (${Math.round(el.x)}, ${Math.round(el.y)}), ${Math.round(el.width)}×${Math.round(el.height)}.`, { id: el.id });
    }

    case 'add_light': {
      const radius = num(args.radius, Math.round(canvas.width * 0.55), 80, 4000);
      const cx = num(args.x, Math.round(canvas.width * 0.5));
      const cy = num(args.y, Math.round(canvas.height * 0.2));
      const el = createLight(hex(args.color, '#d89b35'), {
        x: cx - radius / 2,
        y: cy - radius / 2,
        width: radius,
        height: radius,
        intensity: num(args.intensity, 0.55, 0, 1),
        softness: num(args.softness, 0.85, 0, 1),
        opacity: num(args.opacity, 1, 0, 1),
        blendMode: blend(args.blendMode) ?? 'screen',
        name: str(args.name, 'Atmosphere'),
      });
      // Lights belong just above the background.
      const els = [...useEditorStore.getState().doc.elements];
      const firstVisible = els.findIndex((e) => e.type === 'text' || e.type === 'shape');
      els.splice(firstVisible < 0 ? els.length : firstVisible, 0, el);
      useEditorStore.getState().replaceElements(els, 'ai-light');
      return ok(`Added a ${hex(args.color, '#d89b35')} light (radius ${radius}) centred at (${cx}, ${cy}).`, { id: el.id });
    }

    case 'add_gradient_layer': {
      const g = gradientArgs(args.gradient) ?? gradientArgs({
        stops: [
          { offset: 0, color: hex(args.color, '#d9a441'), opacity: num(args.opacity, 0.55, 0, 1) },
          { offset: 1, color: hex(args.color, '#d9a441'), opacity: 0 },
        ],
      })!;
      const el = createGradientLayer(
        { type: g.type, angle: g.angle, cx: g.cx, cy: g.cy, radius: g.radius, stops: g.stops! },
        {
          x: num(args.x, 0),
          y: num(args.y, 0),
          width: num(args.width, canvas.width),
          height: num(args.height, canvas.height),
          opacity: num(args.layerOpacity, 1, 0, 1),
          blendMode: blend(args.blendMode) ?? 'normal',
          name: str(args.name, 'Gradient'),
        },
      );
      const els = [...useEditorStore.getState().doc.elements];
      const firstVisible = els.findIndex((e) => e.type === 'text');
      els.splice(firstVisible < 0 ? els.length : firstVisible, 0, el);
      useEditorStore.getState().replaceElements(els, 'ai-gradient');
      return ok('Added a gradient layer above the background.');
    }

    case 'add_particles': {
      const el = createParticles({
        x: num(args.x, 0),
        y: num(args.y, 0),
        width: num(args.width, canvas.width),
        height: num(args.height, canvas.height),
        count: Math.round(num(args.count, 55, 1, 600)),
        color: hex(args.color, '#f0c96a'),
        minSize: num(args.minSize, 1, 0.5, 20),
        maxSize: num(args.maxSize, 4, 0.5, 40),
        opacity: num(args.opacity, 0.5, 0, 1),
      });
      ed.addElement(el);
      return ok(`Added ${el.count} particles.`, { id: el.id });
    }

    case 'add_decoration': {
      const def = DECORATIONS.find((d) => d.id === str(args.kind));
      if (!def) return fail(`Unknown decoration. Options: ${DECORATIONS.map((d) => d.id).join(', ')}`);
      const el = def.create(canvas.width, canvas.height);
      if (args.x !== undefined) el.x = num(args.x, el.x);
      if (args.y !== undefined) el.y = num(args.y, el.y);
      if (args.width !== undefined) el.width = num(args.width, el.width, 1);
      if (args.height !== undefined) el.height = num(args.height, el.height, 1);
      if (typeof args.color === 'string') {
        const c = hex(args.color, '#d9a441');
        if (el.type === 'shape') {
          el.stroke = c;
          if (el.fill) el.fill = { kind: 'solid', color: c };
        } else if (el.type === 'quoteMark') el.fill = { kind: 'solid', color: c };
        else if (el.type === 'particles') el.color = c;
      }
      el.opacity = num(args.opacity, el.opacity, 0, 1);
      el.rotation = num(args.rotation, el.rotation, -360, 360);
      ed.addElement(el);
      return ok(`Added the “${def.label}” decoration.`, { id: el.id });
    }

    /* ---------- layer editing ---------- */
    case 'update_elements': {
      const targets = matchElements(args);
      if (!targets.length) return fail('No layers matched that description.');
      const rawPatch = (args.patch ?? {}) as Record<string, unknown>;
      const patch = buildElementPatch(rawPatch);
      if (!Object.keys(patch).length) return fail('Nothing to update — the patch was empty.');
      ed.updateElements(targets.map((t) => ({ id: t.id, patch })), key);
      return ok(`Updated ${targets.length} layer${targets.length === 1 ? '' : 's'}: ${Object.keys(patch).join(', ')}.`);
    }

    case 'set_text_content': {
      const targets = matchElements(args).filter((e) => e.type === 'text' || e.type === 'quoteMark');
      if (!targets.length) return fail('No text layer matched.');
      const content = str(args.content, '');
      if (!content) return fail('The new text was empty.');
      ed.updateElements(targets.map((t) => ({ id: t.id, patch: { content } as Partial<AnyElement> })), key);
      return ok(`Set the text of ${targets.length} layer(s).`);
    }

    case 'set_typography': {
      const targets = matchElements(args).filter((e) => e.type === 'text' || e.type === 'quoteMark');
      if (!targets.length) return fail('No text layer matched.');
      const family = args.fontFamily !== undefined ? fontFamily(args.fontFamily) : undefined;
      const patch: Partial<TextElement> = {};
      if (family) {
        patch.fontFamily = family;
        if (args.fontWeight === undefined) {
          const cur = targets[0];
          if (cur.type === 'text' || cur.type === 'quoteMark') patch.fontWeight = nearestWeight(family, cur.fontWeight);
        }
      }
      if (args.fontWeight !== undefined) patch.fontWeight = nearestWeight(family ?? 'Inter', num(args.fontWeight, 500, 100, 900));
      if (args.fontSize !== undefined) patch.fontSize = num(args.fontSize, 60, 6, 900);
      if (args.letterSpacing !== undefined) patch.letterSpacing = num(args.letterSpacing, 0, -20, 120);
      if (args.lineHeight !== undefined) patch.lineHeight = num(args.lineHeight, 1.25, 0.7, 3);
      if (args.align !== undefined) patch.align = align(args.align) ?? 'left';
      if (args.italic !== undefined) patch.italic = bool(args.italic);
      if (typeof args.color === 'string') patch.fill = { kind: 'solid', color: hex(args.color, '#f5f1e7') };
      if (!Object.keys(patch).length) return fail('No typography change was provided.');
      ed.updateElements(targets.map((t) => ({ id: t.id, patch: patch as Partial<AnyElement> })), key);
      return ok(`Updated typography on ${targets.length} text layer(s).`);
    }

    case 'set_layer_style': {
      const targets = matchElements(args);
      if (!targets.length) return fail('No layers matched.');
      const patch = buildElementPatch({
        opacity: args.opacity,
        blur: args.blur,
        rotation: args.rotation,
        blendMode: args.blendMode,
        glow: args.glow,
        shadow: args.shadow,
        locked: args.locked,
        visible: args.visible,
      });
      if (!Object.keys(patch).length) return fail('No style change was provided.');
      ed.updateElements(targets.map((t) => ({ id: t.id, patch })), key);
      return ok(`Restyled ${targets.length} layer(s).`);
    }

    case 'translate_elements': {
      const targets = matchElements(args);
      if (!targets.length) return fail('No layers matched.');
      const dx = num(args.dx, 0, -10000, 10000);
      const dy = num(args.dy, 0, -10000, 10000);
      ed.updateElements(targets.map((t) => ({ id: t.id, patch: { x: t.x + dx, y: t.y + dy } })), key);
      return ok(`Moved ${targets.length} layer(s) by (${dx}, ${dy}).`);
    }

    case 'resize_elements': {
      const targets = matchElements(args);
      if (!targets.length) return fail('No layers matched.');
      const scale = args.scale !== undefined ? num(args.scale, 1, 0.05, 12) : undefined;
      const patches = targets.map((t) => {
        const patch: Partial<TextElement> = {};
        if (scale) {
          patch.width = Math.max(1, t.width * scale);
          patch.height = Math.max(1, t.height * scale);
          if (t.type === 'text' || t.type === 'quoteMark') patch.fontSize = Math.max(4, t.fontSize * scale);
        }
        if (args.width !== undefined) patch.width = num(args.width, t.width, 1, canvas.width * 3);
        if (args.height !== undefined) patch.height = num(args.height, t.height, 1, canvas.height * 3);
        return { id: t.id, patch: patch as Partial<AnyElement> };
      });
      ed.updateElements(patches, key);
      return ok(`Resized ${targets.length} layer(s).`);
    }

    case 'duplicate_elements': {
      const targets = matchElements(args);
      if (!targets.length) return fail('No layers matched.');
      ed.duplicateElements(targets.map((t) => t.id));
      return ok(`Duplicated ${targets.length} layer(s).`);
    }

    case 'delete_elements': {
      const targets = matchElements(args);
      if (!targets.length) return fail('No layers matched — nothing deleted.');
      const guardText = args.keepText !== false;
      const textTargets = targets.filter((e) => e.type === 'text');
      const remainingText = useEditorStore.getState().doc.elements.filter((e) => e.type === 'text' && !textTargets.some((t) => t.id === e.id));
      let ids = targets.map((t) => t.id);
      let guarded = false;
      if (guardText && textTargets.length && remainingText.length === 0) {
        // Never wipe out every text layer — keep the largest one.
        const keep = [...textTargets].sort((a, b) => b.width * b.height - a.width * a.height)[0];
        ids = ids.filter((id) => id !== keep.id);
        guarded = true;
      }
      ed.removeElements(ids);
      return ok(`Deleted ${ids.length} layer(s)${guarded ? ' (kept the main text layer to protect your content)' : ''}.`, { deleted: ids.length });
    }

    case 'select_elements': {
      if (args.none === true) {
        ed.clearSelection();
        return ok('Cleared the selection.');
      }
      const targets = matchElements({ ...args, all: args.all === true });
      if (!targets.length) return fail('No layers matched.');
      ed.select(targets.map((t) => t.id));
      ed.setRightTab('properties');
      return ok(`Selected ${targets.length} layer(s): ${targets.map((t) => t.name).slice(0, 6).join(', ')}.`);
    }

    case 'reorder_elements': {
      const target = matchElements(args)[0];
      if (!target) return fail('No layer matched.');
      const position = str(args.position, 'up');
      const dir = position === 'top' || position === 'bottom' || position === 'up' || position === 'down' ? position : 'up';
      ed.moveLayer(target.id, dir);
      return ok(`Moved “${target.name}” ${dir} in the layer stack.`);
    }

    case 'group_elements': {
      const targets = matchElements({ ids: args.ids, selection: args.selection }).filter((e) => !e.parentId && e.type !== 'group');
      if (targets.length < 2) return fail('Select at least two top-level layers to group.');
      ed.select(targets.map((t) => t.id));
      ed.groupSelected();
      return ok(`Grouped ${targets.length} layers.`);
    }

    case 'ungroup_elements': {
      const targets = matchElements({ ids: args.ids, types: ['group'], selection: args.selection });
      if (!targets.length) return fail('No group matched.');
      ed.select(targets.map((t) => t.id));
      ed.ungroupSelected();
      return ok('Ungrouped the selection.');
    }

    case 'align_elements': {
      const mode = str(args.mode, 'canvas');
      const allowed = ['left', 'hcenter', 'right', 'top', 'vcenter', 'bottom', 'canvas', 'dist-h', 'dist-v'];
      if (!allowed.includes(mode)) return fail(`Unknown align mode. Use one of: ${allowed.join(', ')}`);
      const targets = matchElements(args);
      if (targets.length) ed.select(targets.map((t) => t.id));
      ed.alignSelected(mode as Parameters<typeof ed.alignSelected>[0]);
      return ok(`Aligned ${ed.selectedIds.length || 1} layer(s) using “${mode}”.`);
    }

    case 'distribute_elements': {
      const targets = matchElements(args);
      if (targets.length < 3) return fail('Distributing needs at least three layers.');
      ed.select(targets.map((t) => t.id));
      ed.alignSelected(str(args.axis) === 'v' ? 'dist-v' : 'dist-h');
      return ok(`Distributed ${targets.length} layers evenly.`);
    }

    /* ---------- history ---------- */
    case 'undo':
      ed.undo();
      return ok('Undid the last change.');
    case 'redo':
      ed.redo();
      return ok('Redid the last change.');

    /* ---------- view + workspace ---------- */
    case 'zoom': {
      const level = args.level;
      if (level === undefined || level === 'fit') {
        const { fitToScreen } = await import('@/components/editor/ZoomControls');
        fitToScreen();
        return ok('Zoomed to fit.');
      }
      const { fitToScreen, zoomTo } = await import('@/components/editor/ZoomControls');
      if (level === 'in') zoomTo(useEditorStore.getState().zoom * 1.25);
      else if (level === 'out') zoomTo(useEditorStore.getState().zoom / 1.25);
      else if (level === '100%') zoomTo(1);
      else zoomTo(num(level, 1, 0.05, 8));
      void fitToScreen;
      return ok(`Zoom is now ${Math.round(useEditorStore.getState().zoom * 100)}%.`);
    }

    case 'set_preview_mode':
      ed.setPreviewMode(bool(args.enabled, true));
      return ok(bool(args.enabled, true) ? 'Entered preview mode.' : 'Back to the editor.');

    case 'open_panel': {
      const panel = str(args.panel, 'none');
      const modals = ['export', 'settings', 'templates', 'projects', 'newDesign', 'ai'];
      if (modals.includes(panel)) {
        ed.setModal(panel as Parameters<typeof ed.setModal>[0]);
        return ok(`Opened the ${panel} panel.`);
      }
      if (panel === 'layers') {
        ed.setRightTab('layers');
        ed.setMobileSheet('layers');
        return ok('Opened the layers panel.');
      }
      if (panel === 'properties') {
        ed.setRightTab('properties');
        ed.setMobileSheet('properties');
        return ok('Opened the properties panel.');
      }
      if (panel === 'none') {
        ed.setModal('none');
        return ok('Closed the open panel.');
      }
      return fail(`Unknown panel. Use one of: ${[...modals, 'layers', 'properties', 'none'].join(', ')}`);
    }

    case 'set_ui_preference': {
      const patch: Record<string, unknown> = {};
      if (args.theme !== undefined && ['dark', 'light', 'system'].includes(str(args.theme))) patch.theme = str(args.theme);
      if (typeof args.accent === 'string') patch.accent = hex(args.accent, '#d9a441');
      if (args.density !== undefined && ['compact', 'comfortable'].includes(str(args.density))) patch.uiDensity = str(args.density);
      if (args.snapping !== undefined) patch.snapping = bool(args.snapping);
      if (args.showGuides !== undefined) patch.showGuides = bool(args.showGuides);
      if (args.handleSize !== undefined) patch.handleSize = num(args.handleSize, 9, 6, 20);
      if (args.reduceMotion !== undefined) patch.reduceMotion = bool(args.reduceMotion);
      if (!Object.keys(patch).length) return fail('No interface preference was provided.');
      useSettingsStore.getState().update(patch);
      return ok(`Updated interface settings: ${Object.keys(patch).join(', ')}.`);
    }

    /* ---------- project level ---------- */
    case 'save_project': {
      await useProjectStore.getState().saveCurrent();
      return ok('Saved the project to this browser.');
    }

    case 'export_image': {
      const format = (['png', 'jpeg', 'webp'].includes(str(args.format)) ? str(args.format) : useSettingsStore.getState().defaultFormat) as ExportFormat;
      const scale = num(args.scale, 1, 0.25, 4);
      const width = Math.round(canvas.width * scale);
      const height = Math.round(canvas.height * scale);
      if (width * height > 36_000_000) {
        const fit = Math.sqrt(36_000_000 / (canvas.width * canvas.height));
        return fail(`That resolution is too large for a browser export. Try scale ${Math.floor(fit * 100) / 100}.`);
      }
      ctx.onStatus?.('Rendering export…');
      const blob = await renderExport({ width, height, format, quality: num(args.quality, useSettingsStore.getState().defaultQuality, 0.3, 1) });
      if (args.download !== false) {
        downloadBlob(blob, `${useEditorStore.getState().projectName.replace(/[^\w\-]+/g, '-').toLowerCase() || 'quotecraft'}-${width}x${height}.${format === 'jpeg' ? 'jpg' : format}`);
      }
      return ok(`Exported a ${width}×${height} ${format.toUpperCase()} (${Math.round(blob.size / 1024)} KB).`, { width, height, format, bytes: blob.size });
    }

    /* ---------- meta: the design studio ---------- */
    case 'generate_design': {
      const brief = str(args.brief, '');
      if (!brief) return fail('A brief is required to generate a design.');
      const preset = CANVAS_PRESETS.find((p) => p.id === str(args.sizePreset));
      const width = preset?.width ?? num(args.width, canvas.width, 200, 4000);
      const height = preset?.height ?? num(args.height, canvas.height, 200, 6000);
      ctx.onStatus?.('Composing a full design…');
      const client = new GeminiClient({ apiKey: ctx.apiKey, model: ctx.model, timeoutMs: 120_000 });
      const service = new GeminiDesignService(client);
      const res = await service.generate({
        brief,
        style: str(args.style, 'Cinematic'),
        mood: str(args.mood, 'Calm and confident'),
        colors: str(args.colors, ''),
        width,
        height,
        includeImage: bool(args.includeImage),
      });
      const mode = str(args.mode, 'replace');
      if (mode === 'replace') {
        ed.setCanvas({ width: res.doc.canvas.width, height: res.doc.canvas.height, background: res.doc.canvas.background }, 'ai-generate');
        ed.replaceElements(res.doc.elements, 'ai-generate');
      } else {
        ed.addElements(res.doc.elements, false);
      }
      return ok(`Generated a ${width}×${height} design with ${res.doc.elements.length} editable layers.`, {
        layers: res.doc.elements.map((e) => ({ id: e.id, type: e.type, name: e.name })),
        warnings: res.warnings,
      });
    }

    default:
      return fail(`Unknown tool “${name}”.`);
  }
}

/* ------------------------------------------------------------------ *
 * declarations handed to Gemini
 * ------------------------------------------------------------------ */

const obj = (properties: Record<string, unknown>, required?: string[]) => ({ type: 'object' as const, properties, required });

const targets = {
  ids: { type: 'array', items: { type: 'string' }, description: 'Exact layer ids (preferred when known).' },
  types: { type: 'array', items: { type: 'string' }, description: 'Match layer types: text, quoteMark, shape, light, gradient, image, particles, group.' },
  nameContains: { type: 'string', description: 'Match layers whose name contains this text (case-insensitive).' },
  textContains: { type: 'string', description: 'Match text layers whose content contains this text.' },
  selection: { type: 'boolean', description: 'Restrict to the current selection.' },
  all: { type: 'boolean', description: 'Match every layer.' },
};

const colorProp = { type: 'string', description: 'Hex colour like #d9a441.' };

export const TOOL_DECLARATIONS: GeminiFunctionDeclaration[] = [
  {
    name: 'get_app_state',
    description: 'Read the live design: canvas size, background, every layer with geometry/typography, selection, zoom and UI settings, plus the available fonts, shapes, palettes, templates and canvas presets. Call this before editing when you are unsure what is on the canvas.',
    parameters: obj({ detailed: { type: 'boolean', description: 'Include full text content for every text layer.' } }),
  },
  {
    name: 'new_project',
    description: 'Start a fresh project (clears the canvas and history).',
    parameters: obj({ preset: { type: 'string', description: 'Canvas preset id, e.g. ig-square, ig-story, poster, yt-thumb.' }, width: { type: 'number' }, height: { type: 'number' }, background: colorProp, palette: { type: 'string' } }),
  },
  {
    name: 'set_canvas_size',
    description: 'Resize the artboard without clearing layers.',
    parameters: obj({ preset: { type: 'string' }, width: { type: 'number' }, height: { type: 'number' } }),
  },
  {
    name: 'set_background',
    description: 'Set the canvas background to a solid colour or a gradient.',
    parameters: obj({
      color: colorProp,
      gradient: obj({
        type: { type: 'string', description: 'linear | radial | conic' },
        angle: { type: 'number' },
        cx: { type: 'number' },
        cy: { type: 'number' },
        radius: { type: 'number' },
        stops: { type: 'array', items: obj({ offset: { type: 'number' }, color: { type: 'string' }, opacity: { type: 'number' } }) },
      }),
    }),
  },
  {
    name: 'apply_palette',
    description: 'Apply a curated colour palette: sets the background, adds two atmospheric lights and recolours text. Fastest way to restyle a whole poster.',
    parameters: obj({ palette: { type: 'string', description: `One of: ${PALETTES.map((p) => p.id).join(', ')}` }, restyleText: { type: 'boolean', description: 'Recolour existing text to match (default true).' } }, ['palette']),
  },
  {
    name: 'list_templates',
    description: 'List the built-in poster templates.',
    parameters: obj({}),
  },
  {
    name: 'apply_template',
    description: 'Load a built-in template as the current document (replaces the canvas contents).',
    parameters: obj({ id: { type: 'string', description: `Template id: ${TEMPLATES.map((t) => t.id).join(', ')}` }, quote: { type: 'string', description: 'Optional replacement text for the main quote of the template.' } }, ['id']),
  },
  {
    name: 'add_text',
    description: 'Add a text layer. Use role "quote" for the main statement, "author" for attribution, "heading" for a large display word, "caption" or "label" for small supporting text.',
    parameters: obj(
      {
        role: { type: 'string', description: 'quote | author | heading | caption | label' },
        content: { type: 'string', description: 'The exact text to show.' },
        x: { type: 'number', description: 'Left edge in canvas pixels.' },
        y: { type: 'number', description: 'Top edge in canvas pixels.' },
        width: { type: 'number', description: 'Text box width in pixels (wrapping width).' },
        height: { type: 'number' },
        fontFamily: { type: 'string', description: `One of: ${FONT_FAMILIES.join(', ')}` },
        fontSize: { type: 'number' },
        fontWeight: { type: 'number', description: '100–900' },
        italic: { type: 'boolean' },
        letterSpacing: { type: 'number' },
        lineHeight: { type: 'number', description: '0.8–2' },
        align: { type: 'string', description: 'left | center | right' },
        color: colorProp,
        opacity: { type: 'number' },
        rotation: { type: 'number' },
        name: { type: 'string', description: 'Layer name shown in the layers panel.' },
      },
      ['content'],
    ),
  },
  {
    name: 'add_quote_mark',
    description: 'Add a large decorative quotation mark.',
    parameters: obj({ glyph: { type: 'string', description: `One of: ${QUOTE_MARK_GLYPHS.join(' ')}` }, fontSize: { type: 'number' }, color: colorProp, fontFamily: { type: 'string' }, x: { type: 'number' }, y: { type: 'number' }, opacity: { type: 'number' }, rotation: { type: 'number' } }),
  },
  {
    name: 'add_shape',
    description: 'Add a geometric shape: rect, roundedRect, circle, ellipse, triangle, polygon, star, line, arrow, ring, arc, cornerFrame, grid, dots, crosshair, plus. Use fill:null with a stroke for outline geometry.',
    parameters: obj({
      shape: { type: 'string' },
      x: { type: 'number' },
      y: { type: 'number' },
      width: { type: 'number' },
      height: { type: 'number' },
      fill: { type: 'string', description: 'Hex colour, or null for no fill.' },
      stroke: colorProp,
      strokeWidth: { type: 'number' },
      cornerRadius: { type: 'number' },
      sides: { type: 'number' },
      innerRatio: { type: 'number' },
      arcAngle: { type: 'number' },
      spacing: { type: 'number' },
      opacity: { type: 'number' },
      rotation: { type: 'number' },
      blendMode: { type: 'string' },
      name: { type: 'string' },
    }, ['shape']),
  },
  {
    name: 'add_light',
    description: 'Add a soft atmospheric light (radial glow). x,y is the light CENTRE. Lights render best with blendMode screen on dark designs.',
    parameters: obj({ x: { type: 'number' }, y: { type: 'number' }, radius: { type: 'number', description: '80–4000 px' }, color: colorProp, intensity: { type: 'number' }, softness: { type: 'number' }, opacity: { type: 'number' }, blendMode: { type: 'string' }, name: { type: 'string' } }),
  },
  {
    name: 'add_gradient_layer',
    description: 'Add a gradient layer above the background (vignettes, colour washes).',
    parameters: obj({
      gradient: obj({ type: { type: 'string' }, angle: { type: 'number' }, cx: { type: 'number' }, cy: { type: 'number' }, radius: { type: 'number' }, stops: { type: 'array', items: obj({ offset: { type: 'number' }, color: { type: 'string' }, opacity: { type: 'number' } }) } }),
      x: { type: 'number' }, y: { type: 'number' }, width: { type: 'number' }, height: { type: 'number' },
      blendMode: { type: 'string' }, layerOpacity: { type: 'number' }, name: { type: 'string' },
    }),
  },
  {
    name: 'add_particles',
    description: 'Add subtle floating dust/particles. Keep count under 80 and opacity under 0.5 for elegance.',
    parameters: obj({ count: { type: 'number' }, color: colorProp, minSize: { type: 'number' }, maxSize: { type: 'number' }, opacity: { type: 'number' }, x: { type: 'number' }, y: { type: 'number' }, width: { type: 'number' }, height: { type: 'number' } }),
  },
  {
    name: 'add_decoration',
    description: 'Add a decoration from the built-in library (thin lines, frames, rings, grids, quote marks, polygons…).',
    parameters: obj({ kind: { type: 'string', description: `One of: ${DECORATIONS.map((d) => d.id).join(', ')}` }, x: { type: 'number' }, y: { type: 'number' }, width: { type: 'number' }, height: { type: 'number' }, color: colorProp, opacity: { type: 'number' }, rotation: { type: 'number' } }, ['kind']),
  },
  {
    name: 'update_elements',
    description: 'Patch any property of one or more existing layers. Target either with ids, or with types/nameContains/textContains/selection. Patch supports x, y, width, height, rotation, opacity, blur, color, fill, stroke, strokeWidth, cornerRadius, sides, innerRatio, arcAngle, spacing, count, minSize, maxSize, intensity, softness, blendMode, glow, shadow, visible, locked.',
    parameters: obj({ ...targets, patch: obj({
      x: { type: 'number' }, y: { type: 'number' }, width: { type: 'number' }, height: { type: 'number' },
      rotation: { type: 'number' }, opacity: { type: 'number' }, blur: { type: 'number' }, color: colorProp, fill: { type: 'string' },
      stroke: colorProp, strokeWidth: { type: 'number' }, cornerRadius: { type: 'number' }, sides: { type: 'number' },
      innerRatio: { type: 'number' }, arcAngle: { type: 'number' }, spacing: { type: 'number' }, count: { type: 'number' },
      minSize: { type: 'number' }, maxSize: { type: 'number' }, intensity: { type: 'number' }, softness: { type: 'number' },
      blendMode: { type: 'string' }, visible: { type: 'boolean' }, locked: { type: 'boolean' },
      glow: obj({ enabled: { type: 'boolean' }, color: { type: 'string' }, radius: { type: 'number' }, intensity: { type: 'number' } }),
      shadow: obj({ enabled: { type: 'boolean' }, x: { type: 'number' }, y: { type: 'number' }, blur: { type: 'number' }, color: { type: 'string' }, opacity: { type: 'number' } }),
    }, ['patch']) }, ['patch']),
  },
  {
    name: 'set_text_content',
    description: 'Replace the words in one or more text layers (keeps all styling).',
    parameters: obj({ ...targets, content: { type: 'string' } }, ['content']),
  },
  {
    name: 'set_typography',
    description: 'Change font family, size, weight, spacing, line height, alignment or colour of text layers.',
    parameters: obj({ ...targets, fontFamily: { type: 'string' }, fontSize: { type: 'number' }, fontWeight: { type: 'number' }, letterSpacing: { type: 'number' }, lineHeight: { type: 'number' }, align: { type: 'string' }, italic: { type: 'boolean' }, color: colorProp }),
  },
  {
    name: 'set_layer_style',
    description: 'Set opacity, blur, rotation, blend mode, glow, shadow, visibility or lock on layers.',
    parameters: obj({ ...targets, opacity: { type: 'number' }, blur: { type: 'number' }, rotation: { type: 'number' }, blendMode: { type: 'string' }, visible: { type: 'boolean' }, locked: { type: 'boolean' }, glow: obj({ enabled: { type: 'boolean' }, color: { type: 'string' }, radius: { type: 'number' }, intensity: { type: 'number' } }), shadow: obj({ enabled: { type: 'boolean' }, x: { type: 'number' }, y: { type: 'number' }, blur: { type: 'number' }, color: { type: 'string' }, opacity: { type: 'number' } }) }),
  },
  {
    name: 'translate_elements',
    description: 'Move layers by a pixel offset.',
    parameters: obj({ ...targets, dx: { type: 'number' }, dy: { type: 'number' } }, ['dx', 'dy']),
  },
  {
    name: 'resize_elements',
    description: 'Scale layers (multiplier) or set explicit width/height. Text scales its font size too.',
    parameters: obj({ ...targets, scale: { type: 'number' }, width: { type: 'number' }, height: { type: 'number' } }),
  },
  {
    name: 'duplicate_elements',
    description: 'Duplicate layers (copies are offset by 24px).',
    parameters: obj(targets),
  },
  {
    name: 'delete_elements',
    description: 'Delete layers. Never delete the main quote text unless the user explicitly asks.',
    parameters: obj({ ...targets, keepText: { type: 'boolean', description: 'Protect the last remaining text layer (default true).' } }),
  },
  {
    name: 'select_elements',
    description: 'Change the editor selection (highlights layers for the user).',
    parameters: obj({ ...targets, none: { type: 'boolean', description: 'Set true to clear the selection.' } }),
  },
  {
    name: 'reorder_elements',
    description: 'Move a layer up/down or to the top/bottom of the stack.',
    parameters: obj({ ...targets, position: { type: 'string', description: 'top | bottom | up | down' } }, ['position']),
  },
  {
    name: 'group_elements',
    description: 'Group layers so they move together.',
    parameters: obj({ ...targets }),
  },
  {
    name: 'ungroup_elements',
    description: 'Ungroup group layers.',
    parameters: obj(targets),
  },
  {
    name: 'align_elements',
    description: 'Align layers: left, hcenter, right, top, vcenter, bottom, canvas (centre on the artboard), dist-h, dist-v.',
    parameters: obj({ ...targets, mode: { type: 'string' } }, ['mode']),
  },
  {
    name: 'distribute_elements',
    description: 'Distribute three or more layers with equal spacing.',
    parameters: obj({ ...targets, axis: { type: 'string', description: 'h or v' } }),
  },
  { name: 'undo', description: 'Undo the last change.', parameters: obj({}) },
  { name: 'redo', description: 'Redo the last undone change.', parameters: obj({}) },
  {
    name: 'zoom',
    description: 'Control the viewport zoom.',
    parameters: obj({ level: { type: 'string', description: 'fit | in | out | 100% | a number like 0.5' } }),
  },
  {
    name: 'set_preview_mode',
    description: 'Toggle distraction-free preview mode so the user sees only the artwork.',
    parameters: obj({ enabled: { type: 'boolean' } }),
  },
  {
    name: 'open_panel',
    description: 'Open or close a panel for the user: export, settings, templates, projects, newDesign, ai, layers, properties, none.',
    parameters: obj({ panel: { type: 'string' } }, ['panel']),
  },
  {
    name: 'set_ui_preference',
    description: 'Change interface preferences: theme (dark|light|system), accent colour, density (compact|comfortable), snapping, showGuides, handleSize, reduceMotion.',
    parameters: obj({ theme: { type: 'string' }, accent: colorProp, density: { type: 'string' }, snapping: { type: 'boolean' }, showGuides: { type: 'boolean' }, handleSize: { type: 'number' }, reduceMotion: { type: 'boolean' } }),
  },
  { name: 'save_project', description: 'Save the project to this browser.', parameters: obj({}) },
  {
    name: 'export_image',
    description: 'Render and download the final artwork at any resolution. Ask before exporting when the user has not mentioned it.',
    parameters: obj({ format: { type: 'string', description: 'png | jpeg | webp' }, scale: { type: 'number', description: '1 = canvas size, 2 = double, …' }, quality: { type: 'number', description: '0.3–1 for jpeg/webp' }, download: { type: 'boolean', description: 'Set false to only render (no file).' } }),
  },
  {
    name: 'generate_design',
    description: 'Run the full design engine: write a complete multi-layer poster from a brief (quote, author, lighting, geometry, typography) and place it on the canvas as editable layers. Use this when the user asks for a new design from scratch.',
    parameters: obj({
      brief: { type: 'string', description: 'What the poster should say and feel like; include the quote text if the user gave one.' },
      style: { type: 'string' },
      mood: { type: 'string' },
      colors: { type: 'string' },
      sizePreset: { type: 'string' },
      width: { type: 'number' },
      height: { type: 'number' },
      includeImage: { type: 'boolean', description: 'Reserve a natural area for a photo.' },
      mode: { type: 'string', description: 'replace (default) or add to the existing canvas.' },
    }, ['brief']),
  },
];

/** Small, fast tool set used when the model needs a quick, cheap turn. */
export const LIGHT_TOOL_NAMES = new Set(['get_app_state', 'update_elements', 'set_text_content', 'add_text', 'translate_elements', 'set_layer_style', 'set_typography', 'undo', 'redo', 'select_elements', 'zoom', 'export_image']);

export function toolDeclarationSubset(names: Set<string>) {
  return TOOL_DECLARATIONS.filter((d) => names.has(d.name));
}

/* Toast + UI helpers used by the runtime for user-visible feedback. */
export function uiToast(message: string, tone: 'info' | 'success' | 'error' | 'ai', detail?: string) {
  return useUIStore.getState().pushToast({ message, tone, detail });
}

export { BACKGROUND_ID };
