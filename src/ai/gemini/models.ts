/**
 * Gemini model catalog.
 *
 * Two jobs:
 *  1. Ship a current, curated list so the app never hard-codes a retired model
 *     (Gemini 2.5 Flash was closed down for new API keys — projects that pinned it
 *     started failing with 404 NOT_FOUND).
 *  2. Heal stored settings: any key that still points at a closed/legacy model is
 *     transparently migrated to the newest Flash model.
 *
 * `LIVE` discovery (GET /v1beta/models) is still used at runtime so the list stays
 * correct even if Google ships a newer model after this build.
 */

export interface GeminiModel {
  /** API model id, e.g. "gemini-3.8-flash". */
  id: string;
  /** Human label shown in the picker. */
  label: string;
  /** Coarse family used for grouping + fallback selection. */
  family: 'flash' | 'pro' | 'lite' | 'legacy';
  /** Higher = newer/more capable. Used to pick a fallback automatically. */
  rank: number;
  /** Short description shown under the picker. */
  blurb: string;
  /** Suggested default for the assistant + design studio. */
  recommended?: boolean;
}

/**
 * Curated catalog — newest first. `gemini-3.8-flash` is the current stable Flash
 * (GA 2026-09-02) and the default for QuoteCraft.
 */
export const GEMINI_MODELS: GeminiModel[] = [
  {
    id: 'gemini-3.8-flash',
    label: 'Gemini 3.8 Flash',
    family: 'flash',
    rank: 380,
    blurb: 'Latest stable Flash. Best quality-per-latency for design + agent work. Default.',
    recommended: true,
  },
  {
    id: 'gemini-3.7-flash',
    label: 'Gemini 3.7 Flash',
    family: 'flash',
    rank: 370,
    blurb: 'Previous Flash release. Solid, slightly cheaper fallback.',
  },
  {
    id: 'gemini-3.6-flash',
    label: 'Gemini 3.6 Flash',
    family: 'flash',
    rank: 360,
    blurb: 'Older Flash release. Use only if 3.7/3.8 are unavailable on your key.',
  },
  {
    id: 'gemini-3.5-flash-lite',
    label: 'Gemini 3.5 Flash-Lite',
    family: 'lite',
    rank: 355,
    blurb: 'Cheapest + fastest. Great for short edits, weaker at composition.',
  },
  {
    id: 'gemini-3.5-flash',
    label: 'Gemini 3.5 Flash',
    family: 'flash',
    rank: 350,
    blurb: 'High-volume Flash. Good fallback when newer models are rate limited.',
  },
  {
    id: 'gemini-3.1-pro',
    label: 'Gemini 3.1 Pro',
    family: 'pro',
    rank: 331,
    blurb: 'Deepest reasoning + best multimodal understanding. Slowest, most expensive.',
  },
  {
    id: 'gemini-3.1-flash-lite',
    label: 'Gemini 3.1 Flash-Lite',
    family: 'lite',
    rank: 331,
    blurb: 'Low-cost, low-latency classification/translation style tasks.',
  },
  {
    id: 'gemini-3-flash-preview',
    label: 'Gemini 3 Flash (preview)',
    family: 'legacy',
    rank: 300,
    blurb: 'Preview build kept for compatibility — prefer 3.8 Flash.',
  },
  {
    id: 'gemini-flash-latest',
    label: 'Gemini Flash (latest alias)',
    family: 'legacy',
    rank: 290,
    blurb: 'Rolling alias that always points at the newest Flash. Convenient, less predictable.',
  },
  {
    id: 'gemini-2.5-flash',
    label: 'Gemini 2.5 Flash (retired for new keys)',
    family: 'legacy',
    rank: 250,
    blurb: 'Closed to new API keys. Kept only so existing keys can still select it.',
  },
];

/** Model ids that are retired or unsafe as a default. */
export const RETIRED_MODEL_IDS = new Set<string>([
  'gemini-2.5-flash',
  'gemini-2.5-flash-lite',
  'gemini-2.5-pro',
  'gemini-2.0-flash',
  'gemini-2.0-flash-001',
  'gemini-2.0-flash-lite',
  'gemini-2.0-flash-lite-001',
  'gemini-1.5-flash',
  'gemini-1.5-flash-8b',
  'gemini-1.5-pro',
  'gemini-pro',
  'gemini-1.0-pro',
]);

/** Current default. */
export const DEFAULT_MODEL = 'gemini-3.8-flash';

/** Ordered fallbacks used when the selected model 404s on this key. */
export const FALLBACK_MODELS = [
  'gemini-3.8-flash',
  'gemini-3.7-flash',
  'gemini-3.6-flash',
  'gemini-3.5-flash',
  'gemini-flash-latest',
  'gemini-3.1-pro',
  'gemini-2.5-flash',
];

export function findModel(id: string | undefined | null): GeminiModel | undefined {
  if (!id) return undefined;
  return GEMINI_MODELS.find((m) => m.id === id);
}

export function modelLabel(id: string): string {
  return findModel(id)?.label ?? id;
}

export function modelRank(id: string): number {
  const known = findModel(id);
  if (known) return known.rank;
  // Discovered-but-unknown ids: derive a rank from the version number so that
  // a brand new "gemini-4.2-flash" automatically outranks our curated list.
  const m = /gemini-(\d+)(?:\.(\d+))?/.exec(id);
  if (!m) return 0;
  const major = Number(m[1]);
  const minor = Number(m[2] ?? 0);
  const familyBonus = /flash-lite/.test(id) ? 2 : /flash/.test(id) ? 0 : /pro/.test(id) ? -2 : 0;
  return major * 100 + minor + familyBonus;
}

/**
 * Migrates a stored model id. Returns the model to actually use plus the id that
 * was replaced (so the UI can tell the user "Gemini 2.5 Flash is retired — using
 * Gemini 3.8 Flash").
 */
export function migrateModelId(stored?: string | null): { model: string; replaced?: string } {
  if (!stored) return { model: DEFAULT_MODEL };
  if (RETIRED_MODEL_IDS.has(stored)) return { model: DEFAULT_MODEL, replaced: stored };
  return { model: stored };
}

/** Picks the newest usable model from a live list returned by the API. */
export function pickBestAvailableModel(availableIds: string[]): string | undefined {
  if (!availableIds.length) return undefined;
  const usable = availableIds.filter((id) => !/embedding|imagen|veo|aqa|learnlm|tts|image/.test(id));
  const pool = usable.length ? usable : availableIds;
  return [...pool].sort((a, b) => modelRank(b) - modelRank(a))[0];
}

/** Live models merged with the curated catalog for display. */
export function mergeWithLiveModels(availableIds: string[]): GeminiModel[] {
  const seen = new Set(GEMINI_MODELS.map((m) => m.id));
  const extra: GeminiModel[] = availableIds
    .filter((id) => !seen.has(id) && !/embedding|imagen|veo|aqa|learnlm|tts|image/.test(id))
    .map((id): GeminiModel => ({
      id,
      label: id.replace(/^models\//, ''),
      family: /flash-lite/.test(id) ? 'lite' : /pro/.test(id) ? 'pro' : 'flash',
      rank: modelRank(id),
      blurb: 'Detected on your API key.',
    }))
    .sort((a, b) => b.rank - a.rank);
  return [...extra, ...GEMINI_MODELS].sort((a, b) => b.rank - a.rank);
}
