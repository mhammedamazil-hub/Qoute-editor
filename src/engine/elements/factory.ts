import type {
  AnyElement,
  BaseElement,
  GradientElement,
  GradientFill,
  GroupElement,
  ImageElement,
  LightElement,
  ParticlesElement,
  ShapeElement,
  ShapeKind,
  TextElement,
} from '@/types/elements';
import { uid } from '../ids';
import { makeGradient } from '../gradient';

export function baseElement(type: AnyElement['type'], name: string, partial: Partial<BaseElement> = {}): BaseElement {
  return {
    id: uid(type),
    type,
    name,
    x: 0,
    y: 0,
    width: 200,
    height: 200,
    rotation: 0,
    opacity: 1,
    visible: true,
    locked: false,
    blendMode: 'normal',
    blur: 0,
    shadow: { enabled: false, x: 0, y: 12, blur: 30, color: '#000000', opacity: 0.6 },
    glow: { enabled: false, color: '#d9a441', radius: 30, intensity: 0.8 },
    parentId: null,
    ...partial,
  };
}

export function createText(partial: Partial<TextElement> = {}): TextElement {
  const base = baseElement('text', 'Text', { width: 600, height: 100 });
  return {
    ...base,
    type: 'text',
    content: 'Your quote goes here',
    fontFamily: 'Playfair Display',
    fontSize: 64,
    fontWeight: 500,
    italic: false,
    underline: false,
    letterSpacing: 0,
    lineHeight: 1.2,
    align: 'left',
    fill: { kind: 'solid', color: '#f5f1e7' },
    stroke: '#000000',
    strokeWidth: 0,
    ...partial,
    id: partial.id ?? base.id,
  };
}

export function createQuoteMark(partial: Partial<TextElement> = {}): TextElement {
  return createText({
    type: 'quoteMark',
    name: 'Quote Mark',
    content: '\u201C',
    fontFamily: 'Playfair Display',
    fontSize: 220,
    fontWeight: 700,
    lineHeight: 0.8,
    width: 160,
    height: 160,
    fill: { kind: 'solid', color: '#d9a441' },
    ...partial,
  });
}

const SHAPE_NAMES: Record<ShapeKind, string> = {
  rect: 'Rectangle',
  roundedRect: 'Rounded Rectangle',
  circle: 'Circle',
  ellipse: 'Ellipse',
  triangle: 'Triangle',
  polygon: 'Polygon',
  star: 'Star',
  line: 'Line',
  arrow: 'Arrow',
  ring: 'Ring',
  arc: 'Arc',
  cornerFrame: 'Corner Frame',
  grid: 'Grid',
  dots: 'Dots',
  crosshair: 'Crosshair',
  plus: 'Plus',
};

export function createShape(shape: ShapeKind, partial: Partial<ShapeElement> = {}): ShapeElement {
  const strokeOnly: ShapeKind[] = ['line', 'arrow', 'arc', 'cornerFrame', 'grid', 'crosshair', 'plus'];
  const base = baseElement('shape', SHAPE_NAMES[shape], { width: 300, height: 300 });
  const isLine = shape === 'line' || shape === 'arrow';
  return {
    ...base,
    type: 'shape',
    shape,
    fill: strokeOnly.includes(shape) ? null : shape === 'dots' ? { kind: 'solid', color: '#d9a441' } : { kind: 'solid', color: '#d9a441' },
    stroke: '#d9a441',
    strokeWidth: strokeOnly.includes(shape) ? 2 : 0,
    cornerRadius: shape === 'roundedRect' ? 24 : 0,
    sides: 6,
    innerRatio: shape === 'star' ? 0.5 : 0.85,
    arcAngle: 240,
    dashed: false,
    spacing: 40,
    width: isLine ? 400 : shape === 'ellipse' ? 400 : 300,
    height: isLine ? 2 : shape === 'ellipse' ? 240 : 300,
    ...partial,
    id: partial.id ?? base.id,
  };
}

export const LIGHT_PRESETS: { id: string; label: string; color: string }[] = [
  { id: 'amber', label: 'Amber', color: '#d89b35' },
  { id: 'gold', label: 'Gold', color: '#f0c96a' },
  { id: 'white', label: 'White', color: '#ffffff' },
  { id: 'green', label: 'Green', color: '#3fbf7f' },
  { id: 'emerald', label: 'Emerald', color: '#12a37f' },
  { id: 'blue', label: 'Blue', color: '#3a7bff' },
  { id: 'purple', label: 'Purple', color: '#8b5cf6' },
  { id: 'red', label: 'Red', color: '#e0453b' },
];

export function createLight(color = '#d89b35', partial: Partial<LightElement> = {}): LightElement {
  const preset = LIGHT_PRESETS.find((p) => p.color === color);
  const base = baseElement('light', `${preset ? preset.label : 'Custom'} Light`, { width: 700, height: 700, blendMode: 'screen' });
  return {
    ...base,
    type: 'light',
    color,
    intensity: 0.6,
    softness: 0.7,
    ...partial,
    id: partial.id ?? base.id,
  };
}

export function createGradientLayer(gradient?: Partial<GradientFill>, partial: Partial<GradientElement> = {}): GradientElement {
  const base = baseElement('gradient', 'Gradient', { width: 1080, height: 1080 });
  return {
    ...base,
    type: 'gradient',
    gradient: makeGradient({
      type: 'radial',
      stops: [
        { offset: 0, color: '#d89b35', opacity: 0.6 },
        { offset: 1, color: '#d89b35', opacity: 0 },
      ],
      ...gradient,
    }),
    ...partial,
    id: partial.id ?? base.id,
  };
}

