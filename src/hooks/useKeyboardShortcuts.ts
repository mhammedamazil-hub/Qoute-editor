import { useEffect } from 'react';
import { BACKGROUND_ID, useEditorStore } from '@/store/editorStore';
import { useSettingsStore } from '@/store/settingsStore';
import { useUIStore } from '@/store/uiStore';
import { fitToScreen, zoomTo } from '@/components/editor/ZoomControls';

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

/**
 * Global shortcuts. Works on desktop and on tablets with a hardware keyboard;
 * touch users get every action through the UI (command palette, sheets, buttons).
 */
export function useKeyboardShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useEditorStore.getState();
      const ui = useUIStore.getState();
      const mod = e.metaKey || e.ctrlKey;
      const key = e.key.toLowerCase();

      // Command palette + copilot work everywhere, even in modals.
      if (mod && key === 'k') {
        e.preventDefault();
        ui.setPalette(!ui.paletteOpen);
        return;
      }
      if (mod && key === 'j') {
        e.preventDefault();
        ui.setAIOpen(true);
        return;
      }
      if (key === 'escape') {
        if (ui.paletteOpen) return ui.setPalette(false);
        if (ui.shortcutsOpen) return ui.setShortcuts(false);
        if (ui.aiOpen) return ui.setAIOpen(false);
      }
      if (mod && e.shiftKey && key === 'l') {
        e.preventDefault();
        const settings = useSettingsStore.getState();
        const effective = settings.theme === 'system' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : settings.theme;
        settings.update({ theme: effective === 'dark' ? 'light' : 'dark' });
        return;
      }
      if (e.key === '?' && !isTyping(e.target)) {
        e.preventDefault();
        ui.setShortcuts(true);
        return;
      }

      if (s.screen !== 'editor' || s.modal !== 'none') return;
      if (isTyping(e.target)) return;

      if (mod && key === 'z') {
        e.preventDefault();
        if (e.shiftKey) s.redo();
        else s.undo();
        return;
      }
      if (mod && key === 'y') {
        e.preventDefault();
        s.redo();
        return;
      }

      const ids = s.selectedIds.filter((i) => i !== BACKGROUND_ID);
      if (mod && key === 'c') {
        s.copy();
        return;
      }
      if (mod && key === 'v') {
        e.preventDefault();
        s.paste();
        return;
      }
      if (mod && key === 'd') {
        e.preventDefault();
        if (ids.length) s.duplicateElements(ids);
        return;
      }
      if (mod && key === 'g') {
        e.preventDefault();
        if (e.shiftKey) s.ungroupSelected();
        else s.groupSelected();
        return;
      }
      if (mod && key === 'a') {
        e.preventDefault();
        s.select(s.doc.elements.filter((el) => !el.parentId).map((el) => el.id));
        return;
      }
      if (mod && key === 's') {
        e.preventDefault();
        void import('@/store/projectStore').then((m) => m.useProjectStore.getState().saveCurrent());
        return;
      }
      if (mod && key === 'e') {
        e.preventDefault();
        s.setModal('export');
        return;
      }
      if (mod && (key === '=' || key === '+')) {
        e.preventDefault();
        zoomTo(s.zoom * 1.2);
        return;
      }
      if (mod && key === '-') {
        e.preventDefault();
        zoomTo(s.zoom / 1.2);
        return;
      }
      if (mod && key === '0') {
        e.preventDefault();
        zoomTo(1);
        return;
      }
      if (e.shiftKey && key === '!') {
        fitToScreen();
        return;
      }
      if (key === 'escape') {
        if (s.previewMode) s.setPreviewMode(false);
        else if (s.editingGroupId) s.setEditingGroup(null);
        else s.clearSelection();
        return;
      }
      if ((key === 'delete' || key === 'backspace') && ids.length) {
        e.preventDefault();
        if (useSettingsStore.getState().confirmDelete && !confirm(`Delete ${ids.length} layer(s)?`)) return;
        s.removeElements(ids);
        return;
      }
      if (!mod && key === 'v') s.setTool('select');
      if (!mod && key === 'h') s.setTool('hand');
      if (!mod && key === 'p') s.setPreviewMode(!s.previewMode);
      if (key.startsWith('arrow') && ids.length) {
        e.preventDefault();
        const step = e.shiftKey ? 10 : 1;
        const dx = key === 'arrowleft' ? -step : key === 'arrowright' ? step : 0;
        const dy = key === 'arrowup' ? -step : key === 'arrowdown' ? step : 0;
        s.updateElements(
          ids.map((id) => {
            const el = s.doc.elements.find((x) => x.id === id)!;
            return { id, patch: { x: el.x + dx, y: el.y + dy } };
          }),
          'nudge',
        );
      }
      if (mod && key === ']') {
        e.preventDefault();
        ids.forEach((id) => s.moveLayer(id, e.shiftKey ? 'top' : 'up'));
      }
      if (mod && key === '[') {
        e.preventDefault();
        ids.forEach((id) => s.moveLayer(id, e.shiftKey ? 'bottom' : 'down'));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}
