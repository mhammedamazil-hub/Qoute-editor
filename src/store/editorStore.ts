import { create } from 'zustand';
import type { AnyElement, BackgroundFill, GroupElement } from '@/types/elements';
import type { CanvasSpec, SceneDocument } from '@/types/project';
import { uid } from '@/engine/ids';
import { createGroup } from '@/engine/elements/factory';

export const BACKGROUND_ID = '__background__';
const HISTORY_LIMIT = 80;
const COALESCE_MS = 700;

export type Tool = 'select' | 'hand';
export type RightTab = 'properties' | 'layers';
export type ModalId = 'none' | 'export' | 'settings' | 'templates' | 'projects' | 'ai' | 'newDesign' | 'canvasSize';
export type SaveStatus = 'idle' | 'saving' | 'saved' | 'unsaved';

export interface Guide {
  orientation: 'v' | 'h';
  position: number;
}

interface HistoryEntry {
  doc: SceneDocument;
  key: string | null;
  time: number;
}

export interface EditorState {
  doc: SceneDocument;
  assets: Record<string, string>;
  selectedIds: string[];
  editingGroupId: string | null;
  zoom: number;
  pan: { x: number; y: number };
  tool: Tool;
  past: HistoryEntry[];
  future: SceneDocument[];
  lastKey: string | null;
  lastKeyTime: number;
  guides: Guide[];
  rightTab: RightTab;
  modal: ModalId;
  mobileSheet: 'none' | 'properties' | 'layers' | 'add';
  previewMode: boolean;
  screen: 'start' | 'editor';
  projectId: string;
  projectName: string;
  saveStatus: SaveStatus;
  clipboard: AnyElement[];
  fontsVersion: number;

  // document
  loadDocument: (doc: SceneDocument, assets: Record<string, string>, meta?: { id?: string; name?: string }) => void;
  newDocument: (width: number, height: number, background?: BackgroundFill) => void;
  setCanvas: (patch: Partial<CanvasSpec>, key?: string) => void;
  setBackground: (bg: BackgroundFill, key?: string) => void;
  addElement: (el: AnyElement, select?: boolean) => void;
  addElements: (els: AnyElement[], select?: boolean) => void;
  updateElement: (id: string, patch: Partial<AnyElement>, key?: string | null) => void;
  updateElements: (patches: { id: string; patch: Partial<AnyElement> }[], key?: string | null) => void;
  replaceElements: (elements: AnyElement[], key?: string) => void;
  removeElements: (ids: string[]) => void;
  duplicateElements: (ids: string[]) => void;
  reorderElement: (id: string, toIndex: number) => void;
  moveLayer: (id: string, dir: 'up' | 'down' | 'top' | 'bottom') => void;
  groupSelected: () => void;
  ungroupSelected: () => void;
  alignSelected: (mode: 'left' | 'hcenter' | 'right' | 'top' | 'vcenter' | 'bottom' | 'canvas' | 'dist-h' | 'dist-v') => void;
  registerAsset: (dataUrl: string) => string;

  // selection
  select: (ids: string[], additive?: boolean) => void;
  clearSelection: () => void;
  setEditingGroup: (id: string | null) => void;

  // history
  undo: () => void;
  redo: () => void;

  // clipboard
  copy: () => void;
  paste: () => void;

  // view
  setZoom: (zoom: number, pan?: { x: number; y: number }) => void;
  setPan: (pan: { x: number; y: number }) => void;
  setTool: (tool: Tool) => void;
  setGuides: (guides: Guide[]) => void;
  setRightTab: (tab: RightTab) => void;
  setModal: (m: ModalId) => void;
  setMobileSheet: (s: EditorState['mobileSheet']) => void;
  setPreviewMode: (v: boolean) => void;
  setScreen: (s: 'start' | 'editor') => void;
  setProjectName: (name: string) => void;
  setSaveStatus: (s: SaveStatus) => void;
  bumpFonts: () => void;
}

