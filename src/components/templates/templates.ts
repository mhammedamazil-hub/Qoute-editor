import type { AnyElement, BackgroundFill } from '@/types/elements';
import type { SceneDocument } from '@/types/project';
import { createGradientLayer, createLight, createParticles, createQuoteMark, createShape, createText } from '@/engine/elements/factory';

export interface TemplateDef {
  id: string;
  name: string;
  description: string;
  width: number;
  height: number;
  swatches: string[];
  build: () => SceneDocument;
}

const solid = (color: string): BackgroundFill => ({ kind: 'solid', color });

function scene(width: number, height: number, background: BackgroundFill, elements: AnyElement[]): SceneDocument {
  return { canvas: { width, height, background }, elements };
}

const quoteText = (o: Partial<Parameters<typeof createText>[0]>) => createText({ name: 'Main Quote', ...o });
const authorText = (o: Partial<Parameters<typeof createText>[0]>) => createText({ name: 'Author', fontFamily: 'Inter', fontSize: 22, fontWeight: 500, letterSpacing: 4, fill: { kind: 'solid', color: '#d9a441' }, height: 30, ...o });

export const TEMPLATES: TemplateDef[] = [
  {
    id: 'dark-cinematic',
    name: 'Dark Cinematic',
    description: 'Amber and emerald atmosphere, thin gold line, editorial serif.',
    width: 1080, height: 1350, swatches: ['#050608', '#d89b35', '#12a37f', '#f5f1e7'],
    build: () => scene(1080, 1350, solid('#050608'), [
      createLight('#d89b35', { name: 'Amber Light', x: 520, y: -420, width: 1000, height: 1000, intensity: 0.55, softness: 0.85 }),
      createLight('#12a37f', { name: 'Emerald Light', x: -500, y: 800, width: 900, height: 900, intensity: 0.35, softness: 0.9 }),
      createShape('circle', { name: 'Geometric Circle', x: 560, y: 140, width: 520, height: 520, fill: null, stroke: '#d9a441', strokeWidth: 1, opacity: 0.35 }),
      createShape('line', { name: 'Gold Vertical Line', x: 96, y: 380, width: 2, height: 520, stroke: '#d6a64a', strokeWidth: 2, glow: { enabled: true, color: '#d6a64a', radius: 16, intensity: 0.9 } }),
      createQuoteMark({ x: 132, y: 300, width: 140, height: 140, fontSize: 200, opacity: 0.9 }),
      quoteText({ x: 140, y: 440, width: 780, height: 320, fontSize: 60, fontWeight: 500, content: 'Discipline is choosing between what you want now and what you want most.', lineHeight: 1.25, shadow: { enabled: true, x: 0, y: 8, blur: 30, color: '#000000', opacity: 0.6 } }),
      authorText({ x: 140, y: 820, width: 500, content: '— ABRAHAM LINCOLN' }),
      createParticles({ x: 0, y: 0, width: 1080, height: 1350, count: 50, opacity: 0.45, seed: 42 }),
      createShape('cornerFrame', { name: 'Frame', x: 60, y: 60, width: 960, height: 1230, stroke: '#d9a441', strokeWidth: 1, spacing: 60, opacity: 0.5 }),
    ]),
  },
  {
    id: 'minimal-quote',
    name: 'Minimal Quote',
    description: 'Warm off-white canvas, generous negative space.',
    width: 1080, height: 1080, swatches: ['#f4efe6', '#1a1714', '#b08a45'],
    build: () => scene(1080, 1080, solid('#f4efe6'), [
      createShape('line', { name: 'Divider', x: 490, y: 300, width: 100, height: 2, stroke: '#b08a45', strokeWidth: 2 }),
      quoteText({ x: 140, y: 380, width: 800, height: 260, fontFamily: 'Cormorant Garamond', fontSize: 64, fontWeight: 500, italic: true, align: 'center', fill: { kind: 'solid', color: '#1a1714' }, content: 'Simplicity is the ultimate sophistication.' }),
      authorText({ x: 240, y: 700, width: 600, align: 'center', fill: { kind: 'solid', color: '#7a6a52' }, content: 'LEONARDO DA VINCI' }),
    ]),
  },
  {
    id: 'black-gold',
    name: 'Black & Gold',
    description: 'Luxury contrast with a gold gradient headline.',
    width: 1080, height: 1350, swatches: ['#000000', '#f0c96a', '#8a5f16'],
    build: () => scene(1080, 1350, solid('#000000'), [
      createLight('#f0c96a', { name: 'Gold Light', x: 240, y: 200, width: 600, height: 600, intensity: 0.22, softness: 0.95 }),
      createShape('rect', { name: 'Gold Frame', x: 80, y: 80, width: 920, height: 1190, fill: null, stroke: '#d9a441', strokeWidth: 1, opacity: 0.6 }),
      createShape('rect', { name: 'Inner Frame', x: 96, y: 96, width: 888, height: 1158, fill: null, stroke: '#d9a441', strokeWidth: 0.5, opacity: 0.35 }),
      quoteText({ x: 160, y: 460, width: 760, height: 320, fontFamily: 'Playfair Display', fontSize: 68, fontWeight: 700, align: 'center', content: 'Luxury is in each detail.', fill: { kind: 'gradient', gradient: { type: 'linear', angle: 180, cx: 0.5, cy: 0.5, radius: 0.7, stops: [{ offset: 0, color: '#fbe7a6', opacity: 1 }, { offset: 0.5, color: '#d9a441', opacity: 1 }, { offset: 1, color: '#8a5f16', opacity: 1 }] } } }),
      createShape('line', { name: 'Divider', x: 480, y: 800, width: 120, height: 1, stroke: '#d9a441', strokeWidth: 1 }),
      authorText({ x: 240, y: 840, width: 600, align: 'center', content: 'HUBERT DE GIVENCHY', fill: { kind: 'solid', color: '#c9b78a' } }),
    ]),
  },
  {
    id: 'emerald-luxury',
    name: 'Emerald Luxury',
    description: 'Deep green atmosphere with a soft gold accent.',
    width: 1080, height: 1350, swatches: ['#03100c', '#12a37f', '#e7d7a8'],
    build: () => scene(1080, 1350, solid('#03100c'), [
      createGradientLayer({ type: 'radial', cx: 0.5, cy: 1.1, radius: 0.8, stops: [{ offset: 0, color: '#12a37f', opacity: 0.45 }, { offset: 1, color: '#12a37f', opacity: 0 }] }, { name: 'Emerald Glow', width: 1080, height: 1350 }),
      createLight('#d9a441', { name: 'Gold Light', x: 700, y: -200, width: 700, height: 700, intensity: 0.3, softness: 0.9 }),
      createShape('ring', { name: 'Ring', x: 340, y: 160, width: 400, height: 400, fill: { kind: 'solid', color: '#e7d7a8' }, strokeWidth: 0, innerRatio: 0.985, opacity: 0.6 }),
      quoteText({ x: 140, y: 560, width: 800, height: 300, fontFamily: 'Libre Baskerville', fontSize: 52, align: 'center', content: 'Grow through what you go through.', fill: { kind: 'solid', color: '#eef3ee' }, lineHeight: 1.35 }),
      authorText({ x: 240, y: 880, width: 600, align: 'center', content: 'UNKNOWN', fill: { kind: 'solid', color: '#9ad4bf' } }),
      createParticles({ x: 0, y: 0, width: 1080, height: 1350, count: 40, color: '#e7d7a8', opacity: 0.4, seed: 7 }),
    ]),
  },
  {
    id: 'editorial',
    name: 'Editorial',
    description: 'Magazine layout with rules, small caps and left alignment.',
    width: 1080, height: 1350, swatches: ['#0f0f10', '#ededea', '#c2410c'],
    build: () => scene(1080, 1350, solid('#0f0f10'), [
      createShape('line', { name: 'Top Rule', x: 100, y: 140, width: 880, height: 2, stroke: '#ededea', strokeWidth: 2 }),
      createText({ name: 'Kicker', x: 100, y: 170, width: 500, height: 24, content: 'ISSUE 04 · ON PATIENCE', fontFamily: 'Space Grotesk', fontSize: 18, fontWeight: 500, letterSpacing: 4, fill: { kind: 'solid', color: '#a3a3a0' } }),
      createText({ name: 'Number', x: 780, y: 160, width: 200, height: 60, content: '01', fontFamily: 'Bebas Neue', fontSize: 64, fontWeight: 400, align: 'right', fill: { kind: 'solid', color: '#c2410c' } }),
      quoteText({ x: 100, y: 380, width: 880, height: 400, fontFamily: 'DM Serif Display', fontSize: 84, fontWeight: 400, lineHeight: 1.05, content: 'Patience is not the ability to wait, but how you act while waiting.', fill: { kind: 'solid', color: '#ededea' } }),
      createShape('line', { name: 'Bottom Rule', x: 100, y: 1180, width: 880, height: 1, stroke: '#ededea', strokeWidth: 1, opacity: 0.4 }),
      authorText({ x: 100, y: 1200, width: 500, content: 'JOYCE MEYER', fontFamily: 'Space Grotesk', fill: { kind: 'solid', color: '#ededea' } }),
    ]),
  },
  {
    id: 'modern-typography',
    name: 'Modern Typography',
    description: 'Bold condensed type with a single accent color.',
    width: 1080, height: 1080, swatches: ['#101114', '#ffffff', '#3a7bff'],
    build: () => scene(1080, 1080, solid('#101114'), [
      createLight('#3a7bff', { name: 'Blue Light', x: -300, y: -300, width: 900, height: 900, intensity: 0.4, softness: 0.9 }),
      createText({ name: 'Headline', x: 80, y: 220, width: 920, height: 500, content: 'MAKE IT\nHAPPEN.', fontFamily: 'Bebas Neue', fontSize: 240, fontWeight: 400, lineHeight: 0.9, letterSpacing: 2, fill: { kind: 'solid', color: '#ffffff' } }),
      createShape('rect', { name: 'Accent Block', x: 80, y: 720, width: 180, height: 14, fill: { kind: 'solid', color: '#3a7bff' }, strokeWidth: 0 }),
      createText({ name: 'Subline', x: 80, y: 770, width: 700, height: 60, content: 'Action is the foundational key to all success.', fontFamily: 'Space Grotesk', fontSize: 28, fontWeight: 400, fill: { kind: 'solid', color: '#b8bec9' } }),
      authorText({ x: 80, y: 840, width: 500, content: 'PABLO PICASSO', fill: { kind: 'solid', color: '#3a7bff' } }),
    ]),
  },
  {
    id: 'motivational',
    name: 'Motivational',
    description: 'Story format with warm gradient and centered message.',
    width: 1080, height: 1920, swatches: ['#1a0b05', '#e0453b', '#f7c46c'],
    build: () => scene(1080, 1920, { kind: 'gradient', gradient: { type: 'linear', angle: 180, cx: 0.5, cy: 0.5, radius: 0.7, stops: [{ offset: 0, color: '#1a0b05', opacity: 1 }, { offset: 1, color: '#050608', opacity: 1 }] } }, [
      createLight('#e0453b', { name: 'Red Light', x: 190, y: 250, width: 700, height: 700, intensity: 0.5, softness: 0.9 }),
      createLight('#f7c46c', { name: 'Warm Light', x: 340, y: 1300, width: 800, height: 800, intensity: 0.35, softness: 0.95 }),
      createShape('circle', { name: 'Circle', x: 340, y: 380, width: 400, height: 400, fill: null, stroke: '#f7c46c', strokeWidth: 1.5, opacity: 0.6 }),
      quoteText({ x: 120, y: 820, width: 840, height: 420, fontFamily: 'Montserrat', fontSize: 64, fontWeight: 700, align: 'center', lineHeight: 1.2, content: 'Your only limit is the one you accept.', fill: { kind: 'solid', color: '#fff8ef' } }),
      authorText({ x: 240, y: 1290, width: 600, align: 'center', content: 'KEEP GOING', fill: { kind: 'solid', color: '#f7c46c' } }),
    ]),
  },
  {
    id: 'islamic-minimal',
    name: 'Islamic Minimal',
    description: 'Geometric star, calm teal, elegant serif — respectful and minimal.',
    width: 1080, height: 1350, swatches: ['#07161a', '#c9a961', '#e9f1f0'],
    build: () => scene(1080, 1350, solid('#07161a'), [
      createLight('#1f8a7a', { name: 'Teal Light', x: 240, y: -150, width: 600, height: 600, intensity: 0.35, softness: 0.95 }),
      createShape('star', { name: 'Eight-point Star', x: 440, y: 180, width: 200, height: 200, fill: null, stroke: '#c9a961', strokeWidth: 1.5, sides: 8, innerRatio: 0.78 }),
      createShape('circle', { name: 'Outer Circle', x: 400, y: 140, width: 280, height: 280, fill: null, stroke: '#c9a961', strokeWidth: 0.75, opacity: 0.6 }),
      quoteText({ x: 140, y: 560, width: 800, height: 300, fontFamily: 'Cormorant Garamond', fontSize: 60, fontWeight: 500, align: 'center', lineHeight: 1.35, content: 'Verily, with hardship comes ease.', fill: { kind: 'solid', color: '#e9f1f0' } }),
      authorText({ x: 240, y: 880, width: 600, align: 'center', content: 'QUR’AN 94:6', fill: { kind: 'solid', color: '#c9a961' } }),
      createShape('line', { name: 'Divider', x: 490, y: 960, width: 100, height: 1, stroke: '#c9a961', strokeWidth: 1 }),
    ]),
  },
  {
    id: 'elegant-serif',
    name: 'Elegant Serif',
    description: 'Cream background, italic serif, subtle drop caps feel.',
    width: 1080, height: 1350, swatches: ['#f7f3ec', '#2b2622', '#a67c52'],
    build: () => scene(1080, 1350, solid('#f7f3ec'), [
      createShape('rect', { name: 'Frame', x: 70, y: 70, width: 940, height: 1210, fill: null, stroke: '#2b2622', strokeWidth: 1, opacity: 0.35 }),
      createQuoteMark({ x: 470, y: 260, width: 140, height: 140, fontSize: 180, fontFamily: 'Cormorant Garamond', align: 'center', fill: { kind: 'solid', color: '#a67c52' } }),
      quoteText({ x: 150, y: 460, width: 780, height: 360, fontFamily: 'Playfair Display', fontSize: 56, italic: true, fontWeight: 400, align: 'center', lineHeight: 1.4, content: 'Elegance is the only beauty that never fades.', fill: { kind: 'solid', color: '#2b2622' } }),
      authorText({ x: 240, y: 880, width: 600, align: 'center', content: 'AUDREY HEPBURN', fill: { kind: 'solid', color: '#a67c52' } }),
    ]),
  },
  {
    id: 'neon-quote',
    name: 'Neon Quote',
    description: 'Glowing magenta and cyan on near-black.',
    width: 1080, height: 1080, swatches: ['#07060c', '#ff2ea6', '#22d3ee'],
    build: () => scene(1080, 1080, solid('#07060c'), [
      createLight('#ff2ea6', { name: 'Magenta Light', x: -250, y: 500, width: 800, height: 800, intensity: 0.4, softness: 0.9 }),
      createLight('#22d3ee', { name: 'Cyan Light', x: 600, y: -300, width: 800, height: 800, intensity: 0.4, softness: 0.9 }),
      createShape('grid', { name: 'Grid', x: 0, y: 0, width: 1080, height: 1080, stroke: '#ffffff', strokeWidth: 0.5, spacing: 80, opacity: 0.08 }),
      createShape('roundedRect', { name: 'Neon Frame', x: 140, y: 300, width: 800, height: 480, fill: null, stroke: '#22d3ee', strokeWidth: 2, cornerRadius: 16, glow: { enabled: true, color: '#22d3ee', radius: 30, intensity: 1 } }),
      quoteText({ x: 190, y: 400, width: 700, height: 200, fontFamily: 'Space Grotesk', fontSize: 58, fontWeight: 700, align: 'center', content: 'Stay hungry. Stay foolish.', fill: { kind: 'solid', color: '#ffffff' }, glow: { enabled: true, color: '#ff2ea6', radius: 40, intensity: 1 } }),
      authorText({ x: 240, y: 640, width: 600, align: 'center', content: 'STEVE JOBS', fill: { kind: 'solid', color: '#22d3ee' } }),
    ]),
  },
  {
    id: 'monochrome',
    name: 'Monochrome',
    description: 'Pure black and white, strong grid and type.',
    width: 1080, height: 1350, swatches: ['#ffffff', '#000000'],
    build: () => scene(1080, 1350, solid('#ffffff'), [
      createShape('rect', { name: 'Black Block', x: 0, y: 0, width: 1080, height: 620, fill: { kind: 'solid', color: '#000000' }, strokeWidth: 0 }),
      createText({ name: 'Headline', x: 90, y: 120, width: 900, height: 400, content: 'LESS,\nBUT BETTER.', fontFamily: 'Montserrat', fontSize: 120, fontWeight: 800, lineHeight: 1, fill: { kind: 'solid', color: '#ffffff' } }),
      quoteText({ x: 90, y: 720, width: 800, height: 240, fontFamily: 'Inter', fontSize: 34, fontWeight: 400, lineHeight: 1.5, content: 'Good design is as little design as possible. It concentrates on the essential aspects.', fill: { kind: 'solid', color: '#000000' } }),
      authorText({ x: 90, y: 1040, width: 500, content: 'DIETER RAMS', fill: { kind: 'solid', color: '#000000' } }),
      createShape('plus', { name: 'Plus', x: 960, y: 1230, width: 40, height: 40, stroke: '#000000', strokeWidth: 2 }),
    ]),
  },
  {
    id: 'luxury-poster',
    name: 'Luxury Poster',
    description: 'Cinematic 4:5 with arc, gold rim light and serif headline.',
    width: 1080, height: 1350, swatches: ['#0a0806', '#d9a441', '#f5f1e7'],
    build: () => scene(1080, 1350, { kind: 'gradient', gradient: { type: 'radial', angle: 0, cx: 0.5, cy: 0.35, radius: 0.9, stops: [{ offset: 0, color: '#1c1408', opacity: 1 }, { offset: 1, color: '#050403', opacity: 1 }] } }, [
      createLight('#d9a441', { name: 'Gold Rim Light', x: 140, y: -500, width: 800, height: 800, intensity: 0.5, softness: 0.8, blendMode: 'screen' }),
      createShape('arc', { name: 'Arc', x: 190, y: 220, width: 700, height: 700, stroke: '#d9a441', strokeWidth: 1.5, arcAngle: 220, opacity: 0.7 }),
      createShape('circle', { name: 'Inner Circle', x: 415, y: 445, width: 250, height: 250, fill: null, stroke: '#d9a441', strokeWidth: 0.75, opacity: 0.5 }),
      createShape('line', { name: 'Vertical Line', x: 539, y: 940, width: 2, height: 120, stroke: '#d9a441', strokeWidth: 1 }),
      quoteText({ x: 120, y: 700, width: 840, height: 220, fontFamily: 'Playfair Display', fontSize: 64, fontWeight: 600, align: 'center', content: 'Great things take time.', fill: { kind: 'solid', color: '#f5f1e7' }, shadow: { enabled: true, x: 0, y: 10, blur: 40, color: '#000000', opacity: 0.7 } }),
      authorText({ x: 240, y: 1090, width: 600, align: 'center', content: 'QUOTECRAFT STUDIO' }),
      createParticles({ x: 0, y: 0, width: 1080, height: 1350, count: 70, opacity: 0.5, seed: 99 }),
      createShape('cornerFrame', { name: 'Corner Frame', x: 50, y: 50, width: 980, height: 1250, stroke: '#d9a441', strokeWidth: 1, spacing: 50, opacity: 0.6 }),
    ]),
  },
];
