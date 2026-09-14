import { Component, useEffect, type ErrorInfo, type ReactNode } from 'react';
import { useEditorStore } from '@/store/editorStore';
import { useProjectStore } from '@/store/projectStore';
import { useSettingsStore } from '@/store/settingsStore';
import { useUIStore } from '@/store/uiStore';
import { waitForFonts, onFontsLoaded } from '@/engine/fonts';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { StartScreen } from '@/components/StartScreen';
import { EditorShell } from '@/components/editor/EditorShell';
import { ExportDialog } from '@/components/editor/ExportDialog';
import { Settings } from '@/components/settings/Settings';
import { AICopilot } from '@/components/ai/AICopilot';
import { CommandPalette } from '@/components/editor/CommandPalette';
import { ShortcutsDialog } from '@/components/editor/ShortcutsDialog';
import { TemplatesDialog, NewDesignDialog, ProjectsDialog } from '@/components/templates/TemplatesDialog';
import { ToastHost } from '@/components/ui';

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('QuoteCraft error', error, info);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
          <p className="text-[13px] font-semibold">Something went wrong in the editor.</p>
          <p className="max-w-md text-[11px] text-ink-400">{this.state.error.message}</p>
          <p className="text-[11px] text-ink-400">Your work is autosaved to this browser. Reload to continue.</p>
          <div className="flex gap-2">
            <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
              Reload
            </button>
            <button type="button" className="btn" onClick={() => this.setState({ error: null })}>
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

/** Applies theme, accent, density and motion preferences to <html>. */
function useAppearance() {
  const theme = useSettingsStore((s) => s.theme);
  const accent = useSettingsStore((s) => s.accent);
  const density = useSettingsStore((s) => s.uiDensity);
  const reduceMotion = useSettingsStore((s) => s.reduceMotion);

  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      const resolved = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : theme;
      root.dataset.theme = resolved;
      root.dataset.density = density;
      root.dataset.reduceMotion = String(reduceMotion);
      root.style.setProperty('--color-accent', accent);
      root.style.setProperty('--color-accent-soft', hexToRgba(accent, 0.16));
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute('content', resolved === 'light' ? '#ffffff' : '#07080a');
    };
    apply();
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [theme, accent, density, reduceMotion]);
}

function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return `rgba(217, 164, 65, ${alpha})`;
  let h = m[1];
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const n = parseInt(h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function Modals() {
  const modal = useEditorStore((s) => s.modal);
  const setModal = useEditorStore((s) => s.setModal);
  const aiOpen = useUIStore((s) => s.aiOpen);
  const setAIOpen = useUIStore((s) => s.setAIOpen);
  const close = () => setModal('none');
  const closeAI = () => {
    setAIOpen(false);
    if (modal === 'ai') setModal('none');
  };
  return (
    <>
      <ExportDialog open={modal === 'export'} onClose={close} />
      <Settings open={modal === 'settings'} onClose={close} />
      <TemplatesDialog open={modal === 'templates'} onClose={close} />
      <NewDesignDialog open={modal === 'newDesign'} onClose={close} />
      <ProjectsDialog open={modal === 'projects'} onClose={close} />
      <AICopilot open={aiOpen || modal === 'ai'} onClose={closeAI} />
    </>
  );
}

export default function App() {
  const screen = useEditorStore((s) => s.screen);
  const bumpFonts = useEditorStore((s) => s.bumpFonts);
  const init = useProjectStore((s) => s.init);
  useKeyboardShortcuts();
  useAppearance();

  useEffect(() => {
    void init();
    void waitForFonts().then(bumpFonts);
    return onFontsLoaded(bumpFonts);
  }, [init, bumpFonts]);

  // Warn before leaving with unsaved changes (autosave usually covers this).
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (useEditorStore.getState().saveStatus === 'unsaved') e.preventDefault();
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  // Offline support: cache the app shell so it keeps working without a network.
  useEffect(() => {
    if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return;
    if (location.protocol === 'file:') return;
    const id = window.setTimeout(() => {
      navigator.serviceWorker.register('sw.js').catch(() => undefined);
    }, 1500);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <ErrorBoundary>
      <div className="h-full select-none">
        {screen === 'start' ? <StartScreen /> : <EditorShell />}
        <Modals />
        <CommandPalette />
        <ShortcutsDialog />
        <ToastHost />
      </div>
    </ErrorBoundary>
  );
}
