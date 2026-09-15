import { useEffect } from 'react';
import { Clock, Command, FolderOpen, LayoutTemplate, MonitorSmartphone, Plus, Settings as SettingsIcon, Sparkles, Wand2 } from 'lucide-react';
import { useEditorStore } from '@/store/editorStore';
import { useProjectStore } from '@/store/projectStore';
import { useUIStore } from '@/store/uiStore';
import { TEMPLATES } from '@/components/templates/templates';

function TemplateChip({ id, name, swatches, onPick }: { id: string; name: string; swatches: string[]; onPick: () => void }) {
  const [bg, accent, second, third] = swatches;
  return (
    <button type="button" onClick={onPick} className="group shrink-0 text-left" aria-label={`Use template ${name}`} data-template={id}>
      <div className="relative h-[104px] w-[82px] overflow-hidden rounded-lg border border-line transition-colors group-hover:border-accent/60" style={{ background: bg }}>
        <div className="absolute -right-5 -top-5 h-16 w-16 rounded-full opacity-60 blur-lg" style={{ background: accent }} />
        {second && <div className="absolute -bottom-6 -left-5 h-16 w-16 rounded-full opacity-40 blur-lg" style={{ background: second }} />}
        <div className="absolute left-2.5 top-[38%] h-[2px] w-7" style={{ background: accent }} />
        <div className="absolute left-2.5 top-[48%] h-1 w-[64%] rounded-sm opacity-80" style={{ background: third ?? accent }} />
        <div className="absolute left-2.5 top-[56%] h-1 w-[48%] rounded-sm opacity-80" style={{ background: third ?? accent }} />
        <div className="absolute left-2.5 top-[68%] h-[3px] w-[28%] rounded-sm" style={{ background: accent }} />
      </div>
      <p className="mt-1 w-[82px] truncate text-[11px] text-ink-300 group-hover:text-ink-100">{name}</p>
    </button>
  );
}

export function StartScreen() {
  const setModal = useEditorStore((s) => s.setModal);
  const loadDocument = useEditorStore((s) => s.loadDocument);
  const setPalette = useUIStore((s) => s.setPalette);
  const setAIOpen = useUIStore((s) => s.setAIOpen);
  const { projects, lastProjectId, loadProject, init, ready } = useProjectStore();

  useEffect(() => {
    if (!ready) void init();
  }, [ready, init]);

  const last = projects.find((p) => p.id === lastProjectId);
  const recents = projects.slice(0, 3);

  const useTemplate = (id: string) => {
    const tpl = TEMPLATES.find((t) => t.id === id);
    if (!tpl) return;
    loadDocument(tpl.build(), {}, { name: tpl.name });
    useEditorStore.setState({ saveStatus: 'unsaved' });
  };

  return (
    <div className="relative h-full overflow-y-auto overscroll-contain">
      {/* restrained atmospheric backdrop, built with the same principles the editor produces */}
      <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 h-[520px] w-[520px] rounded-full opacity-40 blur-3xl" style={{ background: 'radial-gradient(circle, #d89b35 0%, transparent 65%)' }} />
      <div aria-hidden className="pointer-events-none absolute -bottom-52 -left-40 h-[560px] w-[560px] rounded-full opacity-30 blur-3xl" style={{ background: 'radial-gradient(circle, #12a37f 0%, transparent 65%)' }} />
      <div aria-hidden className="pointer-events-none absolute left-[8%] top-[22%] hidden h-[360px] w-px bg-gradient-to-b from-transparent via-accent/50 to-transparent sm:block" />

      <div className="safe-top safe-x absolute right-3 top-3 flex items-center gap-1">
        <button className="icon-btn" title="Command palette (Ctrl+K)" aria-label="Command palette" onClick={() => setPalette(true)}>
          <Command size={16} />
        </button>
        <button className="icon-btn" title="Settings" aria-label="Settings" onClick={() => setModal('settings')}>
          <SettingsIcon size={17} />
        </button>
      </div>

      <div className="mx-auto flex min-h-full w-full max-w-5xl flex-col justify-center px-5 py-10 sm:px-8">
        <div className="fade-up relative z-10">
          <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-accent">QuoteCraft</p>
          <h1 className="text-balance mt-3 text-[30px] font-semibold leading-[1.05] sm:text-[44px]" style={{ fontFamily: '"Playfair Display", serif' }}>
            Create visually powerful quotes — on any device.
          </h1>
          <p className="mt-3 max-w-xl text-[13px] leading-relaxed text-ink-300">
            A layer-based poster editor. Backgrounds, lights, gradients, geometry, images and typography stay fully editable until you export. The built-in AI copilot can do all of it for you.
          </p>

          <div className="mt-6 flex flex-wrap gap-2">
            <button type="button" className="btn btn-primary h-10 px-4 text-[13px]" onClick={() => setModal('newDesign')}>
              <Plus size={15} /> New design
            </button>
            <button type="button" className="btn h-10 px-4 text-[13px]" onClick={() => setAIOpen(true)}>
              <Wand2 size={15} className="text-accent" /> Design with AI
            </button>
            <button type="button" className="btn h-10 px-4 text-[13px]" onClick={() => setModal('templates')}>
              <LayoutTemplate size={15} /> Templates
            </button>
            <button type="button" className="btn h-10 px-4 text-[13px]" onClick={() => setModal('projects')}>
              <FolderOpen size={15} /> Open project
            </button>
          </div>

          {last && (
            <button
              type="button"
              onClick={() => void loadProject(last.id)}
              className="mt-6 flex w-full max-w-xl items-center gap-3 rounded-lg border border-line bg-ink-900/70 p-3 text-left transition-colors hover:border-accent/50"
            >
              <Clock size={15} className="text-ink-400" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-medium">Continue “{last.name}”</p>
                <p className="mono-num text-[10px] text-ink-400">
                  {last.width}×{last.height} · {last.elementCount} layers · autosaved {new Date(last.updatedAt).toLocaleString()}
                </p>
              </div>
              <Sparkles size={14} className="text-accent" />
            </button>
          )}

          {recents.length > 1 && (
            <div className="mt-3 flex max-w-xl flex-wrap gap-2">
              {recents.slice(1).map((p) => (
                <button key={p.id} type="button" className="btn h-8 text-[11px]" onClick={() => void loadProject(p.id)}>
                  <FolderOpen size={12} /> {p.name}
                </button>
              ))}
            </div>
          )}

          <div className="mt-8">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Start from a template</p>
            <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
              {TEMPLATES.slice(0, 8).map((t) => (
                <TemplateChip key={t.id} id={t.id} name={t.name} swatches={t.swatches} onPick={() => useTemplate(t.id)} />
              ))}
              <button
                type="button"
                onClick={() => setModal('templates')}
                className="flex h-[104px] w-[82px] shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-line text-[11px] text-ink-400 hover:border-accent/50 hover:text-ink-200"
              >
                <LayoutTemplate size={18} />
                All {TEMPLATES.length}
              </button>
            </div>
          </div>

          <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-[10.5px] text-ink-500">
            <span className="flex items-center gap-1.5">
              <MonitorSmartphone size={12} /> Phone · tablet · desktop
            </span>
            <span className="flex items-center gap-1.5">
              <Sparkles size={12} /> AI copilot (your own Gemini key)
            </span>
            <span>No account · no backend · works offline</span>
          </div>
        </div>
      </div>
    </div>
  );
}
