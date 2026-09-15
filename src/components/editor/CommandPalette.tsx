import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  Command as CommandIcon,
  CornerDownLeft,
  Eye,
  Grid2x2,
  Layers,
  LayoutTemplate,
  Maximize2,
  Moon,
  Palette,
  Redo2,
  Save,
  Search,
  Settings,
  Sparkles,
  Sun,
  Type,
  Undo2,
  Wand2,
  ZoomIn,
} from 'lucide-react';
import { executeTool } from '@/ai/agent/tools';
import { useEditorStore } from '@/store/editorStore';
import { useProjectStore } from '@/store/projectStore';
import { useSettingsStore } from '@/store/settingsStore';
import { useUIStore, toast } from '@/store/uiStore';
import { PALETTES } from '@/engine/palettes';
import { fitToScreen, zoomTo } from '@/components/editor/ZoomControls';
import { cn } from '@/utils/cn';

interface Command {
  id: string;
  title: string;
  group: string;
  keywords?: string;
  icon?: React.ReactNode;
  run: () => void;
  hint?: string;
}

const ctx = { apiKey: '', model: '' };

export function CommandPalette() {
  const open = useUIStore((s) => s.paletteOpen);
  const setPalette = useUIStore((s) => s.setPalette);
  const setAIOpen = useUIStore((s) => s.setAIOpen);
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands = useMemo<Command[]>(() => {
    const ed = () => useEditorStore.getState();
    const ids = () => ed().selectedIds.filter((i) => i !== '__background__');
    const close = () => setPalette(false);

    const list: Command[] = [
      { id: 'ai', title: 'Ask the Copilot', group: 'AI', icon: <Sparkles size={14} />, keywords: 'chat ai assistant', hint: '⌘J', run: () => { close(); setAIOpen(true); } },
      { id: 'ai-generate', title: 'Design a poster with AI', group: 'AI', icon: <Wand2 size={14} />, keywords: 'generate studio create', run: () => { close(); setAIOpen(true); } },
      { id: 'undo', title: 'Undo', group: 'Edit', icon: <Undo2 size={14} />, hint: '⌘Z', run: () => { ed().undo(); close(); } },
      { id: 'redo', title: 'Redo', group: 'Edit', icon: <Redo2 size={14} />, hint: '⇧⌘Z', run: () => { ed().redo(); close(); } },
      { id: 'duplicate', title: 'Duplicate selection', group: 'Edit', keywords: 'copy', hint: '⌘D', run: () => { if (ids().length) ed().duplicateElements(ids()); close(); } },
      { id: 'group', title: 'Group selection', group: 'Edit', hint: '⌘G', run: () => { ed().groupSelected(); close(); } },
      { id: 'ungroup', title: 'Ungroup selection', group: 'Edit', hint: '⇧⌘G', run: () => { ed().ungroupSelected(); close(); } },
      { id: 'align-center', title: 'Centre selection on canvas', group: 'Edit', run: () => { ed().alignSelected('canvas'); close(); } },
      { id: 'front', title: 'Bring to front', group: 'Edit', run: () => { ids().forEach((id) => ed().moveLayer(id, 'top')); close(); } },
      { id: 'back', title: 'Send to back', group: 'Edit', run: () => { ids().forEach((id) => ed().moveLayer(id, 'bottom')); close(); } },
      { id: 'delete', title: 'Delete selection', group: 'Edit', keywords: 'remove trash', run: () => { if (ids().length) ed().removeElements(ids()); close(); } },

      { id: 'add-quote', title: 'Add quote text', group: 'Add', icon: <Type size={14} />, run: () => { void executeTool('add_text', { role: 'quote' }, ctx); close(); } },
      { id: 'add-author', title: 'Add author line', group: 'Add', icon: <Type size={14} />, run: () => { void executeTool('add_text', { role: 'author' }, ctx); close(); } },
      { id: 'add-heading', title: 'Add display heading', group: 'Add', icon: <Type size={14} />, run: () => { void executeTool('add_text', { role: 'heading' }, ctx); close(); } },
      { id: 'add-quote-mark', title: 'Add quote mark', group: 'Add', run: () => { void executeTool('add_quote_mark', {}, ctx); close(); } },
      { id: 'add-light', title: 'Add amber light', group: 'Add', icon: <Sun size={14} />, run: () => { void executeTool('add_light', { color: '#d89b35' }, ctx); close(); } },
      { id: 'add-light-emerald', title: 'Add emerald light', group: 'Add', icon: <Sun size={14} />, run: () => { void executeTool('add_light', { color: '#12a37f', x: 200, y: 900 }, ctx); close(); } },
      { id: 'add-gradient', title: 'Add gradient wash', group: 'Add', run: () => { void executeTool('add_gradient_layer', {}, ctx); close(); } },
      { id: 'add-particles', title: 'Add subtle particles', group: 'Add', run: () => { void executeTool('add_particles', {}, ctx); close(); } },
      { id: 'add-circle', title: 'Add geometric circle', group: 'Add', icon: <Grid2x2 size={14} />, run: () => { void executeTool('add_shape', { shape: 'circle', fill: null, stroke: '#d9a441', strokeWidth: 1.5, opacity: 0.4 }, ctx); close(); } },
      { id: 'add-line', title: 'Add hairline', group: 'Add', run: () => { void executeTool('add_decoration', { kind: 'thin-line' }, ctx); close(); } },
      { id: 'add-frame', title: 'Add corner frame', group: 'Add', run: () => { void executeTool('add_decoration', { kind: 'corner' }, ctx); close(); } },

      ...PALETTES.map((p) => ({
        id: `palette-${p.id}`,
        title: `Palette · ${p.label}`,
        group: 'Style',
        keywords: 'colour color theme palette',
        icon: <Palette size={14} />,
        run: () => {
          void executeTool('apply_palette', { palette: p.id }, ctx);
          close();
        },
      })),
      { id: 'theme-dark', title: 'Interface: dark theme', group: 'Style', icon: <Moon size={14} />, run: () => { useSettingsStore.getState().update({ theme: 'dark' }); close(); } },
      { id: 'theme-light', title: 'Interface: light theme', group: 'Style', icon: <Sun size={14} />, run: () => { useSettingsStore.getState().update({ theme: 'light' }); close(); } },
      { id: 'theme-system', title: 'Interface: match system', group: 'Style', run: () => { useSettingsStore.getState().update({ theme: 'system' }); close(); } },

      { id: 'fit', title: 'Zoom to fit', group: 'View', icon: <Maximize2 size={14} />, hint: '⇧1', run: () => { fitToScreen(); close(); } },
      { id: 'zoom-100', title: 'Zoom to 100%', group: 'View', icon: <ZoomIn size={14} />, hint: '⌘0', run: () => { zoomTo(1); close(); } },
      { id: 'preview', title: 'Toggle preview mode', group: 'View', icon: <Eye size={14} />, hint: 'P', run: () => { ed().setPreviewMode(!ed().previewMode); close(); } },
      { id: 'layers', title: 'Open layers panel', group: 'View', icon: <Layers size={14} />, run: () => { ed().setRightTab('layers'); ed().setMobileSheet('layers'); close(); } },

      { id: 'new', title: 'New design…', group: 'File', run: () => { ed().setModal('newDesign'); close(); } },
      { id: 'templates', title: 'Browse templates', group: 'File', icon: <LayoutTemplate size={14} />, run: () => { ed().setModal('templates'); close(); } },
      { id: 'projects', title: 'Open project…', group: 'File', run: () => { ed().setModal('projects'); close(); } },
      { id: 'save', title: 'Save project', group: 'File', icon: <Save size={14} />, hint: '⌘S', run: () => { void useProjectStore.getState().saveCurrent(); toast('Project saved', 'success'); close(); } },
      { id: 'export', title: 'Export image…', group: 'File', icon: <ArrowDownToLine size={14} />, hint: '⌘E', run: () => { ed().setModal('export'); close(); } },
      { id: 'settings', title: 'Settings', group: 'File', icon: <Settings size={14} />, run: () => { ed().setModal('settings'); close(); } },
    ];
    return list;
  }, [setPalette, setAIOpen]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => `${c.title} ${c.group} ${c.keywords ?? ''}`.toLowerCase().includes(q));
  }, [commands, query]);

  useEffect(() => {
    setIndex(0);
  }, [query, open]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30);
    else setQuery('');
  }, [open]);

  if (!open) return null;

  const grouped = filtered.reduce<Record<string, Command[]>>((acc, c) => {
    (acc[c.group] ??= []).push(c);
    return acc;
  }, {});

  let flatIndex = -1;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setIndex((i) => Math.min(filtered.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setIndex((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      filtered[index]?.run();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setPalette(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[55] flex items-start justify-center p-3 pt-[12vh]" onMouseDown={(e) => e.target === e.currentTarget && setPalette(false)} role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="absolute inset-0" style={{ background: 'var(--scrim)' }} aria-hidden />
      <div className="pop-in relative flex max-h-[70vh] w-full max-w-xl flex-col overflow-hidden rounded-xl border border-line bg-ink-900 shadow-2xl">
        <div className="flex shrink-0 items-center gap-2 border-b border-line px-3 py-2">
          <Search size={15} className="text-ink-400" />
          <input
            ref={inputRef}
            className="h-7 flex-1 bg-transparent text-[13px] outline-none placeholder:text-ink-500"
            placeholder="Search actions, layers, palettes, panels…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            aria-label="Search commands"
          />
          <span className="hidden items-center gap-1 text-[10px] text-ink-500 sm:flex">
            <kbd>esc</kbd> to close
          </span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
          {!filtered.length && <p className="px-3 py-6 text-center text-[12px] text-ink-400">No matching action.</p>}
          {Object.entries(grouped).map(([group, items]) => (
            <div key={group} className="mb-1">
              <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-ink-500">{group}</p>
              {items.map((c) => {
                flatIndex += 1;
                const active = flatIndex === index;
                return (
                  <button
                    key={c.id}
                    type="button"
                    onMouseEnter={() => setIndex(flatIndex)}
                    onClick={c.run}
                    className={cn('flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12.5px]', active ? 'bg-ink-750 text-ink-100' : 'text-ink-200 hover:bg-ink-850')}
                  >
                    <span className={cn('shrink-0', active ? 'text-accent' : 'text-ink-400')}>{c.icon ?? <CommandIcon size={14} />}</span>
                    <span className="min-w-0 flex-1 truncate">{c.title}</span>
                    {c.hint && <kbd>{c.hint}</kbd>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div className="flex shrink-0 items-center justify-between border-t border-line px-3 py-1.5 text-[10px] text-ink-500">
          <span className="flex items-center gap-1">
            <CornerDownLeft size={10} /> run · <ArrowDownToLine size={10} className="rotate-180" /> navigate
          </span>
          <span>
            <kbd>⌘</kbd> <kbd>K</kbd> anywhere
          </span>
        </div>
      </div>
    </div>
  );
}
