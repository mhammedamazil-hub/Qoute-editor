export interface FontDef {
  family: string;
  category: 'serif' | 'sans' | 'display';
  weights: number[];
}

export const FONTS: FontDef[] = [
  { family: 'Inter', category: 'sans', weights: [300, 400, 500, 600, 700, 800] },
  { family: 'Poppins', category: 'sans', weights: [300, 400, 500, 600, 700] },
  { family: 'Montserrat', category: 'sans', weights: [300, 400, 500, 600, 700, 800] },
  { family: 'Manrope', category: 'sans', weights: [300, 400, 500, 600, 700, 800] },
  { family: 'Space Grotesk', category: 'sans', weights: [300, 400, 500, 600, 700] },
  { family: 'Playfair Display', category: 'serif', weights: [400, 500, 600, 700, 800] },
  { family: 'Cormorant Garamond', category: 'serif', weights: [300, 400, 500, 600, 700] },
  { family: 'Libre Baskerville', category: 'serif', weights: [400, 700] },
  { family: 'DM Serif Display', category: 'serif', weights: [400] },
  { family: 'Bebas Neue', category: 'display', weights: [400] },
];

export const FONT_FAMILIES = FONTS.map((f) => f.family);

export function isAllowedFont(family: string): boolean {
  return FONT_FAMILIES.includes(family);
}

export function nearestWeight(family: string, weight: number): number {
  const def = FONTS.find((f) => f.family === family);
  if (!def) return weight;
  return def.weights.reduce((best, w) => (Math.abs(w - weight) < Math.abs(best - weight) ? w : best), def.weights[0]);
}

/** Resolves when the fonts are usable by canvas; safe on browsers without the Font Loading API. */
export async function waitForFonts(): Promise<void> {
  if (typeof document === 'undefined' || !('fonts' in document)) return;
  try {
    const loads: Promise<unknown>[] = [];
    for (const f of FONTS) {
      for (const w of f.weights) {
        loads.push(document.fonts.load(`${w} 24px "${f.family}"`).catch(() => []));
        loads.push(document.fonts.load(`italic ${w} 24px "${f.family}"`).catch(() => []));
      }
    }
    await Promise.all(loads);
    await document.fonts.ready;
  } catch {
    /* ignore */
  }
}

/** Calls `cb` whenever additional font faces finish loading (e.g. weights requested lazily). */
export function onFontsLoaded(cb: () => void): () => void {
  if (typeof document === 'undefined' || !('fonts' in document)) return () => undefined;
  const handler = () => cb();
  document.fonts.addEventListener('loadingdone', handler);
  return () => document.fonts.removeEventListener('loadingdone', handler);
}
