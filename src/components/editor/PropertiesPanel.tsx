import { useRef } from 'react';
import { Copy, Group as GroupIcon, Lock, Trash2, Ungroup, Unlock, Upload, X } from 'lucide-react';
import type { AnyElement, BackgroundFill, BlendMode } from '@/types/elements';
import { BLEND_MODES } from '@/types/elements';
import { CANVAS_PRESETS } from '@/types/project';
import { BACKGROUND_ID, useEditorStore } from '@/store/editorStore';
import { decodeUpload } from '@/engine/masking/imageProcessor';
import { makeGradient } from '@/engine/gradient';
import { EmptyState, NumberField, Row, Section, Select, Slider, Toggle, SegmentedControl } from '@/components/ui';
import { ColorField } from './ColorPicker';
import { GradientEditor } from './GradientEditor';
import { AlignmentToolbar } from './AlignmentToolbar';
import { TextControls, ShapeControls, LightControls, GradientLayerControls, ParticlesControls, ImageControls } from './ElementControls';

/* ---------- background ---------- */

export function BackgroundControls() {
  const canvas = useEditorStore((s) => s.doc.canvas);
  const setBackground = useEditorStore((s) => s.setBackground);
  const setCanvas = useEditorStore((s) => s.setCanvas);
  const registerAsset = useEditorStore((s) => s.registerAsset);
  const fileRef = useRef<HTMLInputElement>(null);
  const bg = canvas.background;
  const kind = bg.kind;

  const setKind = (k: 'solid' | 'gradient' | 'image') => {
    if (k === kind) return;
    if (k === 'solid') setBackground({ kind: 'solid', color: bg.kind === 'gradient' ? bg.gradient.stops[0].color : '#050608' });
    else if (k === 'gradient') setBackground({ kind: 'gradient', gradient: makeGradient({ type: 'radial', cx: 0.8, cy: 0.1, radius: 0.9, stops: [{ offset: 0, color: '#2a1d08', opacity: 1 }, { offset: 1, color: '#050608', opacity: 1 }] }) });
    else fileRef.current?.click();
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    try {
      const { dataUrl } = await decodeUpload(file);
      const assetId = registerAsset(dataUrl);
      setBackground({ kind: 'image', assetId } as BackgroundFill);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to load image');
    }
  };

  return (
    <>
      <Section title="Canvas">
        <div className="grid grid-cols-2 gap-1.5">
          <NumberField label="W" value={canvas.width} min={64} max={8000} onChange={(width) => setCanvas({ width: Math.round(width) })} />
          <NumberField label="H" value={canvas.height} min={64} max={8000} onChange={(height) => setCanvas({ height: Math.round(height) })} />
        </div>
        <Select label="Canvas preset" value={CANVAS_PRESETS.find((p) => p.width === canvas.width && p.height === canvas.height)?.id ?? 'custom'} onChange={(id) => { const p = CANVAS_PRESETS.find((x) => x.id === id); if (p) setCanvas({ width: p.width, height: p.height }); }} options={[{ value: 'custom', label: 'Custom size' }, ...CANVAS_PRESETS.map((p) => ({ value: p.id, label: `${p.label} · ${p.width}×${p.height}` }))]} />
      </Section>
      <Section title="Background">
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden onChange={(e) => void upload(e.target.files?.[0])} />
        <SegmentedControl value={kind} label="Background type" onChange={setKind} options={[{ value: 'solid', label: 'Solid' }, { value: 'gradient', label: 'Gradient' }, { value: 'image', label: 'Image' }]} />
        {bg.kind === 'solid' && <ColorField label="Color" color={bg.color} onChange={(color) => setBackground({ kind: 'solid', color })} />}
        {bg.kind === 'gradient' && <GradientEditor gradient={bg.gradient} onChange={(gradient) => setBackground({ kind: 'gradient', gradient })} />}
        {bg.kind === 'image' && <button type="button" className="btn w-full" onClick={() => fileRef.current?.click()}><Upload size={13} /> Replace background image</button>}
        <p className="text-[10px] leading-relaxed text-ink-400">Tip: add Gradient layers or Lights from the toolbar to stack multiple gradients over the background.</p>
      </Section>
    </>
  );
}

