import type { BackgroundFill } from '@/types/elements';
import { makeGradient } from './gradient';

export interface PaletteLight {
  color: string;
  /** Position as fraction of the canvas (0..1) — lights sit partly off-canvas. */
  at: [number, number];
  radius: number;
  intensity: number;
  softness: number;
}

export interface Palette {
  id: string;
  label: string;
  blurb: string;
  light: boolean;
  background: BackgroundFill;
  text: string;
  author: string;
  accent: string;
  lights: PaletteLight[];
  swatches: string[];
}

const solid = (color: string): BackgroundFill => ({ kind: 'solid', color });
const radial = (color: string, opacity: number, cx: number, cy: number): BackgroundFill => ({
  kind: 'gradient',
  gradient: makeGradient({
    type: 'radial',
    cx,
    cy,
    radius: 1.1,
    stops: [
      { offset: 0, color, opacity },
      { offset: 0.55, color, opacity: opacity * 0.35 },
      { offset: 1, color, opacity: 0 },
    ],
  }),
});

export const PALETTES: Palette[] = [
  {
    id: 'midnight-gold',
    label: 'Midnight & Gold',
    blurb: 'Cinematic black, warm amber light, gold accent.',
    light: false,
    background: solid('#050608'),
    text: '#f5f1e7',
    author: '#d9a441',
    accent: '#d9a441',
    lights: [
      { color: '#d89b35', at: [0.78, -0.12], radius: 620, intensity: 0.55, softness: 0.85 },
      { color: '#12a37f', at: [-0.15, 0.85], radius: 520, intensity: 0.3, softness: 0.9 },
    ],
    swatches: ['#050608', '#d89b35', '#d9a441', '#f5f1e7', '#12a37f'],
  },
  {
    id: 'ivory-editorial',
    label: 'Ivory Editorial',
    blurb: 'Warm paper canvas, ink type, restrained brass rules.',
    light: true,
    background: solid('#f4efe6'),
    text: '#1a1714',
    author: '#8a6f45',
    accent: '#b08a45',
    lights: [{ color: '#ffffff', at: [0.2, 0.1], radius: 700, intensity: 0.25, softness: 0.95 }],
    swatches: ['#f4efe6', '#1a1714', '#b08a45', '#e2d6c3'],
  },
  {
    id: 'emerald-luxury',
    label: 'Emerald Luxury',
    blurb: 'Deep emerald with jade light and cream type.',
    light: false,
    background: solid('#04140f'),
    text: '#f2f7f4',
    author: '#9fd6bd',
    accent: '#3fbf7f',
    lights: [
      { color: '#12a37f', at: [0.25, 0.15], radius: 640, intensity: 0.5, softness: 0.88 },
      { color: '#d9a441', at: [0.95, 0.9], radius: 480, intensity: 0.28, softness: 0.9 },
    ],
    swatches: ['#04140f', '#12a37f', '#3fbf7f', '#f2f7f4'],
  },
  {
    id: 'neon-night',
    label: 'Neon Night',
    blurb: 'Electric magenta and cyan on near-black.',
    light: false,
    background: solid('#08060f'),
    text: '#f7f5ff',
    author: '#c084fc',
    accent: '#e879f9',
    lights: [
      { color: '#8b5cf6', at: [0.2, 0.1], radius: 560, intensity: 0.55, softness: 0.8 },
      { color: '#22d3ee', at: [0.9, 0.85], radius: 520, intensity: 0.42, softness: 0.85 },
    ],
    swatches: ['#08060f', '#8b5cf6', '#e879f9', '#22d3ee'],
  },
  {
    id: 'sunset-warm',
    label: 'Sunset Warm',
    blurb: 'Burnt orange glow with cream typography.',
    light: false,
    background: radial('#7a2d0c', 0.85, 0.7, 0.15),
    text: '#fff4e6',
    author: '#ffcf9e',
    accent: '#ff8a3d',
    lights: [
      { color: '#ff7a18', at: [0.75, 0.08], radius: 660, intensity: 0.5, softness: 0.85 },
      { color: '#ffb347', at: [0.1, 0.9], radius: 520, intensity: 0.3, softness: 0.9 },
    ],
    swatches: ['#2b1206', '#ff7a18', '#ffb347', '#fff4e6'],
  },
  {
    id: 'mono-press',
    label: 'Monochrome Press',
    blurb: 'Pure greyscale, Swiss grid, zero colour noise.',
    light: true,
    background: solid('#f2f2f2'),
    text: '#101010',
    author: '#5a5a5a',
    accent: '#101010',
    lights: [{ color: '#ffffff', at: [0.5, 0.0], radius: 800, intensity: 0.2, softness: 1 }],
    swatches: ['#f2f2f2', '#101010', '#5a5a5a', '#c9c9c9'],
  },
  {
    id: 'royal-navy',
    label: 'Royal Navy',
    blurb: 'Navy gradient, soft steel light, warm sand accent.',
    light: false,
    background: radial('#123059', 0.9, 0.3, 0.2),
    text: '#eef4ff',
    author: '#e2c48a',
    accent: '#3a7bff',
    lights: [
      { color: '#3a7bff', at: [0.15, 0.1], radius: 620, intensity: 0.45, softness: 0.88 },
      { color: '#e2c48a', at: [0.9, 0.95], radius: 460, intensity: 0.28, softness: 0.9 },
    ],
    swatches: ['#0a1a30', '#3a7bff', '#e2c48a', '#eef4ff'],
  },
  {
    id: 'sage-calm',
    label: 'Sage Calm',
    blurb: 'Muted sage paper, deep moss type. Quiet and gentle.',
    light: true,
    background: solid('#e7ece4'),
    text: '#22301f',
    author: '#5c6b52',
    accent: '#7c8f6b',
    lights: [{ color: '#ffffff', at: [0.8, 0.1], radius: 700, intensity: 0.22, softness: 0.95 }],
    swatches: ['#e7ece4', '#22301f', '#7c8f6b', '#c3cebb'],
  },
];

export function findPalette(id: string | undefined): Palette | undefined {
  return PALETTES.find((p) => p.id === id);
}

/** Applies a palette to an existing design, keeping the text elements' content. */
export function paletteLightsFor(p: Palette, canvasW: number, canvasH: number) {
  const scale = Math.max(canvasW, canvasH) / 1080;
  return p.lights.map((l) => ({
    color: l.color,
    x: l.at[0] * canvasW,
    y: l.at[1] * canvasH,
    radius: l.radius * Math.max(0.55, scale),
    intensity: l.intensity,
    softness: l.softness,
  }));
}
