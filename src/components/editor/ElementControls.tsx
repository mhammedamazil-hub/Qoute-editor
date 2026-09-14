import { useRef } from 'react';
import { AlignCenter, AlignLeft, AlignRight, Bold, Italic, Underline, RefreshCw, Upload } from 'lucide-react';
import type { AnyElement, ImageElement, LightElement, ParticlesElement, ShapeElement, TextElement, GradientElement, MaskType, BlendMode } from '@/types/elements';
import { BLEND_MODES } from '@/types/elements';
import { FONTS, nearestWeight } from '@/engine/fonts';
import { LIGHT_PRESETS, QUOTE_MARK_GLYPHS } from '@/engine/elements/factory';
import { decodeUpload } from '@/engine/masking/imageProcessor';
import { useEditorStore } from '@/store/editorStore';
import { Row, Section, Select, Slider, TextArea, Toggle, SegmentedControl } from '@/components/ui';
import { ColorField } from './ColorPicker';
import { FillControl, GradientEditor } from './GradientEditor';
import { cn } from '@/utils/cn';

type Patch<T> = (patch: Partial<T>, key?: string) => void;

function usePatch<T extends AnyElement>(el: T): Patch<T> {
  const update = useEditorStore((s) => s.updateElement);
  return (patch, key) => update(el.id, patch as Partial<AnyElement>, key ?? `${el.id}:${Object.keys(patch).join(',')}`);
}

/* ---------- text ---------- */

export function TextControls({ el }: { el: TextElement }) {
  const patch = usePatch(el);
  const fontDef = FONTS.find((f) => f.family === el.fontFamily);
  return (
    <>
      <Section title={el.type === 'quoteMark' ? 'Quote Mark' : 'Text'}>
        {el.type === 'quoteMark' ? (
          <div className="flex gap-1">
            {QUOTE_MARK_GLYPHS.map((g) => (
              <button key={g} type="button" onClick={() => patch({ content: g })} className={cn('flex h-9 flex-1 items-center justify-center rounded-md border text-xl', el.content === g ? 'border-accent bg-accent-soft text-accent' : 'border-line bg-ink-800 text-ink-200')} style={{ fontFamily: `"${el.fontFamily}"` }}>
                {g}
              </button>
            ))}
          </div>
        ) : (
          <TextArea label="Text content" value={el.content} rows={4} onChange={(content) => patch({ content })} />
        )}
        <Row label="Font">
          <Select label="Font family" value={el.fontFamily} onChange={(fontFamily) => patch({ fontFamily, fontWeight: nearestWeight(fontFamily, el.fontWeight) })} options={FONTS.map((f) => ({ value: f.family, label: f.family }))} />
        </Row>
        <Row label="Weight">
          <Select label="Font weight" value={String(el.fontWeight)} onChange={(w) => patch({ fontWeight: parseInt(w, 10) })} options={(fontDef?.weights ?? [400, 700]).map((w) => ({ value: String(w), label: String(w) }))} />
          <div className="flex gap-0.5">
            <button type="button" className={cn('icon-btn h-7 w-7', el.fontWeight >= 700 && 'active')} title="Bold" aria-label="Bold" onClick={() => patch({ fontWeight: el.fontWeight >= 700 ? nearestWeight(el.fontFamily, 400) : nearestWeight(el.fontFamily, 700) })}><Bold size={14} /></button>
            <button type="button" className={cn('icon-btn h-7 w-7', el.italic && 'active')} title="Italic" aria-label="Italic" onClick={() => patch({ italic: !el.italic })}><Italic size={14} /></button>
            <button type="button" className={cn('icon-btn h-7 w-7', el.underline && 'active')} title="Underline" aria-label="Underline" onClick={() => patch({ underline: !el.underline })}><Underline size={14} /></button>
          </div>
        </Row>
        <Slider label="Size" value={el.fontSize} min={4} max={600} onChange={(fontSize) => patch({ fontSize }, `${el.id}:fontSize`)} unit="px" />
        <Slider label="Letter spacing" value={el.letterSpacing} min={-20} max={80} step={0.5} onChange={(letterSpacing) => patch({ letterSpacing }, `${el.id}:ls`)} />
        <Slider label="Line height" value={el.lineHeight} min={0.6} max={3} step={0.05} onChange={(lineHeight) => patch({ lineHeight }, `${el.id}:lh`)} />
        <Row label="Align">
          <SegmentedControl
            value={el.align}
            label="Text alignment"
            onChange={(align) => patch({ align })}
            options={[
              { value: 'left', label: <AlignLeft size={14} />, title: 'Left' },
              { value: 'center', label: <AlignCenter size={14} />, title: 'Center' },
              { value: 'right', label: <AlignRight size={14} />, title: 'Right' },
            ]}
          />
        </Row>
      </Section>
      <Section title="Fill">
        <FillControl fill={el.fill} onChange={(fill) => fill && patch({ fill }, `${el.id}:fill`)} allowConic={false} />
      </Section>
      <Section title="Stroke" defaultOpen={el.strokeWidth > 0}>
        <ColorField label="Color" color={el.stroke} onChange={(stroke) => patch({ stroke }, `${el.id}:stroke`)} />
        <Slider label="Width" value={el.strokeWidth} min={0} max={20} step={0.5} onChange={(strokeWidth) => patch({ strokeWidth }, `${el.id}:sw`)} />
      </Section>
    </>
  );
}

