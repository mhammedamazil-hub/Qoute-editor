import { useState, type DragEvent } from 'react';
import { ChevronDown, ChevronRight, ChevronUp, ChevronDown as ChevronDownIcon, Copy, Eye, EyeOff, Group as GroupIcon, Image as ImageIcon, Lock, LockOpen, Sparkles, Sun, Trash2, Type, Quote, Shapes, Layers as LayersIcon, Blend, Ungroup } from 'lucide-react';
import type { AnyElement } from '@/types/elements';
import { BACKGROUND_ID, useEditorStore } from '@/store/editorStore';
import { cn } from '@/utils/cn';

function typeIcon(el: AnyElement) {
  switch (el.type) {
    case 'text': return <Type size={12} />;
    case 'quoteMark': return <Quote size={12} />;
    case 'shape': return <Shapes size={12} />;
    case 'light': return <Sun size={12} />;
    case 'gradient': return <Blend size={12} />;
    case 'image': return <ImageIcon size={12} />;
    case 'particles': return <Sparkles size={12} />;
    case 'group': return <GroupIcon size={12} />;
  }
}

export function LayerPanel() {
  const elements = useEditorStore((s) => s.doc.elements);
  const selectedIds = useEditorStore((s) => s.selectedIds);
  const editingGroupId = useEditorStore((s) => s.editingGroupId);
  const { select, updateElement, removeElements, duplicateElements, reorderElement, moveLayer, setEditingGroup, groupSelected, ungroupSelected } = useEditorStore.getState();
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [renaming, setRenaming] = useState<string | null>(null);

  // Top of the list = top of the z-order
  const topLevel = [...elements].filter((e) => !e.parentId).reverse();

  const onDrop = (e: DragEvent, targetId: string) => {
    e.preventDefault();
    if (!dragId || dragId === targetId) return;
    const dragged = elements.find((x) => x.id === dragId);
    const target = elements.find((x) => x.id === targetId);
    if (!dragged || !target || dragged.parentId !== target.parentId) return;
    const targetIndex = elements.findIndex((x) => x.id === targetId);
    reorderElement(dragId, targetIndex);
    setDragId(null);
    setOverId(null);
  };

  const row = (el: AnyElement, depth: number) => {
    const selected = selectedIds.includes(el.id);
    const isGroup = el.type === 'group';
    const children = isGroup ? [...elements].filter((c) => c.parentId === el.id).reverse() : [];
    const isCollapsed = collapsed.has(el.id);
    return (
      <div key={el.id}>
        <div
          role="option"
          aria-selected={selected}
          tabIndex={0}
          draggable
          onDragStart={() => setDragId(el.id)}
          onDragOver={(e) => { e.preventDefault(); setOverId(el.id); }}
          onDragLeave={() => setOverId(null)}
          onDrop={(e) => onDrop(e, el.id)}
          onDragEnd={() => { setDragId(null); setOverId(null); }}
          onClick={(e) => {
            if (el.parentId) setEditingGroup(el.parentId);
            else if (editingGroupId) setEditingGroup(null);
            select([el.id], e.shiftKey || e.metaKey || e.ctrlKey);
          }}
          onDoubleClick={() => setRenaming(el.id)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') select([el.id]);
            if (e.key === 'Delete' || e.key === 'Backspace') removeElements([el.id]);
          }}
          className={cn(
            'group flex h-8 cursor-pointer items-center gap-1.5 border-l-2 pr-1 text-[12px] transition-colors',
            selected ? 'border-accent bg-accent-soft text-ink-100' : 'border-transparent text-ink-200 hover:bg-ink-800',
            overId === el.id && dragId !== el.id && 'border-t border-t-accent',
            !el.visible && 'opacity-50',
          )}
          style={{ paddingLeft: 8 + depth * 14 }}
        >
          {isGroup ? (
            <button type="button" className="text-ink-400" aria-label={isCollapsed ? 'Expand group' : 'Collapse group'} onClick={(e) => { e.stopPropagation(); setCollapsed((s) => { const n = new Set(s); if (n.has(el.id)) n.delete(el.id); else n.add(el.id); return n; }); }}>
              {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
            </button>
          ) : (
            <span className="w-3" />
          )}
          <span className="text-ink-400">{typeIcon(el)}</span>
          {renaming === el.id ? (
            <input
              autoFocus
              aria-label="Rename layer"
              className="h-6 min-w-0 flex-1 rounded border border-accent/60 bg-ink-800 px-1 text-[12px] outline-none"
              defaultValue={el.name}
              onClick={(e) => e.stopPropagation()}
              onBlur={(e) => { updateElement(el.id, { name: e.target.value || el.name }); setRenaming(null); }}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === 'Escape') (e.target as HTMLInputElement).blur(); }}
            />
          ) : (
            <span className="min-w-0 flex-1 truncate">{el.name}</span>
          )}
          <div className={cn('touch-visible flex items-center opacity-0 group-hover:opacity-100', (selected || el.locked || !el.visible) && 'opacity-100')}>
            {selected && (
              <>
                <button type="button" className="icon-btn h-6 w-6" title="Move up" aria-label="Move layer up" onClick={(e) => { e.stopPropagation(); moveLayer(el.id, 'up'); }}><ChevronUp size={12} /></button>
                <button type="button" className="icon-btn h-6 w-6" title="Move down" aria-label="Move layer down" onClick={(e) => { e.stopPropagation(); moveLayer(el.id, 'down'); }}><ChevronDownIcon size={12} /></button>
              </>
            )}
            <button type="button" className="icon-btn h-6 w-6" title={el.visible ? 'Hide' : 'Show'} aria-label={el.visible ? 'Hide layer' : 'Show layer'} onClick={(e) => { e.stopPropagation(); updateElement(el.id, { visible: !el.visible }); }}>{el.visible ? <Eye size={12} /> : <EyeOff size={12} />}</button>
            <button type="button" className={cn('icon-btn h-6 w-6', el.locked && 'text-accent')} title={el.locked ? 'Unlock' : 'Lock'} aria-label={el.locked ? 'Unlock layer' : 'Lock layer'} onClick={(e) => { e.stopPropagation(); updateElement(el.id, { locked: !el.locked }); }}>{el.locked ? <Lock size={12} /> : <LockOpen size={12} />}</button>
          </div>
        </div>
        {isGroup && !isCollapsed && children.map((c) => row(c, depth + 1))}
      </div>
    );
  };

  const bgSelected = selectedIds.includes(BACKGROUND_ID);
  const hasSelection = selectedIds.some((id) => id !== BACKGROUND_ID);
  const selectedGroups = elements.filter((e) => e.type === 'group' && selectedIds.includes(e.id));

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-0.5 border-b border-line px-2 py-1.5">
        <span className="mr-auto text-[11px] font-semibold uppercase tracking-wider text-ink-300">Layers</span>
        <button className="icon-btn h-7 w-7" title="Group (Ctrl+G)" aria-label="Group" disabled={selectedIds.filter((i) => i !== BACKGROUND_ID).length < 2} onClick={groupSelected}><GroupIcon size={13} /></button>
        <button className="icon-btn h-7 w-7" title="Ungroup" aria-label="Ungroup" disabled={!selectedGroups.length} onClick={ungroupSelected}><Ungroup size={13} /></button>
        <button className="icon-btn h-7 w-7" title="Duplicate (Ctrl+D)" aria-label="Duplicate" disabled={!hasSelection} onClick={() => duplicateElements(selectedIds.filter((i) => i !== BACKGROUND_ID))}><Copy size={13} /></button>
        <button className="icon-btn h-7 w-7 hover:text-red-400" title="Delete" aria-label="Delete" disabled={!hasSelection} onClick={() => removeElements(selectedIds.filter((i) => i !== BACKGROUND_ID))}><Trash2 size={13} /></button>
      </div>
      <div role="listbox" aria-label="Layers" className="min-h-0 flex-1 overflow-y-auto py-1">
        {topLevel.length === 0 && (
          <div className="px-3 py-6 text-center text-[11px] text-ink-400">
            <LayersIcon size={18} className="mx-auto mb-2 opacity-50" />
            No layers yet. Add text, lights, shapes or images from the toolbar.
          </div>
        )}
        {topLevel.map((el) => row(el, 0))}
        <div
          role="option"
          aria-selected={bgSelected}
          tabIndex={0}
          onClick={() => select([BACKGROUND_ID])}
          onKeyDown={(e) => e.key === 'Enter' && select([BACKGROUND_ID])}
          className={cn('mt-1 flex h-8 cursor-pointer items-center gap-1.5 border-l-2 border-t border-t-line pl-2 pr-1 text-[12px]', bgSelected ? 'border-l-accent bg-accent-soft' : 'border-l-transparent text-ink-200 hover:bg-ink-800')}
        >
          <span className="w-3" />
          <span className="h-3 w-3 rounded-sm border border-line bg-ink-950" />
          <span className="flex-1">Background</span>
        </div>
      </div>
    </div>
  );
}
