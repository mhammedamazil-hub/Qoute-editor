import type { ProjectFile, SceneDocument } from '@/types/project';
import type { AnyElement } from '@/types/elements';
import { baseElement } from '@/engine/elements/factory';

export const PROJECT_VERSION = 1 as const;

export function serializeProject(doc: SceneDocument, assets: Record<string, string>, meta: { id: string; name: string; createdAt?: number }): ProjectFile {
  // Only keep assets that are referenced by the scene.
  const used = new Set<string>();
  for (const el of doc.elements) if (el.type === 'image') used.add(el.assetId);
  if (doc.canvas.background.kind === 'image') used.add(doc.canvas.background.assetId);
  const trimmed: Record<string, string> = {};
  for (const id of used) if (assets[id]) trimmed[id] = assets[id];
  return {
    version: PROJECT_VERSION,
    id: meta.id,
    name: meta.name,
    canvas: doc.canvas,
    elements: doc.elements,
    assets: trimmed,
    metadata: { createdAt: meta.createdAt ?? Date.now(), updatedAt: Date.now(), app: 'quotecraft' },
  };
}

/** Fills missing fields so older/partial files load safely. */
export function normalizeElement(raw: Partial<AnyElement> & { type: AnyElement['type'] }): AnyElement {
  const base = baseElement(raw.type, raw.name ?? raw.type);
  return { ...base, ...raw, shadow: { ...base.shadow, ...(raw.shadow ?? {}) }, glow: { ...base.glow, ...(raw.glow ?? {}) } } as AnyElement;
}

export function deserializeProject(input: unknown): ProjectFile {
  if (!input || typeof input !== 'object') throw new Error('Invalid project file');
  const p = input as Partial<ProjectFile>;
  if (!p.canvas || !Array.isArray(p.elements)) throw new Error('Project file is missing canvas or elements');
  const elements = p.elements
    .filter((e): e is AnyElement => !!e && typeof e === 'object' && typeof (e as AnyElement).type === 'string')
    .map((e) => normalizeElement(e));
  return {
    version: 1,
    id: p.id ?? `proj-${Date.now().toString(36)}`,
    name: p.name ?? 'Imported design',
    canvas: {
      width: Math.max(64, Math.min(8000, Number(p.canvas.width) || 1080)),
      height: Math.max(64, Math.min(8000, Number(p.canvas.height) || 1350)),
      background: p.canvas.background ?? { kind: 'solid', color: '#050608' },
    },
    elements,
    assets: p.assets && typeof p.assets === 'object' ? p.assets : {},
    metadata: { createdAt: p.metadata?.createdAt ?? Date.now(), updatedAt: Date.now(), app: 'quotecraft' },
  };
}

export function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