/* ---------- shape ---------- */

export function ShapeControls({ el }: { el: ShapeElement }) {
  const patch = usePatch(el);
  const isLine = el.shape === 'line' || el.shape === 'arrow';
  return (
    <>
      <Section title="Shape">
        {el.shape === 'roundedRect' && <Slider label="Corner radius" value={el.cornerRadius} min={0} max={Math.min(el.width, el.height) / 2} onChange={(cornerRadius) => patch({ cornerRadius }, `${el.id}:cr`)} />}
        {(el.shape === 'polygon' || el.shape === 'star') && <Slider label="Sides / Points" value={el.sides} min={3} max={16} onChange={(sides) => patch({ sides })} />}
        {el.shape === 'star' && <Slider label="Inner radius" value={Math.round(el.innerRatio * 100)} min={5} max={95} onChange={(v) => patch({ innerRatio: v / 100 }, `${el.id}:ir`)} unit="%" />}
        {el.shape === 'ring' && <Slider label="Thickness" value={Math.round((1 - el.innerRatio) * 100)} min={1} max={100} onChange={(v) => patch({ innerRatio: 1 - v / 100 }, `${el.id}:ir`)} unit="%" />}
        {el.shape === 'arc' && <Slider label="Sweep" value={el.arcAngle} min={10} max={360} onChange={(arcAngle) => patch({ arcAngle }, `${el.id}:arc`)} unit="°" />}
        {(el.shape === 'grid' || el.shape === 'dots' || el.shape === 'cornerFrame') && <Slider label={el.shape === 'cornerFrame' ? 'Corner length' : 'Spacing'} value={el.spacing} min={4} max={400} onChange={(spacing) => patch({ spacing }, `${el.id}:sp`)} />}
        <Row label="Dashed"><Toggle checked={el.dashed} onChange={(dashed) => patch({ dashed })} label="Dashed stroke" /></Row>
      </Section>
      {!isLine && el.shape !== 'grid' && el.shape !== 'cornerFrame' && el.shape !== 'crosshair' && el.shape !== 'plus' && el.shape !== 'arc' && (
        <Section title="Fill">
          <FillControl fill={el.fill} onChange={(fill) => patch({ fill }, `${el.id}:fill`)} allowNone allowConic={false} />
        </Section>
      )}
      <Section title="Stroke">
        <ColorField label="Color" color={el.stroke} onChange={(stroke) => patch({ stroke }, `${el.id}:stroke`)} />
        <Slider label="Width" value={el.strokeWidth} min={0} max={60} step={0.5} onChange={(strokeWidth) => patch({ strokeWidth }, `${el.id}:sw`)} />
      </Section>
    </>
  );
}

/* ---------- light ---------- */

export function LightControls({ el }: { el: LightElement }) {
  const patch = usePatch(el);
  return (
    <Section title="Light">
      <div className="flex flex-wrap gap-1">
        {LIGHT_PRESETS.map((p) => (
          <button key={p.id} type="button" title={p.label} aria-label={`${p.label} light`} onClick={() => patch({ color: p.color, name: `${p.label} Light` })} className={cn('h-6 w-6 rounded-full border-2', el.color === p.color ? 'border-white' : 'border-transparent')} style={{ background: p.color, boxShadow: `0 0 12px ${p.color}66` }} />
        ))}
      </div>
      <ColorField label="Color" color={el.color} onChange={(color) => patch({ color }, `${el.id}:color`)} />
      <Slider label="Intensity" value={Math.round(el.intensity * 100)} min={0} max={100} onChange={(v) => patch({ intensity: v / 100 }, `${el.id}:int`)} unit="%" />
      <Slider label="Radius" value={Math.round(el.width / 2)} min={20} max={3000} onChange={(r) => { const cx = el.x + el.width / 2, cy = el.y + el.height / 2; patch({ width: r * 2, height: r * 2 * (el.height / el.width), x: cx - r, y: cy - r * (el.height / el.width) }, `${el.id}:radius`); }} unit="px" />
      <Slider label="Softness" value={Math.round(el.softness * 100)} min={0} max={100} onChange={(v) => patch({ softness: v / 100 }, `${el.id}:soft`)} unit="%" />
      <Slider label="Blur" value={el.blur} min={0} max={120} onChange={(blur) => patch({ blur }, `${el.id}:blur`)} unit="px" />
      <Row label="Blend"><Select label="Blend mode" value={el.blendMode} onChange={(blendMode: BlendMode) => patch({ blendMode })} options={BLEND_MODES.map((m) => ({ value: m, label: m }))} /></Row>
    </Section>
  );
}