export function createImage(assetId: string, naturalWidth: number, naturalHeight: number, partial: Partial<ImageElement> = {}): ImageElement {
  const base = baseElement('image', 'Image', { width: naturalWidth, height: naturalHeight });
  return {
    ...base,
    type: 'image',
    assetId,
    naturalWidth,
    naturalHeight,
    crop: { x: 0, y: 0, w: 1, h: 1 },
    adjustments: { brightness: 0, contrast: 0, saturation: 0, hue: 0, exposure: 0, blur: 0, grayscale: 0, sepia: 0 },
    mask: { type: 'none', x: 0, y: 0, w: 1, h: 1, feather: 0, invert: false, cornerRadius: 0.1, angle: 180 },
    ...partial,
    id: partial.id ?? base.id,
  };
}

export function createParticles(partial: Partial<ParticlesElement> = {}): ParticlesElement {
  const base = baseElement('particles', 'Particles', { width: 1080, height: 1080, opacity: 0.6 });
  return {
    ...base,
    type: 'particles',
    count: 60,
    seed: Math.floor(Math.random() * 10000),
    color: '#f0c96a',
    minSize: 1,
    maxSize: 4,
    ...partial,
    id: partial.id ?? base.id,
  };
}

export function createGroup(partial: Partial<GroupElement> = {}): GroupElement {
  const base = baseElement('group', 'Group');
  return { ...base, type: 'group', scaleX: 1, scaleY: 1, ...partial, id: partial.id ?? base.id };
}

/* ---------- Decorative elements library ---------- */

export interface DecorationDef {
  id: string;
  label: string;
  create: (cw: number, ch: number) => AnyElement;
}

const centered = (cw: number, ch: number, w: number, h: number) => ({ x: (cw - w) / 2, y: (ch - h) / 2, width: w, height: h });

export const DECORATIONS: DecorationDef[] = [
  { id: 'thin-line', label: 'Thin line', create: (cw, ch) => createShape('line', { name: 'Thin Line', ...centered(cw, ch, 420, 1), strokeWidth: 1 }) },
  { id: 'vline', label: 'Vertical line', create: (cw, ch) => createShape('line', { name: 'Vertical Line', ...centered(cw, ch, 2, 500), strokeWidth: 2, glow: { enabled: true, color: '#d9a441', radius: 14, intensity: 0.8 } }) },
  { id: 'hline', label: 'Horizontal line', create: (cw, ch) => createShape('line', { name: 'Horizontal Line', ...centered(cw, ch, 520, 2), strokeWidth: 2 }) },
  { id: 'corner', label: 'Corner frame', create: (cw, ch) => createShape('cornerFrame', { ...centered(cw, ch, cw * 0.86, ch * 0.86), strokeWidth: 1.5, spacing: 70 }) },
  { id: 'circle', label: 'Circle', create: (cw, ch) => createShape('circle', { ...centered(cw, ch, 360, 360), fill: null, strokeWidth: 1.5 }) },
  { id: 'ring', label: 'Ring', create: (cw, ch) => createShape('ring', { ...centered(cw, ch, 420, 420), strokeWidth: 0, innerRatio: 0.96 }) },
  { id: 'arc', label: 'Arc', create: (cw, ch) => createShape('arc', { ...centered(cw, ch, 480, 480), strokeWidth: 1.5, arcAngle: 200 }) },
  { id: 'grid', label: 'Grid', create: (cw, ch) => createShape('grid', { ...centered(cw, ch, cw, ch), strokeWidth: 0.6, spacing: 90, opacity: 0.25 }) },
  { id: 'dots', label: 'Dots', create: (cw, ch) => createShape('dots', { ...centered(cw, ch, 300, 300), spacing: 30, opacity: 0.5 }) },
  { id: 'particles', label: 'Particles', create: (cw, ch) => createParticles({ x: 0, y: 0, width: cw, height: ch }) },
  { id: 'crosshair', label: 'Crosshair', create: (cw, ch) => createShape('crosshair', { ...centered(cw, ch, 120, 120), strokeWidth: 1 }) },
  { id: 'plus', label: 'Plus', create: (cw, ch) => createShape('plus', { ...centered(cw, ch, 40, 40), strokeWidth: 1.5 }) },
  { id: 'star', label: 'Star', create: (cw, ch) => createShape('star', { ...centered(cw, ch, 60, 60) }) },
  { id: 'frame', label: 'Geometric frame', create: (cw, ch) => createShape('rect', { name: 'Geometric Frame', ...centered(cw, ch, cw * 0.8, ch * 0.8), fill: null, strokeWidth: 1 }) },
  { id: 'quote-open', label: 'Quote mark \u201C', create: (cw, ch) => createQuoteMark({ ...centered(cw, ch, 160, 160), content: '\u201C' }) },
  { id: 'quote-close', label: 'Quote mark \u201D', create: (cw, ch) => createQuoteMark({ ...centered(cw, ch, 160, 160), content: '\u201D' }) },
  { id: 'quote-heavy', label: 'Quote mark \u275D', create: (cw, ch) => createQuoteMark({ ...centered(cw, ch, 160, 160), content: '\u275D', fontFamily: 'Inter' }) },
  { id: 'triangle', label: 'Triangle', create: (cw, ch) => createShape('triangle', { ...centered(cw, ch, 200, 180), fill: null, strokeWidth: 1.5 }) },
  { id: 'hexagon', label: 'Hexagon', create: (cw, ch) => createShape('polygon', { ...centered(cw, ch, 260, 260), fill: null, strokeWidth: 1.5, sides: 6 }) },
];

export const QUOTE_MARK_GLYPHS = ['"', '\u201C', '\u201D', '\u275D', '\u275E'];
