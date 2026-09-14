import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Check,
  ChevronLeft,
  Command as CommandIcon,
  Download,
  Eye,
  FolderOpen,
  LayoutTemplate,
  Moon,
  MoreHorizontal,
  Plus,
  Redo2,
  Save,
  Settings as SettingsIcon,
  Sun,
  Undo2,
  Wand2,
} from 'lucide-react';
import { selectCanRedo, selectCanUndo, useEditorStore } from '@/store/editorStore';
import { useProjectStore } from '@/store/projectStore';
import { useSettingsStore } from '@/store/settingsStore';
import { useUIStore, toast } from '@/store/uiStore';
import { cn } from '@/utils/cn';

export function SaveIndicator() {
  const status = useEditorStore((s) => s.saveStatus);
  const label = status === 'saving' ? 'Saving…' : status === 'saved' ? 'Saved' : status === 'unsaved' ? 'Unsaved changes' : 'Autosave on';
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-ink-400">
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full',
          status === 'saved' ? 'bg-emerald-400' : status === 'saving' ? 'bg-amber-400 animate-pulse' : status === 'unsaved' ? 'bg-ink-300' : 'bg-ink-500',
        )}
      />
      <span className="hidden sm:inline">{label}</span>
    </span>
  );
}

function Menu({ open, onClose, children, align = 'right' }: { open: boolean; onClose: () => void; children: ReactNode; align?: 'left' | 'right' }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const id = window.setTimeout(() => {
      document.addEventListener('mousedown', onDown);
      document.addEventListener('touchstart', onDown);
    }, 0);
    return () => {
      window.clearTimeout(id);
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      ref={ref}
      className={cn('fade-up absolute top-full z-50 mt-1 w-56 rounded-xl border border-line bg-ink-900 p-1.5 shadow-2xl', align === 'right' ? 'right-0' : 'left-0')}
      role="menu"
    >
      {children}
    </div>
  );
}

function MenuItem({ icon, label, onClick, hint, danger }: { icon?: ReactNode; label: string; onClick: () => void; hint?: string; danger?: boolean }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={cn('flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12.5px] text-ink-200 hover:bg-ink-800 hover:text-ink-100', danger && 'text-red-300 hover:bg-red-500/15')}
    >
      {icon && <span className="shrink-0 text-ink-400">{icon}</span>}
      <span className="flex-1 truncate">{label}</span>
      {hint && <kbd>{hint}</kbd>}
    </button>
  );
}

