import { useEffect, useState } from 'react';
import { useEditorStore } from '@/store/editorStore';
import { useUIStore } from '@/store/uiStore';
import { useIsTouch } from '@/store/uiStore';
import { Modal } from '@/components/ui';

const GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: 'General',
    items: [
      ['Command palette', '⌘/Ctrl + K'],
      ['Open the Copilot', '⌘/Ctrl + J'],
      ['Save project', '⌘/Ctrl + S'],
      ['Export image', '⌘/Ctrl + E'],
      ['Preview mode', 'P'],
      ['Undo / Redo', '⌘Z / ⇧⌘Z'],
    ],
  },
  {
    title: 'Layers',
    items: [
      ['Duplicate', '⌘/Ctrl + D'],
      ['Copy / Paste', '⌘C / ⌘V'],
      ['Group / Ungroup', '⌘G / ⇧⌘G'],
      ['Delete selection', 'Delete'],
      ['Nudge 1px / 10px', 'Arrows / ⇧+Arrows'],
      ['Bring forward / back', '⌘] / ⌘['],
      ['Select all', '⌘/Ctrl + A'],
    ],
  },
  {
    title: 'Canvas',
    items: [
      ['Zoom in / out', '⌘ + / ⌘ −'],
      ['Zoom to 100%', '⌘/Ctrl + 0'],
      ['Zoom to fit', '⇧ + 1'],
      ['Pan', 'Space-drag or H (hand tool)'],
      ['Zoom gesture', 'Pinch or ⌘ + scroll'],
      ['Edit text', 'Double-click a text layer'],
    ],
  },
];

export function ShortcutsDialog() {
  const open = useUIStore((s) => s.shortcutsOpen);
  const setOpen = useUIStore((s) => s.setShortcuts);
  const setModal = useEditorStore((s) => s.setModal);
  const touch = useIsTouch();
  const [installEvent, setInstallEvent] = useState<Event | null>(null);

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      setInstallEvent(e);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const install = async () => {
    const e = installEvent as (Event & { prompt?: () => Promise<void> }) | null;
    await e?.prompt?.();
    setInstallEvent(null);
  };

  return (
    <Modal open={open} onClose={() => setOpen(false)} title="Keyboard shortcuts & help" width="max-w-3xl" fullscreenOnMobile={false}>
      <div className="grid gap-4 p-4 sm:grid-cols-3">
        {GROUPS.map((g) => (
          <div key={g.title}>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-300">{g.title}</p>
            <ul className="space-y-1.5">
              {g.items.map(([label, keys]) => (
                <li key={label} className="flex items-center justify-between gap-2 text-[11.5px] text-ink-200">
                  <span>{label}</span>
                  <kbd>{keys}</kbd>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="space-y-2 border-t border-line p-4">
        <p className="text-[11.5px] text-ink-300">
          Everything runs offline in your browser — projects are stored locally (IndexedDB). {touch ? 'On touch devices, pinch to zoom and drag layers directly.' : ''}
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn"
            onClick={() => {
              setOpen(false);
              setModal('settings');
            }}
          >
            Open settings
          </button>
          {installEvent && (
            <button type="button" className="btn btn-primary" onClick={() => void install()}>
              Install app on this device
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
