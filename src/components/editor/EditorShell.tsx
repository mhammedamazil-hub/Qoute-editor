import { useEffect, useState, type ReactNode } from 'react';
import {
  ArrowLeft,
  Download,
  Eye,
  Group as GroupIcon,
  Layers as LayersIcon,
  PaintBucket,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  SlidersHorizontal,
  Wand2,
} from 'lucide-react';
import { BACKGROUND_ID, useEditorStore } from '@/store/editorStore';
import { useUIStore, useVisualViewportInset } from '@/store/uiStore';
import { CanvasEditor } from './canvas/CanvasEditor';
import { EditorToolbar, AddMenuContent } from './EditorToolbar';
import { LayerPanel } from './LayerPanel';
import { PropertiesPanel } from './PropertiesPanel';
import { TopBar, SaveIndicator } from './TopBar';
import { ZoomControls } from './ZoomControls';
import { SelectionToolbar } from './SelectionToolbar';
import { BottomSheet, useMediaQuery } from '@/components/ui';
import { cn } from '@/utils/cn';

/* ------------------------------------------------------------------ *
 * shared chrome
 * ------------------------------------------------------------------ */

function RightPanel() {
  const rightTab = useEditorStore((s) => s.rightTab);
  const setRightTab = useEditorStore((s) => s.setRightTab);
  return (
    <>
      <div className="flex h-9 shrink-0 border-b border-line" role="tablist">
        {(['properties', 'layers'] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={rightTab === t}
            type="button"
            onClick={() => setRightTab(t)}
            className={cn('flex-1 text-[11px] font-semibold uppercase tracking-wider', rightTab === t ? 'border-b-2 border-accent text-ink-100' : 'text-ink-400 hover:text-ink-200')}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{rightTab === 'properties' ? <PropertiesPanel /> : <LayerPanel />}</div>
    </>
  );
}

function StatusBar({ onTogglePanel, panelOpen }: { onTogglePanel?: () => void; panelOpen?: boolean }) {
  const canvas = useEditorStore((s) => s.doc.canvas);
  const count = useEditorStore((s) => s.doc.elements.length);
  const selected = useEditorStore((s) => s.selectedIds.length);
  const editingGroupId = useEditorStore((s) => s.editingGroupId);
  const setEditingGroup = useEditorStore((s) => s.setEditingGroup);
  return (
    <footer className="safe-bottom flex h-8 shrink-0 items-center gap-3 border-t border-line bg-ink-900 px-3 text-[11px] text-ink-400">
      <span className="mono-num">
        {canvas.width} × {canvas.height}
      </span>
      <span className="hidden sm:inline">
        {count} layers{selected ? ` · ${selected} selected` : ''}
      </span>
      {editingGroupId && (
        <button type="button" className="flex items-center gap-1 text-accent" onClick={() => setEditingGroup(null)}>
          <GroupIcon size={11} /> Editing group — click to exit
        </button>
      )}
      <span className="ml-auto">
        <SaveIndicator />
      </span>
      {onTogglePanel && (
        <button type="button" className="icon-btn icon-btn-sm" onClick={onTogglePanel} title={panelOpen ? 'Hide panels' : 'Show panels'} aria-label="Toggle panels">
          {panelOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}
        </button>
      )}
      <ZoomControls />
    </footer>
  );
}

function PreviewOverlay() {
  const setPreviewMode = useEditorStore((s) => s.setPreviewMode);
  const setModal = useEditorStore((s) => s.setModal);
  return (
    <div className="absolute inset-0 z-40 flex flex-col bg-ink-950">
      <div className="safe-top flex h-11 shrink-0 items-center gap-2 px-3">
        <button type="button" className="btn btn-ghost" onClick={() => setPreviewMode(false)}>
          <ArrowLeft size={14} /> Back to Editor
        </button>
        <span className="ml-auto text-[11px] text-ink-400">Preview</span>
        <button type="button" className="btn btn-primary" onClick={() => setModal('export')}>
          <Download size={14} /> Export
        </button>
      </div>
      <div className="relative min-h-0 flex-1">
        <CanvasEditor interactive={false} fitPadding={16} />
        <SelectionToolbar />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * layouts
 * ------------------------------------------------------------------ */

function DesktopLayout({ wide }: { wide: boolean }) {
  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <EditorToolbar />
        <main className="relative min-w-0 flex-1">
          <CanvasEditor fitPadding={wide ? 64 : 40} />
          <SelectionToolbar />
        </main>
        <aside className={cn('flex shrink-0 flex-col border-l border-line bg-ink-900', wide ? 'w-[328px]' : 'w-[300px]')}>
          <RightPanel />
        </aside>
      </div>
      <StatusBar />
    </div>
  );
}

/** Tablet (landscape ≥768px): icon rail + canvas + slide-over inspector. */
function TabletLayout() {
  const [panelOpen, setPanelOpen] = useState(true);
  return (
    <div className="flex h-full flex-col">
      <TopBar compact />
      <div className="relative flex min-h-0 flex-1">
        <EditorToolbar />
        <main className="relative min-w-0 flex-1">
          <CanvasEditor fitPadding={28} />
          <SelectionToolbar />
          {!panelOpen && (
            <button type="button" className="btn absolute right-2 top-2 z-20 glass" onClick={() => setPanelOpen(true)} aria-label="Show panels">
              <PanelRightOpen size={14} /> Panels
            </button>
          )}
        </main>
        {panelOpen && (
          <aside className="fade-up absolute inset-y-0 right-0 z-30 flex w-[320px] flex-col border-l border-line shadow-xl glass">
            <button type="button" className="icon-btn icon-btn-sm absolute left-2 top-2 z-40" onClick={() => setPanelOpen(false)} aria-label="Hide panels">
              <PanelRightClose size={15} />
            </button>
            <div className="pt-8" />
            <RightPanel />
          </aside>
        )}
      </div>
      <StatusBar onTogglePanel={() => setPanelOpen((v) => !v)} panelOpen={panelOpen} />
    </div>
  );
}

function MobileLayout() {
  const sheet = useEditorStore((s) => s.mobileSheet);
  const setSheet = useEditorStore((s) => s.setMobileSheet);
  const select = useEditorStore((s) => s.select);
  const setPreviewMode = useEditorStore((s) => s.setPreviewMode);
  const setAIOpen = useUIStore((s) => s.setAIOpen);
  const selectedCount = useEditorStore((s) => s.selectedIds.length);
  const selectedName = useEditorStore((s) => {
    const id = s.selectedIds[0];
    if (id === BACKGROUND_ID) return 'Background';
    return s.doc.elements.find((e) => e.id === id)?.name ?? '';
  });
  const keyboardInset = useVisualViewportInset();

  useEffect(() => {
    if (selectedCount === 0 && sheet === 'properties') setSheet('none');
  }, [selectedCount, sheet, setSheet]);

  const NavBtn = ({ label, icon, onClick, active }: { label: string; icon: ReactNode; onClick: () => void; active?: boolean }) => (
    <button
      type="button"
      onClick={onClick}
      className={cn('flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-lg py-1 text-[10px]', active ? 'text-accent' : 'text-ink-300')}
      aria-label={label}
      aria-pressed={active}
    >
      {icon}
      {label}
    </button>
  );

  return (
    <div className="flex h-full flex-col" style={{ paddingBottom: keyboardInset ? keyboardInset : undefined }}>
      <TopBar compact />
      <main className="relative min-h-0 flex-1">
        <CanvasEditor fitPadding={12} />
        {selectedCount > 0 && sheet === 'none' && (
          <button
            type="button"
            onClick={() => setSheet('properties')}
            className="fade-up absolute bottom-14 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-line px-3 py-1.5 text-[11px] text-ink-100 shadow-lg glass"
          >
            <SlidersHorizontal size={13} className="text-accent" /> Edit {selectedName}
          </button>
        )}
        <div className="absolute right-2 top-2 z-20 rounded-md border border-line glass">
          <ZoomControls compact />
        </div>
        <SelectionToolbar compact />
        <BottomSheet open={sheet === 'properties'} onClose={() => setSheet('none')} title={selectedName || 'Properties'} height="62vh">
          <PropertiesPanel />
        </BottomSheet>
        <BottomSheet open={sheet === 'layers'} onClose={() => setSheet('none')} title="Layers" height="62vh">
          <LayerPanel />
        </BottomSheet>
        <BottomSheet open={sheet === 'add'} onClose={() => setSheet('none')} title="Add layer" height="66vh">
          <div className="p-2">
            <AddMenuContent onDone={() => setSheet('properties')} />
          </div>
        </BottomSheet>
      </main>
      <nav className="safe-bottom flex shrink-0 items-center gap-0.5 border-t border-line bg-ink-900 px-1 py-1" aria-label="Editor tools">
        <NavBtn label="Add" icon={<Plus size={19} />} active={sheet === 'add'} onClick={() => setSheet(sheet === 'add' ? 'none' : 'add')} />
        <NavBtn label="Edit" icon={<SlidersHorizontal size={19} />} active={sheet === 'properties'} onClick={() => setSheet(sheet === 'properties' ? 'none' : 'properties')} />
        <NavBtn label="Layers" icon={<LayersIcon size={19} />} active={sheet === 'layers'} onClick={() => setSheet(sheet === 'layers' ? 'none' : 'layers')} />
        <NavBtn
          label="Colour"
          icon={<PaintBucket size={19} />}
          onClick={() => {
            select([BACKGROUND_ID]);
            setSheet('properties');
          }}
        />
        <NavBtn label="Preview" icon={<Eye size={19} />} onClick={() => setPreviewMode(true)} />
        <NavBtn label="AI" icon={<Wand2 size={19} className="text-accent" />} onClick={() => setAIOpen(true)} />
      </nav>
    </div>
  );
}

export function EditorShell() {
  const isPhone = useMediaQuery('(max-width: 767px)');
  const shortLandscape = useMediaQuery('(max-height: 460px) and (orientation: landscape)');
  const isDesktop = useMediaQuery('(min-width: 1100px)');
  const isWide = useMediaQuery('(min-width: 1600px)');
  const previewMode = useEditorStore((s) => s.previewMode);

  const layout: 'phone' | 'tablet' | 'desktop' = isDesktop ? 'desktop' : isPhone || shortLandscape ? 'phone' : 'tablet';

  return (
    <div className="relative h-full overflow-hidden">
      {layout === 'desktop' ? <DesktopLayout wide={isWide} /> : layout === 'tablet' ? <TabletLayout /> : <MobileLayout />}
      {previewMode && <PreviewOverlay />}
    </div>
  );
}
