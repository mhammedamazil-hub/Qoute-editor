import { useRef, useState } from 'react';
import { Copy, FolderOpen, Pencil, Trash2, Upload } from 'lucide-react';
import { TEMPLATES, type TemplateDef } from './templates';
import { CANVAS_PRESETS } from '@/types/project';
import { useEditorStore } from '@/store/editorStore';
import { useProjectStore } from '@/store/projectStore';
import { Modal, NumberField } from '@/components/ui';
import { cn } from '@/utils/cn';

/** Tiny CSS preview that mirrors the template palette (the real template is scene data, not this thumbnail). */
function TemplateThumb({ t }: { t: TemplateDef }) {
  const [bg, accent, second] = t.swatches;
  return (
    <div className="relative aspect-[4/5] w-full overflow-hidden rounded-md border border-line" style={{ background: bg }}>
      <div className="absolute -right-6 -top-6 h-20 w-20 rounded-full opacity-60 blur-xl" style={{ background: accent }} />
      {second && <div className="absolute -bottom-8 -left-6 h-20 w-20 rounded-full opacity-40 blur-xl" style={{ background: second }} />}
      <div className="absolute left-3 top-[38%] h-[2px] w-8" style={{ background: accent }} />
      <div className="absolute left-3 top-[48%] h-1.5 w-[70%] rounded-sm opacity-80" style={{ background: t.swatches[t.swatches.length - 1] }} />
      <div className="absolute left-3 top-[56%] h-1.5 w-[55%] rounded-sm opacity-80" style={{ background: t.swatches[t.swatches.length - 1] }} />
      <div className="absolute left-3 top-[68%] h-1 w-[30%] rounded-sm" style={{ background: accent }} />
    </div>
  );
}

export function TemplatesDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const loadDocument = useEditorStore((s) => s.loadDocument);
  const apply = (t: TemplateDef) => {
    const doc = t.build();
    loadDocument(doc, {}, { name: t.name });
    useEditorStore.setState({ saveStatus: 'unsaved' });
    onClose();
  };
  return (
    <Modal open={open} onClose={onClose} title="Templates" width="max-w-4xl">
      <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 md:grid-cols-4">
        {TEMPLATES.map((t) => (
          <button key={t.id} type="button" onClick={() => apply(t)} className="group text-left">
            <TemplateThumb t={t} />
            <p className="mt-1.5 text-[12px] font-medium text-ink-100 group-hover:text-accent">{t.name}</p>
            <p className="text-[10px] leading-snug text-ink-400">{t.width}×{t.height} · {t.description}</p>
          </button>
        ))}
      </div>
      <p className="px-4 pb-4 text-[10px] text-ink-500">Every template opens as fully editable layers — background, lights, shapes, text and effects.</p>
    </Modal>
  );
}