/* ---------- gradient layer ---------- */

export function GradientLayerControls({ el }: { el: GradientElement }) {
  const patch = usePatch(el);
  return (
    <Section title="Gradient">
      <GradientEditor gradient={el.gradient} onChange={(gradient) => patch({ gradient }, `${el.id}:grad`)} />
    </Section>
  );
}

/* ---------- particles ---------- */

export function ParticlesControls({ el }: { el: ParticlesElement }) {
  const patch = usePatch(el);
  return (
    <Section title="Particles">
      <ColorField label="Color" color={el.color} onChange={(color) => patch({ color }, `${el.id}:color`)} />
      <Slider label="Count" value={el.count} min={1} max={600} onChange={(count) => patch({ count }, `${el.id}:count`)} />
      <Slider label="Min size" value={el.minSize} min={0.5} max={20} step={0.5} onChange={(minSize) => patch({ minSize: Math.min(minSize, el.maxSize) }, `${el.id}:min`)} />
      <Slider label="Max size" value={el.maxSize} min={0.5} max={40} step={0.5} onChange={(maxSize) => patch({ maxSize: Math.max(maxSize, el.minSize) }, `${el.id}:max`)} />
      <button type="button" className="btn w-full" onClick={() => patch({ seed: Math.floor(Math.random() * 100000) })}><RefreshCw size={13} /> Shuffle positions</button>
    </Section>
  );
}

/* ---------- image ---------- */

const MASK_TYPES: { value: MaskType; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'rect', label: 'Rect' },
  { value: 'roundedRect', label: 'Rounded' },
  { value: 'circle', label: 'Circle' },
  { value: 'ellipse', label: 'Ellipse' },
  { value: 'linear', label: 'Gradient' },
];

