import { create } from 'zustand';
import type { AIStatus } from '@/types/ai';
import { DEFAULT_MODEL, migrateModelId } from '@/ai/gemini/models';

const SETTINGS_KEY = 'quotecraft.settings.v1';
const KEY_STORAGE = 'quotecraft.gemini.key';

export type ThemeChoice = 'dark' | 'light' | 'system';
export type Density = 'compact' | 'comfortable';

export interface SettingsState {
  // General
  autosave: boolean;
  autosaveDelayMs: number;
  confirmDelete: boolean;
  // Editor
  snapping: boolean;
  showGuides: boolean;
  handleSize: number;
  // Appearance
  theme: ThemeChoice;
  accent: string;
  uiDensity: Density;
  canvasBackdrop: 'dark' | 'gray' | 'black';
  reduceMotion: boolean;
  // Export
  defaultFormat: 'png' | 'jpeg' | 'webp';
  defaultQuality: number;
  defaultScale: number;
  // AI (never a default key — the user supplies their own at runtime)
  geminiKey: string;
  geminiKeyPersisted: boolean;
  geminiModel: string;
  /** Set when a stored model id was retired and auto-migrated. */
  modelMigratedFrom: string | null;
  aiAutoApply: boolean;
  aiShowToolActivity: boolean;
  aiStatus: AIStatus;
  /** Models discovered on the user's key (cache for the settings picker). */
  discoveredModels: string[];
  discoveredAt: number | null;
  recentColors: string[];
  savedColors: string[];

  update: (patch: Partial<SettingsState>) => void;
  setGeminiKey: (key: string, persist: boolean) => void;
  removeGeminiKey: () => void;
  setAIStatus: (s: AIStatus) => void;
  setDiscoveredModels: (models: string[]) => void;
  pushRecentColor: (hex: string) => void;
  toggleSavedColor: (hex: string) => void;
  resetAll: () => void;
}

type Persisted = Pick<
  SettingsState,
  | 'autosave'
  | 'autosaveDelayMs'
  | 'confirmDelete'
  | 'snapping'
  | 'showGuides'
  | 'handleSize'
  | 'theme'
  | 'accent'
  | 'uiDensity'
  | 'canvasBackdrop'
  | 'reduceMotion'
  | 'defaultFormat'
  | 'defaultQuality'
  | 'defaultScale'
  | 'geminiModel'
  | 'aiAutoApply'
  | 'aiShowToolActivity'
  | 'recentColors'
  | 'savedColors'
>;

function readStorage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function loadKey(): string {
  try {
    return localStorage.getItem(KEY_STORAGE) ?? '';
  } catch {
    return '';
  }
}

const persistedKey = loadKey();
const stored = readStorage<Partial<Persisted>>(SETTINGS_KEY, {});
const migrated = migrateModelId(stored.geminiModel ?? DEFAULT_MODEL);

const DEFAULTS = {
  autosave: true,
  autosaveDelayMs: 1200,
  confirmDelete: false,
  snapping: true,
  showGuides: true,
  handleSize: 9,
  theme: 'dark' as ThemeChoice,
  accent: '#d9a441',
  uiDensity: 'comfortable' as Density,
  canvasBackdrop: 'dark' as const,
  reduceMotion: false,
  defaultFormat: 'png' as const,
  defaultQuality: 0.92,
  defaultScale: 1,
};

export const useSettingsStore = create<SettingsState>()((set, get) => {
  const persist = () => {
    const s = get();
    const data: Persisted = {
      autosave: s.autosave,
      autosaveDelayMs: s.autosaveDelayMs,
      confirmDelete: s.confirmDelete,
      snapping: s.snapping,
      showGuides: s.showGuides,
      handleSize: s.handleSize,
      theme: s.theme,
      accent: s.accent,
      uiDensity: s.uiDensity,
      canvasBackdrop: s.canvasBackdrop,
      reduceMotion: s.reduceMotion,
      defaultFormat: s.defaultFormat,
      defaultQuality: s.defaultQuality,
      defaultScale: s.defaultScale,
      geminiModel: s.geminiModel,
      aiAutoApply: s.aiAutoApply,
      aiShowToolActivity: s.aiShowToolActivity,
      recentColors: s.recentColors,
      savedColors: s.savedColors,
    };
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(data));
    } catch {
      /* storage unavailable (private mode / file://) */
    }
  };

  return {
    ...DEFAULTS,
    geminiKey: persistedKey,
    geminiKeyPersisted: !!persistedKey,
    geminiModel: migrated.model,
    modelMigratedFrom: migrated.replaced ?? null,
    aiAutoApply: true,
    aiShowToolActivity: true,
    aiStatus: persistedKey ? 'configured' : 'not-configured',
    discoveredModels: [],
    discoveredAt: null,
    recentColors: [],
    savedColors: ['#050608', '#d9a441', '#f5f1e7', '#12a37f', '#3a7bff', '#e879f9'],

    update: (patch) => {
      set(patch);
      persist();
    },

    setGeminiKey: (key, persistKey) => {
      const trimmed = key.trim();
      set({ geminiKey: trimmed, geminiKeyPersisted: persistKey && !!trimmed, aiStatus: trimmed ? 'configured' : 'not-configured' });
      try {
        if (persistKey && trimmed) localStorage.setItem(KEY_STORAGE, trimmed);
        else localStorage.removeItem(KEY_STORAGE);
      } catch {
        /* ignore */
      }
    },

    removeGeminiKey: () => {
      set({ geminiKey: '', geminiKeyPersisted: false, aiStatus: 'not-configured', discoveredModels: [], discoveredAt: null });
      try {
        localStorage.removeItem(KEY_STORAGE);
      } catch {
        /* ignore */
      }
    },

    setAIStatus: (aiStatus) => set({ aiStatus }),

    setDiscoveredModels: (models) => set({ discoveredModels: models, discoveredAt: Date.now() }),

    pushRecentColor: (hex) => {
      const next = [hex, ...get().recentColors.filter((c) => c !== hex)].slice(0, 12);
      set({ recentColors: next });
      persist();
    },

    toggleSavedColor: (hex) => {
      const cur = get().savedColors;
      set({ savedColors: cur.includes(hex) ? cur.filter((c) => c !== hex) : [...cur, hex].slice(-24) });
      persist();
    },

    resetAll: () => {
      set({ ...DEFAULTS, confirmDelete: false });
      persist();
    },
  };
});
