import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import Konva from 'konva';
import { Stage, Layer, Group, Rect, Line, Transformer } from 'react-konva';
import type { AnyElement, TextElement } from '@/types/elements';
import { BACKGROUND_ID, useEditorStore } from '@/store/editorStore';
import { useSettingsStore } from '@/store/settingsStore';
import { toast } from '@/store/uiStore';
import { createImage } from '@/engine/elements/factory';
import { decodeUpload } from '@/engine/masking/imageProcessor';
import { registerStage, CONTENT_GROUP_NAME } from '@/engine/canvas/stageRegistry';
import { computeSnap } from '@/engine/canvas/snapping';
import { cn } from '@/utils/cn';
import { ElementNode, ELEMENT_CLASS } from './ElementNode';
import { BackgroundNode, BACKGROUND_NODE_NAME } from './BackgroundNode';

interface CanvasEditorProps {
  interactive?: boolean;
  fitPadding?: number;
}

function GuidesLayer({ zoom, pan, canvasW, canvasH }: { zoom: number; pan: { x: number; y: number }; canvasW: number; canvasH: number }) {
  const guides = useEditorStore((s) => s.guides);
  if (!guides.length) return null;
  return (
    <Layer listening={false}>
      {guides.map((g, i) =>
        g.orientation === 'v' ? (
          <Line key={i} points={[pan.x + g.position * zoom, pan.y - 20, pan.x + g.position * zoom, pan.y + canvasH * zoom + 20]} stroke="#d9a441" strokeWidth={1} dash={[4, 4]} />
        ) : (
          <Line key={i} points={[pan.x - 20, pan.y + g.position * zoom, pan.x + canvasW * zoom + 20, pan.y + g.position * zoom]} stroke="#d9a441" strokeWidth={1} dash={[4, 4]} />
        ),
      )}
    </Layer>
  );
}

export function useFitToScreen(containerRef: React.RefObject<HTMLDivElement | null>, padding = 48) {
  return useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const { doc, setZoom } = useEditorStore.getState();
    const w = el.clientWidth, h = el.clientHeight;
    const zoom = Math.min((w - padding * 2) / doc.canvas.width, (h - padding * 2) / doc.canvas.height);
    const z = Math.max(0.02, zoom);
    setZoom(z, { x: (w - doc.canvas.width * z) / 2, y: (h - doc.canvas.height * z) / 2 });
  }, [containerRef, padding]);
}