/* ---------- effects ---------- */

function EffectsPanel({ el }: { el: AnyElement }) {
  const update = useEditorStore((s) => s.updateElement);
  const patch = (p: Partial<AnyElement>, key: string) => update(el.id, p, `${el.id}:${key}`);
  return (
    <>
      <Section title="Appearance">
        <Slider label="Opacity" value={Math.round(el.opacity * 100)} min={0} max={100} onChange={(v) => patch({ opacity: v / 100 }, 'opacity')} unit="%" />
        <Row label="Blend"><Select label="Blend mode" value={el.blendMode} onChange={(blendMode: BlendMode) => patch({ blendMode }, 'blend')} options={BLEND_MODES.map((m) => ({ value: m, label: m }))} /></Row>
        {el.type !== 'light' && <Slider label="Blur" value={el.blur} min={0} max={100} onChange={(blur) => patch({ blur }, 'blur')} unit="px" />}
      </Section>
      {el.type !== 'group' && (
        <>
          <Section title="Glow" defaultOpen={el.glow.enabled} action={<Toggle checked={el.glow.enabled} onChange={(enabled) => patch({ glow: { ...el.glow, enabled } }, 'glow')} label="Enable glow" />}>
            <ColorField label="Color" color={el.glow.color} onChange={(color) => patch({ glow: { ...el.glow, color } }, 'glowc')} />
            <Slider label="Radius" value={el.glow.radius} min={0} max={200} onChange={(radius) => patch({ glow: { ...el.glow, radius } }, 'glowr')} unit="px" />
            <Slider label="Intensity" value={Math.round(el.glow.intensity * 100)} min={0} max={100} onChange={(v) => patch({ glow: { ...el.glow, intensity: v / 100 } }, 'glowi')} unit="%" />
          </Section>
          <Section title="Shadow" defaultOpen={el.shadow.enabled} action={<Toggle checked={el.shadow.enabled} onChange={(enabled) => patch({ shadow: { ...el.shadow, enabled } }, 'shadow')} label="Enable shadow" />}>
            <div className="grid grid-cols-2 gap-1.5">
              <NumberField label="X" value={el.shadow.x} onChange={(x) => patch({ shadow: { ...el.shadow, x } }, 'shx')} />
              <NumberField label="Y" value={el.shadow.y} onChange={(y) => patch({ shadow: { ...el.shadow, y } }, 'shy')} />
            </div>
            <Slider label="Blur" value={el.shadow.blur} min={0} max={200} onChange={(blur) => patch({ shadow: { ...el.shadow, blur } }, 'shb')} unit="px" />
            <ColorField label="Color" color={el.shadow.color} onChange={(color) => patch({ shadow: { ...el.shadow, color } }, 'shc')} />
            <Slider label="Opacity" value={Math.round(el.shadow.opacity * 100)} min={0} max={100} onChange={(v) => patch({ shadow: { ...el.shadow, opacity: v / 100 } }, 'sho')} unit="%" />
          </Section>
        </>
      )}
    </>
  );
}

/* ---------- transform ---------- */