export function ImageControls({ el }: { el: ImageElement }) {
  const patch = usePatch(el);
  const registerAsset = useEditorStore((s) => s.registerAsset);
  const fileRef = useRef<HTMLInputElement>(null);
  const a = el.adjustments;
  const adj = (k: keyof ImageElement['adjustments'], v: number) => patch({ adjustments: { ...a, [k]: v } }, `${el.id}:adj:${k}`);
  const mask = (p: Partial<ImageElement['mask']>) => patch({ mask: { ...el.mask, ...p } }, `${el.id}:mask:${Object.keys(p).join()}`);
  const crop = (p: Partial<ImageElement['crop']>) => {
    const next = { ...el.crop, ...p };
    next.w = Math.min(next.w, 1 - next.x);
    next.h = Math.min(next.h, 1 - next.y);
    patch({ crop: next }, `${el.id}:crop`);
  };

  const replace = async (file: File | undefined) => {
    if (!file) return;
    try {
      const { dataUrl, width, height } = await decodeUpload(file);
      const id = registerAsset(dataUrl);
      patch({ assetId: id, naturalWidth: width, naturalHeight: height, crop: { x: 0, y: 0, w: 1, h: 1 } });
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to load image');
    }
  };

  const cropZoom = 1 / Math.max(el.crop.w, el.crop.h);

  return (
    <>
      <Section title="Image">
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden onChange={(e) => void replace(e.target.files?.[0])} />
        <button type="button" className="btn w-full" onClick={() => fileRef.current?.click()}><Upload size={13} /> Replace image</button>
        <p className="text-[10px] text-ink-400">{el.naturalWidth} × {el.naturalHeight}px source. Edits are non-destructive.</p>
      </Section>
      <Section title="Crop" defaultOpen={false}>
        <Slider label="Zoom" value={Math.round(cropZoom * 100)} min={100} max={400} onChange={(z) => {
          const size = 1 / (z / 100);
          const cx = el.crop.x + el.crop.w / 2, cy = el.crop.y + el.crop.h / 2;
          const w = Math.min(1, size), h = Math.min(1, size);
          crop({ w, h, x: Math.min(1 - w, Math.max(0, cx - w / 2)), y: Math.min(1 - h, Math.max(0, cy - h / 2)) });
        }} unit="%" />
        <Slider label="Offset X" value={Math.round((el.crop.x / Math.max(0.0001, 1 - el.crop.w)) * 100) || 0} min={0} max={100} onChange={(v) => crop({ x: (v / 100) * (1 - el.crop.w) })} unit="%" />
        <Slider label="Offset Y" value={Math.round((el.crop.y / Math.max(0.0001, 1 - el.crop.h)) * 100) || 0} min={0} max={100} onChange={(v) => crop({ y: (v / 100) * (1 - el.crop.h) })} unit="%" />
        <button type="button" className="btn w-full" onClick={() => patch({ crop: { x: 0, y: 0, w: 1, h: 1 } })}>Reset crop</button>
      </Section>
      <Section title="Mask">
        <Select label="Mask type" value={el.mask.type} onChange={(type: MaskType) => mask({ type })} options={MASK_TYPES} />
        {el.mask.type !== 'none' && (
          <>
            <Slider label="Feather" value={Math.round(el.mask.feather * 100)} min={0} max={100} onChange={(v) => mask({ feather: v / 100 })} unit="%" />
            <div className="flex gap-1">
              {[0, 10, 20, 30, 50, 75, 100].map((p) => (
                <button key={p} type="button" onClick={() => mask({ feather: p / 100 })} className={cn('flex-1 rounded border py-1 text-[10px]', Math.round(el.mask.feather * 100) === p ? 'border-accent text-accent' : 'border-line text-ink-300')}>{p}%</button>
              ))}
            </div>
            {el.mask.type === 'roundedRect' && <Slider label="Corner" value={Math.round(el.mask.cornerRadius * 100)} min={0} max={100} onChange={(v) => mask({ cornerRadius: v / 100 })} unit="%" />}
            {el.mask.type === 'linear' && <Slider label="Angle" value={el.mask.angle} min={0} max={360} onChange={(angle) => mask({ angle })} unit="°" />}
            <Slider label="Mask X" value={Math.round(el.mask.x * 100)} min={-50} max={100} onChange={(v) => mask({ x: v / 100 })} unit="%" />
            <Slider label="Mask Y" value={Math.round(el.mask.y * 100)} min={-50} max={100} onChange={(v) => mask({ y: v / 100 })} unit="%" />
            <Slider label="Mask width" value={Math.round(el.mask.w * 100)} min={5} max={200} onChange={(v) => mask({ w: v / 100 })} unit="%" />
            <Slider label="Mask height" value={Math.round(el.mask.h * 100)} min={5} max={200} onChange={(v) => mask({ h: v / 100 })} unit="%" />
            <Row label="Invert"><Toggle checked={el.mask.invert} onChange={(invert) => mask({ invert })} label="Invert mask" /></Row>
          </>
        )}
      </Section>
      <Section title="Adjustments">
        <Slider label="Brightness" value={Math.round(a.brightness * 100)} min={-100} max={100} onChange={(v) => adj('brightness', v / 100)} />
        <Slider label="Contrast" value={Math.round(a.contrast * 100)} min={-100} max={100} onChange={(v) => adj('contrast', v / 100)} />
        <Slider label="Saturation" value={Math.round(a.saturation * 100)} min={-100} max={100} onChange={(v) => adj('saturation', v / 100)} />
        <Slider label="Hue" value={a.hue} min={-180} max={180} onChange={(v) => adj('hue', v)} unit="°" />
        <Slider label="Exposure" value={Math.round(a.exposure * 100)} min={-100} max={100} onChange={(v) => adj('exposure', v / 100)} />
        <Slider label="Blur" value={a.blur} min={0} max={60} onChange={(v) => adj('blur', v)} unit="px" />
        <Slider label="Grayscale" value={Math.round(a.grayscale * 100)} min={0} max={100} onChange={(v) => adj('grayscale', v / 100)} unit="%" />
        <Slider label="Sepia" value={Math.round(a.sepia * 100)} min={0} max={100} onChange={(v) => adj('sepia', v / 100)} unit="%" />
        <button type="button" className="btn w-full" onClick={() => patch({ adjustments: { brightness: 0, contrast: 0, saturation: 0, hue: 0, exposure: 0, blur: 0, grayscale: 0, sepia: 0 } })}>Reset adjustments</button>
      </Section>
    </>
  );
}