export function CanvasEditor({ interactive = true, fitPadding = 48 }: CanvasEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const trRef = useRef<Konva.Transformer>(null);
  const [size, setSize] = useState({ width: 300, height: 300 });
  const [editingText, setEditingText] = useState<{ id: string; value: string } | null>(null);

  const doc = useEditorStore((s) => s.doc);
  const zoom = useEditorStore((s) => s.zoom);
  const pan = useEditorStore((s) => s.pan);
  const tool = useEditorStore((s) => s.tool);
  const selectedIds = useEditorStore((s) => s.selectedIds);
  const editingGroupId = useEditorStore((s) => s.editingGroupId);
  const backdrop = useSettingsStore((s) => s.canvasBackdrop);
  const handleSize = useSettingsStore((s) => s.handleSize);

  const fit = useFitToScreen(containerRef, fitPadding);
  const [dropActive, setDropActive] = useState(false);

  /** Adds an image file to the scene at a screen position (or centred). */
  const addImageAt = useCallback(
    async (file: File, client?: { x: number; y: number }) => {
      try {
        const { dataUrl, width, height } = await decodeUpload(file);
        const s = useEditorStore.getState();
        const assetId = s.registerAsset(dataUrl);
        const cw = s.doc.canvas.width;
        const ch = s.doc.canvas.height;
        const scale = Math.min(1, (cw * 0.7) / width, (ch * 0.7) / height);
        const w = Math.round(width * scale);
        const h = Math.round(height * scale);
        let x = (cw - w) / 2;
        let y = (ch - h) / 2;
        const rect = containerRef.current?.getBoundingClientRect();
        if (client && rect) {
          const worldX = (client.x - rect.left - s.pan.x) / s.zoom;
          const worldY = (client.y - rect.top - s.pan.y) / s.zoom;
          x = Math.round(worldX - w / 2);
          y = Math.round(worldY - h / 2);
        }
        s.addElement(createImage(assetId, width, height, { x, y, width: w, height: h }));
        toast('Image added', 'success', 'Drag the handles to resize — it stays a separate layer.');
      } catch (e) {
        toast('Could not load that image', 'error', e instanceof Error ? e.message : undefined);
      }
    },
    [],
  );

  // Paste an image straight from the clipboard anywhere in the editor.
  useEffect(() => {
    if (!interactive) return;
    const onPaste = (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile();
          if (file) {
            e.preventDefault();
            void addImageAt(file);
            return;
          }
        }
      }
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [interactive, addImageAt]);

  // Resize observer + initial fit
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setSize({ width: el.clientWidth, height: el.clientHeight });
    });
    ro.observe(el);
    setSize({ width: el.clientWidth, height: el.clientHeight });
    fit();
    return () => ro.disconnect();
  }, [fit]);

  // Refit when canvas dimensions change
  const canvasW = doc.canvas.width, canvasH = doc.canvas.height;
  useEffect(() => {
    fit();
  }, [canvasW, canvasH, fit]);

  useEffect(() => {
    if (!interactive) return;
    registerStage(stageRef.current);
    return () => registerStage(null);
  }, [interactive]);

  // Sync transformer with selection
  useEffect(() => {
    const tr = trRef.current, stage = stageRef.current;
    if (!tr || !stage) return;
    if (!interactive) {
      tr.nodes([]);
      return;
    }
    const nodes = selectedIds
      .filter((id) => id !== BACKGROUND_ID)
      .map((id) => stage.findOne(`#${id}`))
      .filter((n): n is Konva.Group => !!n && !doc.elements.find((e) => e.id === n.id())?.locked);
    tr.nodes(nodes);
    tr.forceUpdate();
    tr.getLayer()?.batchDraw();
  }, [selectedIds, doc, interactive, zoom]);

  const elementsById = useMemo(() => new Map(doc.elements.map((e) => [e.id, e])), [doc.elements]);
  const topLevel = useMemo(() => doc.elements.filter((e) => !e.parentId), [doc.elements]);
  const textOnlySelection = useMemo(() => {
    const els = selectedIds.map((id) => elementsById.get(id)).filter((e): e is AnyElement => !!e);
    return els.length > 0 && els.every((e) => e.type === 'text' || e.type === 'quoteMark');
  }, [selectedIds, elementsById]);
  const coarsePointer = useMemo(() => (typeof window !== 'undefined' ? window.matchMedia('(pointer: coarse)').matches : false), []);

  /* ---------- selection ---------- */
  const handlePointerDown = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    if (!interactive || tool === 'hand') return;
    const s = useEditorStore.getState();
    const target = e.target;
    const additive = 'shiftKey' in e.evt ? e.evt.shiftKey || e.evt.metaKey || e.evt.ctrlKey : false;
    if (target === target.getStage()) {
      s.clearSelection();
      s.setEditingGroup(null);
      return;
    }
    if (target.hasName(BACKGROUND_NODE_NAME)) {
      s.select([BACKGROUND_ID]);
      s.setEditingGroup(null);
      return;
    }
    const chain = target.findAncestors(`.${ELEMENT_CLASS}`, true) as Konva.Node[]; // closest → farthest
    if (!chain.length) return;
    let pick: string | null = null;
    if (s.editingGroupId) {
      const inside = chain.find((n) => elementsById.get(n.id())?.parentId === s.editingGroupId);
      if (inside) pick = inside.id();
      else s.setEditingGroup(null);
    }
    if (!pick) pick = chain[chain.length - 1].id();
    const el = elementsById.get(pick);
    if (!el) return;
    if (additive) s.select([pick], true);
    else if (!s.selectedIds.includes(pick)) s.select([pick]);
  };

  const handleDblClick = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    if (!interactive) return;
    const chain = e.target.findAncestors(`.${ELEMENT_CLASS}`, true) as Konva.Node[];
    if (!chain.length) return;
    const s = useEditorStore.getState();
    const outer = elementsById.get(chain[chain.length - 1].id());
    if (outer?.type === 'group') {
      const child = chain.find((n) => elementsById.get(n.id())?.parentId === outer.id);
      s.setEditingGroup(outer.id);
      if (child) s.select([child.id()]);
      return;
    }
    const el = elementsById.get(chain[0].id());
    if (el && (el.type === 'text' || el.type === 'quoteMark')) setEditingText({ id: el.id, value: el.content });
  };

  /* ---------- drag with snapping + multi-move ---------- */
  const dragStart = useRef<Map<string, { x: number; y: number }>>(new Map());
  const rafRef = useRef<number | null>(null);

  const onDragMove = useCallback((e: Konva.KonvaEventObject<DragEvent>, el: AnyElement) => {
    const s = useEditorStore.getState();
    const node = e.target as Konva.Group;
    const settings = useSettingsStore.getState();
    const stage = node.getStage();
    if (!stage) return;
    const single = s.selectedIds.length === 1;
    if (single && settings.snapping && !el.parentId && el.rotation === 0) {
      const snap = computeSnap(
        { x: node.x(), y: node.y(), w: el.width, h: el.height },
        s.doc.elements.filter((o) => o.id !== el.id),
        s.doc.canvas,
        6 / s.zoom,
      );
      node.position({ x: snap.x, y: snap.y });
      if (settings.showGuides) {
        if (rafRef.current) cancelAnimationFrame(rafRef.current);
        rafRef.current = requestAnimationFrame(() => s.setGuides(snap.guides));
      }
    }
    if (!single) {
      const start = dragStart.current;
      if (!start.has(el.id)) {
        for (const id of s.selectedIds) {
          const n = stage.findOne(`#${id}`);
          if (n) start.set(id, { x: n.x(), y: n.y() });
        }
        // record original position of the dragged node before movement
        const orig = s.doc.elements.find((x) => x.id === el.id);
        if (orig) start.set(el.id, { x: orig.x, y: orig.y });
      }
      const o = start.get(el.id)!;
      const dx = node.x() - o.x, dy = node.y() - o.y;
      for (const id of s.selectedIds) {
        if (id === el.id) continue;
        const n = stage.findOne(`#${id}`);
        const so = start.get(id);
        if (n && so) n.position({ x: so.x + dx, y: so.y + dy });
      }
    }
  }, []);

  const onDragEnd = useCallback((e: Konva.KonvaEventObject<DragEvent>, el: AnyElement) => {
    const s = useEditorStore.getState();
    const stage = e.target.getStage();
    s.setGuides([]);
    const patches: { id: string; patch: Partial<AnyElement> }[] = [];
    const ids = s.selectedIds.includes(el.id) ? s.selectedIds : [el.id];
    for (const id of ids) {
      const n = stage?.findOne(`#${id}`);
      if (n) patches.push({ id, patch: { x: Math.round(n.x() * 100) / 100, y: Math.round(n.y() * 100) / 100 } });
    }
    dragStart.current.clear();
    s.updateElements(patches);
  }, []);

  const onTransformEnd = useCallback((e: Konva.KonvaEventObject<Event>, el: AnyElement) => {
    const s = useEditorStore.getState();
    const node = e.target as Konva.Group;
    const sx = node.scaleX(), sy = node.scaleY();
    const patch: Partial<AnyElement> = { x: node.x(), y: node.y(), rotation: node.rotation() };
    if (el.type === 'group') {
      Object.assign(patch, { scaleX: sx, scaleY: sy });
    } else {
      node.scaleX(1);
      node.scaleY(1);
      if (el.type === 'text' || el.type === 'quoteMark') {
        const uniform = Math.abs(sx - sy) < 0.02;
        if (uniform) Object.assign(patch, { fontSize: Math.max(4, el.fontSize * sx), width: Math.max(10, el.width * sx) });
        else Object.assign(patch, { width: Math.max(10, el.width * sx) });
      } else {
        Object.assign(patch, { width: Math.max(1, el.width * sx), height: Math.max(1, el.height * sy) });
      }
    }
    s.updateElement(el.id, patch);
  }, []);

  /* ---------- wheel zoom / pan ---------- */
  const handleWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    const s = useEditorStore.getState();
    if (e.evt.ctrlKey || e.evt.metaKey) {
      const stage = stageRef.current;
      const pointer = stage?.getPointerPosition() ?? { x: size.width / 2, y: size.height / 2 };
      const factor = e.evt.deltaY > 0 ? 0.9 : 1.1;
      const newZoom = Math.min(8, Math.max(0.05, s.zoom * factor));
      const mouseTo = { x: (pointer.x - s.pan.x) / s.zoom, y: (pointer.y - s.pan.y) / s.zoom };
      s.setZoom(newZoom, { x: pointer.x - mouseTo.x * newZoom, y: pointer.y - mouseTo.y * newZoom });
    } else {
      s.setPan({ x: s.pan.x - e.evt.deltaX, y: s.pan.y - e.evt.deltaY });
    }
  };

  /* ---------- touch pinch / two-finger pan ---------- */
  const pinch = useRef<{ dist: number; center: { x: number; y: number }; zoom: number; pan: { x: number; y: number } } | null>(null);
  const handleTouchMove = (e: Konva.KonvaEventObject<TouchEvent>) => {
    const t = e.evt.touches;
    if (t.length !== 2) return;
    e.evt.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;
    if (stage.isDragging()) stage.stopDrag();
    stage.find(`.${ELEMENT_CLASS}`).forEach((n) => {
      if (n.isDragging()) n.stopDrag();
    });
    const s = useEditorStore.getState();
    const rect = stage.container().getBoundingClientRect();
    const p1 = { x: t[0].clientX - rect.left, y: t[0].clientY - rect.top };
    const p2 = { x: t[1].clientX - rect.left, y: t[1].clientY - rect.top };
    const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
    const center = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
    if (!pinch.current) {
      pinch.current = { dist, center, zoom: s.zoom, pan: s.pan };
      return;
    }
    const start = pinch.current;
    const newZoom = Math.min(8, Math.max(0.05, start.zoom * (dist / start.dist)));
    const worldCenter = { x: (start.center.x - start.pan.x) / start.zoom, y: (start.center.y - start.pan.y) / start.zoom };
    s.setZoom(newZoom, { x: center.x - worldCenter.x * newZoom, y: center.y - worldCenter.y * newZoom });
  };
  const handleTouchEnd = () => {
    pinch.current = null;
  };

  /* ---------- inline text editing ---------- */
  const editingEl = editingText ? (elementsById.get(editingText.id) as TextElement | undefined) : undefined;
  const commitText = () => {
    if (editingText && editingEl && editingText.value !== editingEl.content) {
      useEditorStore.getState().updateElement(editingText.id, { content: editingText.value } as Partial<AnyElement>);
    }
    setEditingText(null);
  };

  const backdropColor = backdrop === 'black' ? '#000000' : backdrop === 'gray' ? '#1b1e23' : '#0b0c0f';

  return (
    <div
      ref={containerRef}
      className={cn('relative h-full w-full overflow-hidden no-touch-action', dropActive && 'ring-2 ring-inset ring-accent')}
      style={{ background: backdropColor }}
      onDragOver={(e) => {
        if (!interactive) return;
        if (Array.from(e.dataTransfer.types).includes('Files')) {
          e.preventDefault();
          setDropActive(true);
        }
      }}
      onDragLeave={() => setDropActive(false)}
      onDrop={(e) => {
        if (!interactive) return;
        e.preventDefault();
        setDropActive(false);
        const file = Array.from(e.dataTransfer.files).find((f) => f.type.startsWith('image/'));
        if (file) void addImageAt(file, { x: e.clientX, y: e.clientY });
      }}
    >
      {dropActive && (
        <div className="pointer-events-none absolute inset-3 z-30 flex items-center justify-center rounded-xl border-2 border-dashed border-accent/70 bg-accent-soft text-[12px] font-medium text-ink-100">
          Drop an image to place it on the canvas
        </div>
      )}
      <Stage
        ref={stageRef}
        width={size.width}
        height={size.height}
        draggable={interactive && tool === 'hand'}
        onDragEnd={(e) => {
          if (e.target === stageRef.current) {
            const st = stageRef.current!;
            const s = useEditorStore.getState();
            const dx = st.x(), dy = st.y();
            st.position({ x: 0, y: 0 });
            s.setPan({ x: s.pan.x + dx, y: s.pan.y + dy });
          }
        }}
        onMouseDown={handlePointerDown}
        onTouchStart={handlePointerDown}
        onDblClick={handleDblClick}
        onDblTap={handleDblClick}
        onWheel={handleWheel}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={{ cursor: tool === 'hand' ? 'grab' : 'default' }}
      >
        <Layer>
          {/* canvas shadow */}
          <Rect x={pan.x} y={pan.y} width={canvasW * zoom} height={canvasH * zoom} fill="#000" shadowColor="#000" shadowBlur={40} shadowOpacity={0.6} listening={false} />
          <Group name={CONTENT_GROUP_NAME} x={pan.x} y={pan.y} scaleX={zoom} scaleY={zoom} clipX={0} clipY={0} clipWidth={canvasW} clipHeight={canvasH}>
            <BackgroundNode width={canvasW} height={canvasH} fill={doc.canvas.background} />
            {topLevel.map((el) => (
              <ElementNode
                key={el.id}
                el={el}
                allElements={doc.elements}
                children={el.type === 'group' ? doc.elements.filter((c) => c.parentId === el.id) : undefined}
                interactive={interactive && tool === 'select'}
                isSelected={selectedIds.includes(el.id)}
                editingGroupId={editingGroupId}
                onDragMove={onDragMove}
                onDragEnd={onDragEnd}
                onTransformEnd={onTransformEnd}
              />
            ))}
          </Group>
        </Layer>
        <GuidesLayer zoom={zoom} pan={pan} canvasW={canvasW} canvasH={canvasH} />
        {interactive && (
          <Layer>
            <Transformer
              ref={trRef}
              rotateEnabled
              rotationSnaps={[0, 45, 90, 135, 180, 225, 270, 315]}
              rotationSnapTolerance={4}
              anchorSize={coarsePointer ? handleSize + 6 : handleSize}
              anchorCornerRadius={2}
              keepRatio={textOnlySelection}
              enabledAnchors={textOnlySelection ? ['top-left', 'top-right', 'bottom-left', 'bottom-right', 'middle-left', 'middle-right'] : undefined}
              anchorStroke="#d9a441"
              anchorFill="#0b0c0f"
              anchorStrokeWidth={1.5}
              borderStroke="#d9a441"
              borderStrokeWidth={1}
              rotateAnchorOffset={28}
              ignoreStroke
              flipEnabled={false}
              boundBoxFunc={(oldBox, newBox) => (newBox.width < 4 || newBox.height < 1 ? oldBox : newBox)}
              shouldOverdrawWholeArea={false}
            />
          </Layer>
        )}
      </Stage>
      {editingText && editingEl && (
        <textarea
          autoFocus
          aria-label="Edit text"
          value={editingText.value}
          onChange={(e) => setEditingText({ id: editingText.id, value: e.target.value })}
          onBlur={commitText}
          onKeyDown={(e) => {
            if (e.key === 'Escape' || (e.key === 'Enter' && (e.metaKey || e.ctrlKey))) {
              e.preventDefault();
              commitText();
            }
          }}
          className="absolute resize-none border border-accent bg-black/60 p-0 text-ink-100 outline-none"
          style={{
            left: pan.x + editingEl.x * zoom,
            top: pan.y + editingEl.y * zoom,
            width: editingEl.width * zoom + 4,
            minHeight: Math.max(40, editingEl.height * zoom + 8),
            fontFamily: `"${editingEl.fontFamily}"`,
            fontSize: editingEl.fontSize * zoom,
            fontWeight: editingEl.fontWeight,
            fontStyle: editingEl.italic ? 'italic' : 'normal',
            lineHeight: editingEl.lineHeight,
            letterSpacing: editingEl.letterSpacing * zoom,
            textAlign: editingEl.align,
            transform: `rotate(${editingEl.rotation}deg)`,
            transformOrigin: 'top left',
          }}
        />
      )}
    </div>
  );
}