export function NewDesignDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const newDocument = useEditorStore((s) => s.newDocument);
  const [custom, setCustom] = useState({ w: 1080, h: 1350 });
  const quick = [
    { label: 'Square', hint: '1:1 · 1080×1080', w: 1080, h: 1080 },
    { label: 'Portrait', hint: '4:5 · 1080×1350', w: 1080, h: 1350 },
    { label: 'Story', hint: '9:16 · 1080×1920', w: 1080, h: 1920 },
    { label: 'Landscape', hint: '16:9 · 1920×1080', w: 1920, h: 1080 },
    { label: '3:4', hint: '1200×1600', w: 1200, h: 1600 },
    { label: '3:2', hint: '1800×1200', w: 1800, h: 1200 },
  ];
  const create = (w: number, h: number) => {
    newDocument(w, h);
    onClose();
  };
  return (
    <Modal open={open} onClose={onClose} title="New design" width="max-w-lg">
      <div className="p-4">
        <div className="grid grid-cols-3 gap-2">
          {quick.map((q) => (
            <button key={q.label} type="button" onClick={() => create(q.w, q.h)} className="flex flex-col items-center gap-2 rounded-lg border border-line bg-ink-850 p-3 hover:border-accent/60">
              <div className="flex h-14 w-14 items-center justify-center"><div className="border border-ink-300" style={{ width: q.w >= q.h ? 48 : (48 * q.w) / q.h, height: q.h >= q.w ? 48 : (48 * q.h) / q.w }} /></div>
              <span className="text-[12px] font-medium">{q.label}</span>
              <span className="text-[10px] text-ink-400">{q.hint}</span>
            </button>
          ))}
        </div>
        <p className="mb-1.5 mt-4 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Presets</p>
        <div className="flex flex-wrap gap-1.5">
          {CANVAS_PRESETS.map((p) => (
            <button key={p.id} type="button" className="btn h-7 text-[11px]" onClick={() => create(p.width, p.height)}>{p.label} <span className="text-ink-400">{p.width}×{p.height}</span></button>
          ))}
        </div>
        <p className="mb-1.5 mt-4 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Custom</p>
        <div className="flex items-center gap-2">
          <NumberField label="W" value={custom.w} min={64} max={8000} onChange={(w) => setCustom((c) => ({ ...c, w: Math.round(w) }))} className="w-28" />
          <NumberField label="H" value={custom.h} min={64} max={8000} onChange={(h) => setCustom((c) => ({ ...c, h: Math.round(h) }))} className="w-28" />
          <button type="button" className="btn btn-primary" onClick={() => create(custom.w, custom.h)}>Create</button>
        </div>
      </div>
    </Modal>
  );
}

export function ProjectsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { projects, loadProject, deleteProject, duplicateProject, renameProject, importProjectFile } = useProjectStore();
  const currentId = useEditorStore((s) => s.projectId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const openProject = async (id: string) => {
    if (await loadProject(id)) onClose();
  };
  return (
    <Modal open={open} onClose={onClose} title="Projects" width="max-w-xl" footer={<button type="button" className="btn" onClick={() => fileRef.current?.click()}><Upload size={13} /> Import .json project</button>}>
      <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void importProjectFile(f).then((ok) => { if (ok) onClose(); else alert('Could not read that project file.'); }); e.target.value = ''; }} />
      <div className="divide-y divide-line">
        {projects.length === 0 && <p className="p-6 text-center text-[12px] text-ink-400">No saved projects yet. Designs autosave to this browser as you work.</p>}
        {projects.map((p) => (
          <div key={p.id} className={cn('flex items-center gap-3 px-4 py-2.5', p.id === currentId && 'bg-accent-soft/40')}>
            <button type="button" onClick={() => void openProject(p.id)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-line bg-ink-800 text-ink-400"><FolderOpen size={16} /></div>
              <div className="min-w-0">
                {renaming === p.id ? (
                  <input autoFocus aria-label="Project name" className="field h-6" defaultValue={p.name} onClick={(e) => e.stopPropagation()} onBlur={(e) => { void renameProject(p.id, e.target.value || p.name); setRenaming(null); }} onKeyDown={(e) => (e.key === 'Enter' || e.key === 'Escape') && (e.target as HTMLInputElement).blur()} />
                ) : (
                  <p className="truncate text-[12px] font-medium">{p.name}{p.id === currentId && <span className="ml-2 text-[10px] text-accent">current</span>}</p>
                )}
                <p className="text-[10px] text-ink-400">{p.width}×{p.height} · {p.elementCount} layers · {new Date(p.updatedAt).toLocaleString()}</p>
              </div>
            </button>
            <button className="icon-btn h-7 w-7" title="Rename" aria-label="Rename project" onClick={() => setRenaming(p.id)}><Pencil size={13} /></button>
            <button className="icon-btn h-7 w-7" title="Duplicate" aria-label="Duplicate project" onClick={() => void duplicateProject(p.id)}><Copy size={13} /></button>
            <button className="icon-btn h-7 w-7 hover:text-red-400" title="Delete" aria-label="Delete project" onClick={() => { if (confirm(`Delete "${p.name}"?`)) void deleteProject(p.id); }}><Trash2 size={13} /></button>
          </div>
        ))}
      </div>
    </Modal>
  );
}
