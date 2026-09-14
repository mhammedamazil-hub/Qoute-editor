import { ArrowDownToLine, ArrowUpToLine, Copy, Group, Layers, SlidersHorizontal, Trash2, Ungroup } from 'lucide-react';
import { BACKGROUND_ID, useEditorStore } from '@/store/editorStore';
import { cn } from '@/utils/cn';

/**
 * Contextual quick actions for the current selection.
 * Floats over the canvas on every device so the most common edits are one tap.
 */
export function SelectionToolbar({ compact = false }: { compact?: boolean }) {
  const selectedIds = useEditorStore((s) => s.selectedIds);
  const elements = useEditorStore((s) => s.doc.elements);
  const duplicate = useEditorStore((s) => s.duplicateElements);
  const remove = useEditorStore((s) => s.removeElements);
  const moveLayer = useEditorStore((s) => s.moveLayer);
  const group = useEditorStore((s) => s.groupSelected);
  const ungroup = useEditorStore((s) => s.ungroupSelected);
  const setRightTab = useEditorStore((s) => s.setRightTab);
  const setMobileSheet = useEditorStore((s) => s.setMobileSheet);
  const clearSelection = useEditorStore((s) => s.clearSelection);

  const ids = selectedIds.filter((id) => id !== BACKGROUND_ID);
  if (!ids.length) return null;
  const selected = elements.filter((e) => ids.includes(e.id));
  const hasGroup = selected.some((e) => e.type === 'group');
  const canGroup = selected.filter((e) => !e.parentId && e.type !== 'group').length > 1;

  const Btn = ({ label, onClick, children, danger }: { label: string; onClick: () => void; children: React.ReactNode; danger?: boolean }) => (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className={cn(
        'flex items-center justify-center rounded-md text-ink-200 transition-colors hover:bg-ink-700 hover:text-ink-100',
        compact ? 'h-9 w-9' : 'h-7 w-7',
        danger && 'hover:bg-red-500/20 hover:text-red-300',
      )}
    >
      {children}
    </button>
  );

  return (
    <div className="pointer-events-auto absolute bottom-2 left-1/2 z-20 -translate-x-1/2">
      <div className="flex items-center gap-0.5 rounded-xl border border-line px-1 py-1 shadow-lg glass">
        <Btn label="Open properties" onClick={() => { setRightTab('properties'); setMobileSheet('properties'); }}>
          <SlidersHorizontal size={compact ? 16 : 14} />
        </Btn>
        <Btn label="Duplicate (⌘D)" onClick={() => duplicate(ids)}>
          <Copy size={compact ? 16 : 14} />
        </Btn>
        <Btn label="Bring to front (⌘⇧])" onClick={() => ids.forEach((id) => moveLayer(id, 'top'))}>
          <ArrowUpToLine size={compact ? 16 : 14} />
        </Btn>
        <Btn label="Send to back (⌘⇧[)" onClick={() => ids.forEach((id) => moveLayer(id, 'bottom'))}>
          <ArrowDownToLine size={compact ? 16 : 14} />
        </Btn>
        {canGroup && (
          <Btn label="Group (⌘G)" onClick={group}>
            <Group size={compact ? 16 : 14} />
          </Btn>
        )}
        {hasGroup && (
          <Btn label="Ungroup (⇧⌘G)" onClick={ungroup}>
            <Ungroup size={compact ? 16 : 14} />
          </Btn>
        )}
        <span className="mx-0.5 h-5 w-px bg-line" />
        <Btn label="Layers panel" onClick={() => { setRightTab('layers'); setMobileSheet('layers'); }}>
          <Layers size={compact ? 16 : 14} />
        </Btn>
        <Btn
          label="Delete"
          danger
          onClick={() => {
            remove(ids);
            clearSelection();
          }}
        >
          <Trash2 size={compact ? 16 : 14} />
        </Btn>
      </div>
    </div>
  );
}