export function blankDocument(width = 1080, height = 1350, background: BackgroundFill = { kind: 'solid', color: '#050608' }): SceneDocument {
  return { canvas: { width, height, background }, elements: [] };
}

function cloneDoc(doc: SceneDocument): SceneDocument {
  return typeof structuredClone === 'function' ? structuredClone(doc) : JSON.parse(JSON.stringify(doc));
}

/** Collect an element and all of its descendants (for groups). */
export function collectWithChildren(elements: AnyElement[], ids: string[]): string[] {
  const out = new Set<string>(ids);
  let changed = true;
  while (changed) {
    changed = false;
    for (const el of elements) {
      if (el.parentId && out.has(el.parentId) && !out.has(el.id)) {
        out.add(el.id);
        changed = true;
      }
    }
  }
  return [...out];
}

function elementBounds(el: AnyElement) {
  return { left: el.x, top: el.y, right: el.x + el.width, bottom: el.y + el.height, cx: el.x + el.width / 2, cy: el.y + el.height / 2 };
}

export const useEditorStore = create<EditorState>()((set, get) => {
  /** Push current doc into history (coalescing rapid updates with the same key). */
  const pushHistory = (key: string | null) => {
    const { doc, past, lastKey, lastKeyTime } = get();
    const now = Date.now();
    if (key && key === lastKey && now - lastKeyTime < COALESCE_MS) {
      set({ lastKeyTime: now });
      return;
    }
    const entry: HistoryEntry = { doc: cloneDoc(doc), key, time: now };
    const next = [...past, entry].slice(-HISTORY_LIMIT);
    set({ past: next, future: [], lastKey: key, lastKeyTime: now, saveStatus: 'unsaved' });
  };

  const commit = (mutate: (doc: SceneDocument) => SceneDocument, key: string | null = null) => {
    pushHistory(key);
    set((s) => ({ doc: mutate(s.doc), saveStatus: 'unsaved' }));
  };

  return {
    doc: blankDocument(),
    assets: {},
    selectedIds: [],
    editingGroupId: null,
    zoom: 0.5,
    pan: { x: 0, y: 0 },
    tool: 'select',
    past: [],
    future: [],
    lastKey: null,
    lastKeyTime: 0,
    guides: [],
    rightTab: 'properties',
    modal: 'none',
    mobileSheet: 'none',
    previewMode: false,
    screen: 'start',
    projectId: uid('proj'),
    projectName: 'Untitled design',
    saveStatus: 'idle',
    clipboard: [],
    fontsVersion: 0,

    loadDocument: (doc, assets, meta) =>
      set({
        doc: cloneDoc(doc),
        assets,
        selectedIds: [],
        editingGroupId: null,
        past: [],
        future: [],
        lastKey: null,
        projectId: meta?.id ?? uid('proj'),
        projectName: meta?.name ?? 'Untitled design',
        saveStatus: 'idle',
        screen: 'editor',
        modal: 'none',
        previewMode: false,
      }),

    newDocument: (width, height, background) =>
      set({
        doc: blankDocument(width, height, background),
        assets: {},
        selectedIds: [BACKGROUND_ID],
        editingGroupId: null,
        past: [],
        future: [],
        lastKey: null,
        projectId: uid('proj'),
        projectName: 'Untitled design',
        saveStatus: 'unsaved',
        screen: 'editor',
        modal: 'none',
        previewMode: false,
      }),

    setCanvas: (patch, key) => commit((d) => ({ ...d, canvas: { ...d.canvas, ...patch } }), key ?? 'canvas'),

    setBackground: (bg, key) => commit((d) => ({ ...d, canvas: { ...d.canvas, background: bg } }), key ?? 'background'),

    addElement: (el, select = true) => {
      commit((d) => ({ ...d, elements: [...d.elements, el] }));
      if (select) set({ selectedIds: [el.id], rightTab: 'properties' });
    },

    addElements: (els, select = true) => {
      commit((d) => ({ ...d, elements: [...d.elements, ...els] }));
      if (select) set({ selectedIds: els.map((e) => e.id) });
    },

    updateElement: (id, patch, key = null) =>
      commit((d) => ({ ...d, elements: d.elements.map((e) => (e.id === id ? ({ ...e, ...patch } as AnyElement) : e)) }), key),

    updateElements: (patches, key = null) => {
      const map = new Map(patches.map((p) => [p.id, p.patch]));
      commit((d) => ({ ...d, elements: d.elements.map((e) => (map.has(e.id) ? ({ ...e, ...map.get(e.id) } as AnyElement) : e)) }), key);
    },

    replaceElements: (elements, key) => {
      commit((d) => ({ ...d, elements }), key ?? null);
      set({ selectedIds: [], editingGroupId: null });
    },

    removeElements: (ids) => {
      const all = new Set(collectWithChildren(get().doc.elements, ids));
      commit((d) => ({ ...d, elements: d.elements.filter((e) => !all.has(e.id)) }));
      set((s) => ({ selectedIds: s.selectedIds.filter((i) => !all.has(i)), editingGroupId: s.editingGroupId && all.has(s.editingGroupId) ? null : s.editingGroupId }));
    },

    duplicateElements: (ids) => {
      const { doc } = get();
      const all = collectWithChildren(doc.elements, ids);
      const idMap = new Map(all.map((id) => [id, uid(doc.elements.find((e) => e.id === id)?.type ?? 'el')]));
      const copies: AnyElement[] = doc.elements
        .filter((e) => all.includes(e.id))
        .map((e) => ({
          ...cloneDoc({ canvas: doc.canvas, elements: [e] }).elements[0],
          id: idMap.get(e.id)!,
          parentId: e.parentId && idMap.has(e.parentId) ? idMap.get(e.parentId)! : e.parentId,
          x: e.parentId && idMap.has(e.parentId) ? e.x : e.x + 24,
          y: e.parentId && idMap.has(e.parentId) ? e.y : e.y + 24,
          name: ids.includes(e.id) ? `${e.name} copy` : e.name,
        }));
      commit((d) => ({ ...d, elements: [...d.elements, ...copies] }));
      set({ selectedIds: ids.map((id) => idMap.get(id)!) });
    },

    reorderElement: (id, toIndex) =>
      commit((d) => {
        const els = [...d.elements];
        const from = els.findIndex((e) => e.id === id);
        if (from < 0) return d;
        const [item] = els.splice(from, 1);
        els.splice(Math.max(0, Math.min(els.length, toIndex)), 0, item);
        return { ...d, elements: els };
      }),

    moveLayer: (id, dir) => {
      const els = get().doc.elements;
      const idx = els.findIndex((e) => e.id === id);
      if (idx < 0) return;
      const target = dir === 'up' ? idx + 1 : dir === 'down' ? idx - 1 : dir === 'top' ? els.length - 1 : 0;
      get().reorderElement(id, target);
    },

    groupSelected: () => {
      const { doc, selectedIds } = get();
      const members = doc.elements.filter((e) => selectedIds.includes(e.id) && !e.parentId && e.type !== 'group');
      if (members.length < 2) return;
      const left = Math.min(...members.map((m) => m.x));
      const top = Math.min(...members.map((m) => m.y));
      const right = Math.max(...members.map((m) => m.x + m.width));
      const bottom = Math.max(...members.map((m) => m.y + m.height));
      const group = createGroup({ x: left, y: top, width: right - left, height: bottom - top, name: 'Group' });
      const memberIds = new Set(members.map((m) => m.id));
      commit((d) => {
        const firstIdx = d.elements.findIndex((e) => memberIds.has(e.id));
        const rest = d.elements.filter((e) => !memberIds.has(e.id));
        const moved = d.elements.filter((e) => memberIds.has(e.id)).map((e) => ({ ...e, parentId: group.id, x: e.x - left, y: e.y - top }) as AnyElement);
        rest.splice(firstIdx, 0, group, ...moved);
        return { ...d, elements: rest };
      });
      set({ selectedIds: [group.id], editingGroupId: null });
    },

    ungroupSelected: () => {
      const { doc, selectedIds } = get();
      const groups = doc.elements.filter((e): e is GroupElement => e.type === 'group' && selectedIds.includes(e.id));
      if (!groups.length) return;
      const freed: string[] = [];
      commit((d) => {
        let els = d.elements;
        for (const g of groups) {
          const rad = (g.rotation * Math.PI) / 180;
          const cos = Math.cos(rad), sin = Math.sin(rad);
          els = els
            .filter((e) => e.id !== g.id)
            .map((e) => {
              if (e.parentId !== g.id) return e;
              const lx = e.x * g.scaleX, ly = e.y * g.scaleY;
              freed.push(e.id);
              return {
                ...e,
                parentId: null,
                x: g.x + lx * cos - ly * sin,
                y: g.y + lx * sin + ly * cos,
                width: e.width * g.scaleX,
                height: e.height * g.scaleY,
                rotation: e.rotation + g.rotation,
              } as AnyElement;
            });
        }
        return { ...d, elements: els };
      });
      set({ selectedIds: freed, editingGroupId: null });
    },

    alignSelected: (mode) => {
      const { doc, selectedIds } = get();
      const sel = doc.elements.filter((e) => selectedIds.includes(e.id) && !e.parentId);
      if (!sel.length) return;
      const cw = doc.canvas.width, chh = doc.canvas.height;
      const single = sel.length === 1 || mode === 'canvas';
      const boundsList = sel.map(elementBounds);
      const box = single
        ? { left: 0, top: 0, right: cw, bottom: chh, cx: cw / 2, cy: chh / 2 }
        : {
            left: Math.min(...boundsList.map((b) => b.left)),
            top: Math.min(...boundsList.map((b) => b.top)),
            right: Math.max(...boundsList.map((b) => b.right)),
            bottom: Math.max(...boundsList.map((b) => b.bottom)),
            cx: 0,
            cy: 0,
          };
      box.cx = (box.left + box.right) / 2;
      box.cy = (box.top + box.bottom) / 2;
      const patches: { id: string; patch: Partial<AnyElement> }[] = [];
      if (mode === 'dist-h' || mode === 'dist-v') {
        if (sel.length < 3) return;
        const sorted = [...sel].sort((a, b) => (mode === 'dist-h' ? a.x - b.x : a.y - b.y));
        const total = mode === 'dist-h' ? box.right - box.left : box.bottom - box.top;
        const sizes = sorted.reduce((s, e) => s + (mode === 'dist-h' ? e.width : e.height), 0);
        const gap = (total - sizes) / (sorted.length - 1);
        let cursor = mode === 'dist-h' ? box.left : box.top;
        for (const e of sorted) {
          patches.push({ id: e.id, patch: mode === 'dist-h' ? { x: cursor } : { y: cursor } });
          cursor += (mode === 'dist-h' ? e.width : e.height) + gap;
        }
      } else {
        for (const e of sel) {
          const p: Partial<AnyElement> = {};
          if (mode === 'left') p.x = box.left;
          if (mode === 'hcenter' || mode === 'canvas') p.x = box.cx - e.width / 2;
          if (mode === 'right') p.x = box.right - e.width;
          if (mode === 'top') p.y = box.top;
          if (mode === 'vcenter' || mode === 'canvas') p.y = box.cy - e.height / 2;
          if (mode === 'bottom') p.y = box.bottom - e.height;
          patches.push({ id: e.id, patch: p });
        }
      }
      get().updateElements(patches);
    },

    registerAsset: (dataUrl) => {
      const id = uid('asset');
      set((s) => ({ assets: { ...s.assets, [id]: dataUrl } }));
      return id;
    },

    select: (ids, additive = false) =>
      set((s) => {
        if (!additive) return { selectedIds: ids };
        const next = new Set(s.selectedIds.filter((i) => i !== BACKGROUND_ID));
        for (const id of ids) {
          if (next.has(id)) next.delete(id);
          else next.add(id);
        }
        return { selectedIds: [...next] };
      }),

    clearSelection: () => set({ selectedIds: [] }),
    setEditingGroup: (id) => set({ editingGroupId: id }),

    undo: () => {
      const { past, doc, future } = get();
      if (!past.length) return;
      const prev = past[past.length - 1];
      set({ past: past.slice(0, -1), future: [cloneDoc(doc), ...future].slice(0, HISTORY_LIMIT), doc: prev.doc, lastKey: null, saveStatus: 'unsaved' });
      set((s) => ({ selectedIds: s.selectedIds.filter((id) => id === BACKGROUND_ID || prev.doc.elements.some((e) => e.id === id)) }));
    },

    redo: () => {
      const { past, doc, future } = get();
      if (!future.length) return;
      const [next, ...rest] = future;
      set({ past: [...past, { doc: cloneDoc(doc), key: null, time: Date.now() }], future: rest, doc: next, lastKey: null, saveStatus: 'unsaved' });
      set((s) => ({ selectedIds: s.selectedIds.filter((id) => id === BACKGROUND_ID || next.elements.some((e) => e.id === id)) }));
    },

    copy: () => {
      const { doc, selectedIds } = get();
      const all = collectWithChildren(doc.elements, selectedIds.filter((i) => i !== BACKGROUND_ID));
      set({ clipboard: cloneDoc({ canvas: doc.canvas, elements: doc.elements.filter((e) => all.includes(e.id)) }).elements });
    },

    paste: () => {
      const { clipboard } = get();
      if (!clipboard.length) return;
      const idMap = new Map(clipboard.map((e) => [e.id, uid(e.type)]));
      const pasted = clipboard.map(
        (e) =>
          ({
            ...e,
            id: idMap.get(e.id)!,
            parentId: e.parentId && idMap.has(e.parentId) ? idMap.get(e.parentId)! : null,
            x: e.parentId && idMap.has(e.parentId) ? e.x : e.x + 32,
            y: e.parentId && idMap.has(e.parentId) ? e.y : e.y + 32,
          }) as AnyElement,
      );
      commit((d) => ({ ...d, elements: [...d.elements, ...pasted] }));
      set({ selectedIds: pasted.filter((e) => !e.parentId).map((e) => e.id) });
    },

    setZoom: (zoom, pan) => set((s) => ({ zoom: Math.min(8, Math.max(0.05, zoom)), pan: pan ?? s.pan })),
    setPan: (pan) => set({ pan }),
    setTool: (tool) => set({ tool }),
    setGuides: (guides) => set({ guides }),
    setRightTab: (rightTab) => set({ rightTab }),
    setModal: (modal) => set({ modal }),
    setMobileSheet: (mobileSheet) => set({ mobileSheet }),
    setPreviewMode: (previewMode) => set({ previewMode, selectedIds: previewMode ? [] : get().selectedIds }),
    setScreen: (screen) => set({ screen }),
    setProjectName: (projectName) => set({ projectName, saveStatus: 'unsaved' }),
    setSaveStatus: (saveStatus) => set({ saveStatus }),
    bumpFonts: () => set((s) => ({ fontsVersion: s.fontsVersion + 1 })),
  };
});

/* ---------- selectors ---------- */

export const selectSelectedElements = (s: EditorState) => s.doc.elements.filter((e) => s.selectedIds.includes(e.id));
export const selectPrimaryElement = (s: EditorState): AnyElement | undefined => {
  const id = s.selectedIds[0];
  return id ? s.doc.elements.find((e) => e.id === id) : undefined;
};
export const selectCanUndo = (s: EditorState) => s.past.length > 0;
export const selectCanRedo = (s: EditorState) => s.future.length > 0;