function TransformSection({ el }: { el: AnyElement }) {
  const update = useEditorStore((s) => s.updateElement);
  const p = (patch: Partial<AnyElement>) => update(el.id, patch, `${el.id}:transform`);
  const isText = el.type === 'text' || el.type === 'quoteMark';
  return (
    <Section title="Transform">
      <div className="grid grid-cols-2 gap-1.5">
        <NumberField label="X" value={el.x} onChange={(x) => p({ x })} />
        <NumberField label="Y" value={el.y} onChange={(y) => p({ y })} />
        <NumberField label="W" value={el.width} min={1} onChange={(width) => p({ width })} />
        <NumberField label="H" value={el.height} min={1} onChange={(height) => !isText && p({ height })} className={isText ? 'opacity-50' : ''} />
        <NumberField label="°" value={el.rotation} onChange={(rotation) => p({ rotation })} />
        {el.type === 'group' && <NumberField label="S" value={Math.round(el.scaleX * 100) / 100} step={0.05} min={0.05} onChange={(s) => p({ scaleX: s, scaleY: s } as Partial<AnyElement>)} />}
      </div>
      <AlignmentToolbar />
    </Section>
  );
}

/* ---------- panel ---------- */

export function PropertiesPanel() {
  const selectedIds = useEditorStore((s) => s.selectedIds);
  const el = useEditorStore((s) => (s.selectedIds.length ? s.doc.elements.find((e) => e.id === s.selectedIds[0]) : undefined));
  const count = selectedIds.length;
  const { updateElement, removeElements, duplicateElements, groupSelected, ungroupSelected, clearSelection } = useEditorStore.getState();

  if (selectedIds[0] === BACKGROUND_ID) return <div><BackgroundControls /></div>;
  if (!el) return <EmptyState title="Nothing selected" hint="Select a layer on the canvas or in the Layers panel. Click the canvas background to edit it." />;

  if (count > 1) {
    return (
      <div>
        <div className="flex items-center justify-between border-b border-line px-3 py-2">
          <span className="text-[12px] font-medium">{count} layers selected</span>
          <button className="icon-btn h-7 w-7" onClick={clearSelection} aria-label="Clear selection"><X size={14} /></button>
        </div>
        <Section title="Arrange">
          <AlignmentToolbar />
          <div className="flex gap-1.5">
            <button type="button" className="btn flex-1" onClick={groupSelected}><GroupIcon size={13} /> Group</button>
            <button type="button" className="btn flex-1" onClick={() => duplicateElements(selectedIds)}><Copy size={13} /> Duplicate</button>
            <button type="button" className="btn" onClick={() => removeElements(selectedIds)} aria-label="Delete"><Trash2 size={13} /></button>
          </div>
        </Section>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-1 border-b border-line px-3 py-2">
        <input aria-label="Layer name" className="h-7 min-w-0 flex-1 rounded border border-transparent bg-transparent px-1 text-[12px] font-medium outline-none hover:border-line focus:border-accent/60" value={el.name} onChange={(e) => updateElement(el.id, { name: e.target.value }, `${el.id}:name`)} />
        <button className="icon-btn h-7 w-7" title={el.locked ? 'Unlock' : 'Lock'} aria-label={el.locked ? 'Unlock' : 'Lock'} onClick={() => updateElement(el.id, { locked: !el.locked })}>{el.locked ? <Lock size={13} /> : <Unlock size={13} />}</button>
        <button className="icon-btn h-7 w-7" title="Duplicate" aria-label="Duplicate" onClick={() => duplicateElements([el.id])}><Copy size={13} /></button>
        {el.type === 'group' && <button className="icon-btn h-7 w-7" title="Ungroup" aria-label="Ungroup" onClick={ungroupSelected}><Ungroup size={13} /></button>}
        <button className="icon-btn h-7 w-7 hover:text-red-400" title="Delete" aria-label="Delete" onClick={() => removeElements([el.id])}><Trash2 size={13} /></button>
      </div>
      <TransformSection el={el} />
      {(el.type === 'text' || el.type === 'quoteMark') && <TextControls el={el} />}
      {el.type === 'shape' && <ShapeControls el={el} />}
      {el.type === 'light' && <LightControls el={el} />}
      {el.type === 'gradient' && <GradientLayerControls el={el} />}
      {el.type === 'particles' && <ParticlesControls el={el} />}
      {el.type === 'image' && <ImageControls el={el} />}
      <EffectsPanel el={el} />
    </div>
  );
}