export function TopBar({ compact = false }: { compact?: boolean }) {
  const projectName = useEditorStore((s) => s.projectName);
  const setProjectName = useEditorStore((s) => s.setProjectName);
  const canUndo = useEditorStore(selectCanUndo);
  const canRedo = useEditorStore(selectCanRedo);
  const undo = useEditorStore((s) => s.undo);
  const redo = useEditorStore((s) => s.redo);
  const setModal = useEditorStore((s) => s.setModal);
  const setPreviewMode = useEditorStore((s) => s.setPreviewMode);
  const setScreen = useEditorStore((s) => s.setScreen);
  const saveCurrent = useProjectStore((s) => s.saveCurrent);
  const theme = useSettingsStore((s) => s.theme);
  const update = useSettingsStore((s) => s.update);
  const setPalette = useUIStore((s) => s.setPalette);
  const setAIOpen = useUIStore((s) => s.setAIOpen);
  const setShortcuts = useUIStore((s) => s.setShortcuts);
  const [menu, setMenu] = useState(false);

  const cycleTheme = () => {
    const current = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : theme;
    update({ theme: current === 'dark' ? 'light' : 'dark' });
  };

  const save = async () => {
    await saveCurrent();
    toast('Project saved', 'success');
  };

  return (
    <header className="safe-top safe-x flex h-12 shrink-0 items-center gap-1 border-b border-line bg-ink-900 px-2">
      <button className="icon-btn" title="Back to start" aria-label="Back to start" onClick={() => setScreen('start')}>
        <ChevronLeft size={17} />
      </button>
      {!compact && <span className="ml-1 hidden text-[11px] font-semibold uppercase tracking-[0.3em] text-accent sm:inline">QuoteCraft</span>}
      <input
        aria-label="Project name"
        className="ml-1 h-7 w-28 min-w-0 rounded border border-transparent bg-transparent px-1.5 text-[12px] font-medium text-ink-100 outline-none hover:border-line focus:border-accent/60 sm:w-44"
        value={projectName}
        onChange={(e) => setProjectName(e.target.value)}
      />
      {!compact && (
        <span className="mr-1 hidden lg:inline">
          <SaveIndicator />
        </span>
      )}

      <div className="mx-auto flex items-center gap-0.5">
        <button className="icon-btn" title="Undo (Ctrl+Z)" aria-label="Undo" disabled={!canUndo} onClick={undo}>
          <Undo2 size={16} />
        </button>
        <button className="icon-btn" title="Redo (Ctrl+Shift+Z)" aria-label="Redo" disabled={!canRedo} onClick={redo}>
          <Redo2 size={16} />
        </button>
        {!compact && (
          <button className="icon-btn hidden sm:inline-flex" title="Command palette (Ctrl+K)" aria-label="Command palette" onClick={() => setPalette(true)}>
            <CommandIcon size={16} />
          </button>
        )}
      </div>

      {!compact && (
        <div className="hidden items-center gap-0.5 md:flex">
          <button className="icon-btn" title="New design" aria-label="New design" onClick={() => setModal('newDesign')}>
            <Plus size={16} />
          </button>
          <button className="icon-btn" title="Templates" aria-label="Templates" onClick={() => setModal('templates')}>
            <LayoutTemplate size={16} />
          </button>
          <button className="icon-btn" title="Projects" aria-label="Projects" onClick={() => setModal('projects')}>
            <FolderOpen size={16} />
          </button>
          <button className="icon-btn" title="Save (Ctrl+S)" aria-label="Save project" onClick={() => void save()}>
            <Save size={16} />
          </button>
        </div>
      )}

      <button className="btn btn-ghost h-8 text-accent" title="Design with AI (Ctrl+J)" onClick={() => setAIOpen(true)}>
        <Wand2 size={15} /> <span className="hidden sm:inline">AI</span>
      </button>
      <button className="icon-btn" title="Preview (P)" aria-label="Preview" onClick={() => setPreviewMode(true)}>
        <Eye size={16} />
      </button>
      <button className="btn btn-primary h-8 px-2.5" title="Export (Ctrl+E)" onClick={() => setModal('export')}>
        <Download size={14} />
        <span className="hidden sm:inline">Export</span>
      </button>
      <div className="relative">
        <button className="icon-btn" title="More" aria-label="More options" onClick={() => setMenu((v) => !v)} aria-expanded={menu}>
          <MoreHorizontal size={16} />
        </button>
        <Menu open={menu} onClose={() => setMenu(false)}>
          <MenuItem
            icon={theme === 'light' ? <Moon size={14} /> : <Sun size={14} />}
            label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
            onClick={() => {
              cycleTheme();
              setMenu(false);
            }}
          />
          <MenuItem icon={<CommandIcon size={14} />} label="Command palette" hint="⌘K" onClick={() => { setPalette(true); setMenu(false); }} />
          <MenuItem icon={<SettingsIcon size={14} />} label="Settings" onClick={() => { setModal('settings'); setMenu(false); }} />
          <MenuItem icon={<Check size={14} />} label="Keyboard shortcuts" onClick={() => { setShortcuts(true); setMenu(false); }} />
          {compact && (
            <>
              <div className="my-1 h-px bg-line" />
              <MenuItem icon={<Plus size={14} />} label="New design" onClick={() => { setModal('newDesign'); setMenu(false); }} />
              <MenuItem icon={<LayoutTemplate size={14} />} label="Templates" onClick={() => { setModal('templates'); setMenu(false); }} />
              <MenuItem icon={<FolderOpen size={14} />} label="Projects" onClick={() => { setModal('projects'); setMenu(false); }} />
              <MenuItem icon={<Save size={14} />} label="Save project" onClick={() => { void save(); setMenu(false); }} />
            </>
          )}
        </Menu>
      </div>
      {compact ? null : (
        <button className="icon-btn" title="Settings" aria-label="Settings" onClick={() => setModal('settings')}>
          <SettingsIcon size={16} />
        </button>
      )}
    </header>
  );
}
