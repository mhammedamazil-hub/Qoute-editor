import { useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import type { Fill, GradientFill, GradientStop, GradientType } from '@/types/elements';
import { gradientToCss, makeGradient, sortedStops } from '@/engine/gradient';
import { withAlpha } from '@/engine/color';
import { ColorField } from './ColorPicker';
import { SegmentedControl, Slider } from '@/components/ui';
import { cn } from '@/utils/cn';

interface GradientEditorProps {
  gradient: GradientFill;
  onChange: (g: GradientFill) => void;
  allowConic?: boolean;
}

export function GradientEditor({ gradient, onChange, allowConic = true }: GradientEditorProps) {
  const [selected, setSelected] = useState(0);
  const barRef = useRef<HTMLDivElement>(null);
  const stops = gradient.stops;
  const sel = stops[Math.min(selected, stops.length - 1)];

  const updateStop = (idx: number, patch: Partial<GradientStop>) => onChange({ ...gradient, stops: stops.map((s, i) => (i === idx ? { ...s, ...patch } : s)) });

  const addStopAt = (offset: number) => {
    const sorted = sortedStops(stops);
    const after = sorted.find((s) => s.offset >= offset) ?? sorted[sorted.length - 1];
    const next: GradientStop = { offset, color: after.color, opacity: after.opacity };
    onChange({ ...gradient, stops: [...stops, next] });
    setSelected(stops.length);
  };

  const removeStop = (idx: number) => {
    if (stops.length <= 2) return;
    onChange({ ...gradient, stops: stops.filter((_, i) => i !== idx) });
    setSelected(0);
  };

  const onBarPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    const bar = barRef.current;
    if (!bar) return;
    const r = bar.getBoundingClientRect();
    const t = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    addStopAt(Math.round(t * 100) / 100);
  };

  const onHandlePointerDown = (idx: number) => (e: ReactPointerEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setSelected(idx);
    const bar = barRef.current;
    if (!bar) return;
    const target = e.currentTarget;
    target.setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => {
      const r = bar.getBoundingClientRect();
      const t = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
      updateStop(idx, { offset: Math.round(t * 1000) / 1000 });
    };
    const up = () => {
      target.removeEventListener('pointermove', move);
      target.removeEventListener('pointerup', up);
    };
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerup', up);
  };

  const typeOptions: { value: GradientType; label: string }[] = [
    { value: 'linear', label: 'Linear' },
    { value: 'radial', label: 'Radial' },
    ...(allowConic ? [{ value: 'conic' as GradientType, label: 'Conic' }] : []),
  ];

  return (
    <div className="space-y-2.5">
      <SegmentedControl value={gradient.type} onChange={(type) => onChange({ ...gradient, type })} options={typeOptions} label="Gradient type" />
      <div className="relative pb-3 pt-1">
        <div ref={barRef} onPointerDown={onBarPointerDown} className="checker relative h-6 w-full cursor-copy rounded-md border border-line no-touch-action" title="Click to add a stop">
          <div className="h-full w-full rounded-md" style={{ background: `linear-gradient(90deg, ${sortedStops(stops).map((s) => `${withAlpha(s.color, s.opacity)} ${s.offset * 100}%`).join(', ')})` }} />
        </div>
        {stops.map((s, i) => (
          <button
            key={i}
            type="button"
            aria-label={`Gradient stop ${i + 1}`}
            onPointerDown={onHandlePointerDown(i)}
            className={cn('absolute top-0 h-8 w-3 -translate-x-1/2 rounded-sm border-2 no-touch-action', i === selected ? 'z-10 border-accent' : 'border-white/70')}
            style={{ left: `${s.offset * 100}%`, background: s.color }}
          />
        ))}
      </div>
      {sel && (
        <div className="space-y-2 rounded-md border border-line bg-ink-850 p-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-ink-300">Stop {selected + 1} of {stops.length}</span>
            <div className="flex gap-1">
              <button type="button" className="icon-btn h-6 w-6" title="Add stop" aria-label="Add stop" onClick={() => addStopAt(Math.min(1, sel.offset + 0.1))}><Plus size={13} /></button>
              <button type="button" className="icon-btn h-6 w-6" title="Delete stop" aria-label="Delete stop" disabled={stops.length <= 2} onClick={() => removeStop(selected)}><Trash2 size={13} /></button>
            </div>
          </div>
          <ColorField label="Color" color={sel.color} onChange={(c) => updateStop(selected, { color: c })} alpha={sel.opacity} onAlphaChange={(a) => updateStop(selected, { opacity: a })} />
          <Slider label="Position" value={Math.round(sel.offset * 100)} min={0} max={100} onChange={(v) => updateStop(selected, { offset: v / 100 })} unit="%" />
          <Slider label="Opacity" value={Math.round(sel.opacity * 100)} min={0} max={100} onChange={(v) => updateStop(selected, { opacity: v / 100 })} unit="%" />
        </div>
      )}
      {gradient.type !== 'radial' && <Slider label="Angle" value={gradient.angle} min={0} max={360} onChange={(angle) => onChange({ ...gradient, angle })} unit="°" />}
      {gradient.type !== 'linear' && (
        <>
          <Slider label="Center X" value={Math.round(gradient.cx * 100)} min={-50} max={150} onChange={(v) => onChange({ ...gradient, cx: v / 100 })} unit="%" />
          <Slider label="Center Y" value={Math.round(gradient.cy * 100)} min={-50} max={150} onChange={(v) => onChange({ ...gradient, cy: v / 100 })} unit="%" />
        </>
      )}
      {gradient.type === 'radial' && <Slider label="Radius" value={Math.round(gradient.radius * 100)} min={5} max={200} onChange={(v) => onChange({ ...gradient, radius: v / 100 })} unit="%" />}
    </div>
  );
}

/** Solid / gradient fill switcher used by text, shapes and backgrounds. */
export function FillControl({ fill, onChange, allowNone, allowConic }: { fill: Fill | null; onChange: (f: Fill | null) => void; allowNone?: boolean; allowConic?: boolean }) {
  const kind = fill ? fill.kind : 'none';
  const options = [
    ...(allowNone ? [{ value: 'none', label: 'None' }] : []),
    { value: 'solid', label: 'Solid' },
    { value: 'gradient', label: 'Gradient' },
  ];
  const lastColor = fill?.kind === 'solid' ? fill.color : fill?.kind === 'gradient' ? fill.gradient.stops[0].color : '#d9a441';
  return (
    <div className="space-y-2">
      <SegmentedControl
        value={kind}
        label="Fill type"
        options={options}
        onChange={(k) => {
          if (k === 'none') onChange(null);
          else if (k === 'solid') onChange({ kind: 'solid', color: lastColor });
          else onChange({ kind: 'gradient', gradient: makeGradient({ stops: [{ offset: 0, color: lastColor, opacity: 1 }, { offset: 1, color: '#ffffff', opacity: 1 }] }) });
        }}
      />
      {fill?.kind === 'solid' && <ColorField label="Color" color={fill.color} onChange={(color) => onChange({ kind: 'solid', color })} />}
      {fill?.kind === 'gradient' && (
        <>
          <div className="h-2 w-full rounded" style={{ background: gradientToCss(fill.gradient) }} />
          <GradientEditor gradient={fill.gradient} onChange={(gradient) => onChange({ kind: 'gradient', gradient })} allowConic={allowConic} />
        </>
      )}
    </div>
  );
}
