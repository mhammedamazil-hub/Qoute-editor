export type BlendMode =
  | 'normal'
  | 'multiply'
  | 'screen'
  | 'overlay'
  | 'soft-light'
  | 'hard-light'
  | 'darken'
  | 'lighten'
  | 'color-dodge'
  | 'difference';

export const BLEND_MODES: BlendMode[] = [
  'normal',
  'multiply',
  'screen',
  'overlay',
  'soft-light',
  'hard-light',
  'darken',
  'lighten',
  'color-dodge',
  'difference',
];

export interface GradientStop {
  offset: number; // 0..1
  color: string; // hex
  opacity: number; // 0..1
}

export type GradientType = 'linear' | 'radial' | 'conic';

export interface GradientFill {
  type: GradientType;
  stops: GradientStop[];
  angle: number; // degrees, linear + conic
  cx: number; // 0..1 radial/conic center
  cy: number; // 0..1
  radius: number; // 0..1.5 relative to max(w,h)
}

export type Fill =
  | { kind: 'solid'; color: string }
  | { kind: 'gradient'; gradient: GradientFill };

export type BackgroundFill = Fill | { kind: 'image'; assetId: string };

export interface ShadowEffect {
  enabled: boolean;
  x: number;
  y: number;
  blur: number;
  color: string;
  opacity: number;
}

export interface GlowEffect {
  enabled: boolean;
  color: string;
  radius: number;
  intensity: number; // 0..1
}

export type ElementType =
  | 'text'
  | 'quoteMark'
  | 'shape'
  | 'light'
  | 'gradient'
  | 'image'
  | 'particles'
  | 'group';

export interface BaseElement {
  id: string;
  type: ElementType;
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  opacity: number;
  visible: boolean;
  locked: boolean;
  blendMode: BlendMode;
  blur: number;
  shadow: ShadowEffect;
  glow: GlowEffect;
  parentId: string | null;
}

export type TextAlign = 'left' | 'center' | 'right';

export interface TextElement extends BaseElement {
  type: 'text' | 'quoteMark';
  content: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  italic: boolean;
  underline: boolean;
  letterSpacing: number;
  lineHeight: number;
  align: TextAlign;
  fill: Fill;
  stroke: string;
  strokeWidth: number;
}

export type ShapeKind =
  | 'rect'
  | 'roundedRect'
  | 'circle'
  | 'ellipse'
  | 'triangle'
  | 'polygon'
  | 'star'
  | 'line'
  | 'arrow'
  | 'ring'
  | 'arc'
  | 'cornerFrame'
  | 'grid'
  | 'dots'
  | 'crosshair'
  | 'plus';

export interface ShapeElement extends BaseElement {
  type: 'shape';
  shape: ShapeKind;
  fill: Fill | null;
  stroke: string;
  strokeWidth: number;
  cornerRadius: number;
  sides: number;
  innerRatio: number; // star inner radius ratio, ring thickness ratio
  arcAngle: number;
  dashed: boolean;
  spacing: number; // grid / dots spacing
}

export interface LightElement extends BaseElement {
  type: 'light';
  color: string;
  intensity: number; // 0..1
  softness: number; // 0..1
}

export interface GradientElement extends BaseElement {
  type: 'gradient';
  gradient: GradientFill;
}

export type MaskType = 'none' | 'rect' | 'roundedRect' | 'circle' | 'ellipse' | 'linear';

export interface ImageMask {
  type: MaskType;
  x: number; // 0..1 fraction of element
  y: number;
  w: number;
  h: number;
  feather: number; // 0..1
  invert: boolean;
  cornerRadius: number; // 0..1
  angle: number; // for linear
}

export interface ImageAdjustments {
  brightness: number; // -1..1
  contrast: number; // -1..1
  saturation: number; // -1..1
  hue: number; // -180..180
  exposure: number; // -1..1
  blur: number; // px
  grayscale: number; // 0..1
  sepia: number; // 0..1
}

export interface ImageElement extends BaseElement {
  type: 'image';
  assetId: string;
  naturalWidth: number;
  naturalHeight: number;
  crop: { x: number; y: number; w: number; h: number }; // fractions
  adjustments: ImageAdjustments;
  mask: ImageMask;
}

export interface ParticlesElement extends BaseElement {
  type: 'particles';
  count: number;
  seed: number;
  color: string;
  minSize: number;
  maxSize: number;
}

export interface GroupElement extends BaseElement {
  type: 'group';
  scaleX: number;
  scaleY: number;
}

export type AnyElement =
  | TextElement
  | ShapeElement
  | LightElement
  | GradientElement
  | ImageElement
  | ParticlesElement
  | GroupElement;
