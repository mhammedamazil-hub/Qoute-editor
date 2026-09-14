import { create } from 'zustand';
import { get as idbGet, set as idbSet, del as idbDel, createStore } from 'idb-keyval';
import type { ProjectFile, ProjectSummary } from '@/types/project';
import { serializeProject, deserializeProject } from '@/engine/serialization/project';
import { useEditorStore } from './editorStore';
import { useSettingsStore } from './settingsStore';
import { uid } from '@/engine/ids';

const hasIdb = typeof indexedDB !== 'undefined';

/** False in private-browsing modes without IndexedDB — the UI tells the user. */
export const storageAvailable = hasIdb;
const store = hasIdb ? createStore('quotecraft', 'projects') : undefined;

/**
 * IndexedDB is unavailable in some private-browsing modes and in embedded
 * webviews. Every access goes through these helpers so the editor still runs
 * (without persistence) instead of throwing.
 */
async function safeGet<T>(key: string): Promise<T | undefined> {
  if (!hasIdb) return undefined;
  try {
    return await idbGet<T>(key, store);
  } catch {
    return undefined;
  }
}

async function safeSet(key: string, value: unknown): Promise<boolean> {
  if (!hasIdb) return false;
  try {
    await idbSet(key, value, store);
    return true;
  } catch {
    return false;
  }
}

async function safeDel(key: string): Promise<void> {
  if (!hasIdb) return;
  try {
    await idbDel(key, store);
  } catch {
    /* ignore */
  }
}
const INDEX_KEY = 'index';
const LAST_KEY = 'lastProjectId';

interface ProjectState {
  projects: ProjectSummary[];
  lastProjectId: string | null;
  ready: boolean;
  init: () => Promise<void>;
  saveCurrent: (opts?: { silent?: boolean }) => Promise<void>;
  loadProject: (id: string) => Promise<boolean>;
  deleteProject: (id: string) => Promise<void>;
  duplicateProject: (id: string) => Promise<void>;
  renameProject: (id: string, name: string) => Promise<void>;
  importProjectFile: (file: File) => Promise<boolean>;
  exportProjectFile: () => Promise<ProjectFile>;
}

async function readIndex(): Promise<ProjectSummary[]> {
  try {
    return ((await safeGet<ProjectSummary[]>(INDEX_KEY)) ?? []).sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

async function writeIndex(list: ProjectSummary[]) {
  try {
    await safeSet(INDEX_KEY, list);
  } catch {
    /* ignore */
  }
}

export const useProjectStore = create<ProjectState>()((set, get) => ({
  projects: [],
  lastProjectId: null,
  ready: false,

  init: async () => {
    const [projects, last] = await Promise.all([readIndex(), safeGet<string>(LAST_KEY)]);
    set({ projects, lastProjectId: last ?? null, ready: true });
  },

  saveCurrent: async () => {
    const ed = useEditorStore.getState();
    ed.setSaveStatus('saving');
    try {
      const existing = get().projects.find((p) => p.id === ed.projectId);
      const file = serializeProject(ed.doc, ed.assets, { id: ed.projectId, name: ed.projectName, createdAt: existing?.updatedAt });
      await safeSet(`project:${file.id}`, file);
      const summary: ProjectSummary = {
        id: file.id,
        name: file.name,
        updatedAt: file.metadata.updatedAt,
        width: file.canvas.width,
        height: file.canvas.height,
        elementCount: file.elements.length,
      };
      const list = [summary, ...get().projects.filter((p) => p.id !== file.id)];
      await writeIndex(list);
      await safeSet(LAST_KEY, file.id);
      set({ projects: list, lastProjectId: file.id });
      ed.setSaveStatus('saved');
    } catch {
      ed.setSaveStatus('unsaved');
    }
  },

  loadProject: async (id) => {
    try {
      const raw = await safeGet<ProjectFile>(`project:${id}`);
      if (!raw) return false;
      const file = deserializeProject(raw);
      useEditorStore.getState().loadDocument({ canvas: file.canvas, elements: file.elements }, file.assets, { id: file.id, name: file.name });
      await safeSet(LAST_KEY, id);
      set({ lastProjectId: id });
      return true;
    } catch {
      return false;
    }
  },

  deleteProject: async (id) => {
    await safeDel(`project:${id}`);
    const list = get().projects.filter((p) => p.id !== id);
    await writeIndex(list);
    set({ projects: list, lastProjectId: get().lastProjectId === id ? null : get().lastProjectId });
  },

  duplicateProject: async (id) => {
    const raw = await safeGet<ProjectFile>(`project:${id}`).catch(() => undefined);
    if (!raw) return;
    const copy: ProjectFile = { ...raw, id: uid('proj'), name: `${raw.name} copy`, metadata: { ...raw.metadata, updatedAt: Date.now() } };
    await safeSet(`project:${copy.id}`, copy);
    const summary: ProjectSummary = { id: copy.id, name: copy.name, updatedAt: copy.metadata.updatedAt, width: copy.canvas.width, height: copy.canvas.height, elementCount: copy.elements.length };
    const list = [summary, ...get().projects];
    await writeIndex(list);
    set({ projects: list });
  },

  renameProject: async (id, name) => {
    const raw = await safeGet<ProjectFile>(`project:${id}`).catch(() => undefined);
    if (raw) await safeSet(`project:${id}`, { ...raw, name });
    const list = get().projects.map((p) => (p.id === id ? { ...p, name } : p));
    await writeIndex(list);
    set({ projects: list });
    const ed = useEditorStore.getState();
    if (ed.projectId === id) useEditorStore.setState({ projectName: name });
  },

  importProjectFile: async (file) => {
    try {
      const text = await file.text();
      const parsed = deserializeProject(JSON.parse(text));
      useEditorStore.getState().loadDocument({ canvas: parsed.canvas, elements: parsed.elements }, parsed.assets, { id: uid('proj'), name: parsed.name });
      return true;
    } catch {
      return false;
    }
  },

  exportProjectFile: async () => {
    const ed = useEditorStore.getState();
    return serializeProject(ed.doc, ed.assets, { id: ed.projectId, name: ed.projectName });
  },
}));

/** Autosave: debounced subscription to document changes. */
let timer: ReturnType<typeof setTimeout> | null = null;
useEditorStore.subscribe((state, prev) => {
  if (state.screen !== 'editor') return;
  if (state.doc === prev.doc && state.projectName === prev.projectName) return;
  if (!useSettingsStore.getState().autosave) return;
  if (timer) clearTimeout(timer);
  const delay = Math.max(400, useSettingsStore.getState().autosaveDelayMs || 1500);
  timer = setTimeout(() => void useProjectStore.getState().saveCurrent(), delay);
});
