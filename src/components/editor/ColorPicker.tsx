import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { Pipette, Star } from 'lucide-react';
import { hexToRgb, hslToRgb, hsvToRgb, normalizeHex, rgbToHex, rgbToHsl, rgbToHsv } from '@/engine/color';
import { useSettingsStore } from '@/store/settingsStore';
import { cn } from '@/utils/cn';
import { SegmentedControl } from '@/components/ui';

interface EyeDropperCtor {
  new (): { open: () => Promise<{ sRGBHex: string }> };
}

export interface ColorPickerProps {
  color: string;
  onChange: (hex: string) => void;
  alpha?: number;
  onAlphaChange?: (a: number) => void;
}

export function ColorPickerPanel({ color, onChange, alpha, onAlphaChange }: ColorPickerProps) {
  const hex = normalizeHex(color);
  const [hsv, setHsv] = useState(() => rgbToHsv(hexToRgb(hex)));
  const [mode, setMode] = useState<'hex' | 'rgb' | 'hsl'>('hex');
  const [hexText, setHexText] = useState(hex);
  const lastEmitted = useRef(hex);
  const { recentColors, savedColors, pushRecentColor, toggleSavedColor } = useSettingsStore();

  useEffect(() => {
    if (hex !== lastEmitted.current) {
      setHsv(rgbToHsv(hexToRgb(hex)));
      lastEmitted.current = hex;
    }
    setHexText(hex);
  }, [hex]);

  const emit = (next: { h: number; s: number; v: number }) => {
    setHsv(next);
    const out = rgbToHex(hsvToRgb(next));
    lastEmitted.current = out;
    onChange(out);
  };

  const svRef = useRef<HTMLDivElement>(null);
  const onSvPointer = (e: ReactPointerEvent<HTMLDivElement>) => {
    const el = svRef.current;
    if (!el) return;
    el.setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent | ReactPointerEvent<HTMLDivElement>) => {
      const r = el.getBoundingClientRect();
      const s = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
      const v = 1 - Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height));
      emit({ h: hsv.h, s, v });
    };
    move(e);
    const up = () => {
      el.removeEventListener('pointermove', move as EventListener);
      el.removeEventListener('pointerup', up);
      pushRecentColor(lastEmitted.current);
    };
    el.addEventListener('pointermove', move as EventListener);
    el.addEventListener('pointerup', up);
  };

  const rgb = hexToRgb(hex);
  const hsl = rgbToHsl(rgb);
  const hueColor = useMemo(() => rgbToHex(hsvToRgb({ h: hsv.h, s: 1, v: 1 })), [hsv.h]);
  const eyedropperSupported = typeof window !== 'undefined' && 'EyeDropper' in window;

  const pickWithEyedropper = async () => {
    try {
      const Ctor = (window as unknown as { EyeDropper: EyeDropperCtor }).EyeDropper;
      const res = await new Ctor().open();
      const out = normalizeHex(res.sRGBHex);
      lastEmitted.current = out;
      setHsv(rgbToHsv(hexToRgb(out)));
      onChange(out);
      pushRecentColor(out);
    } catch {
      /* cancelled */
    }
  };

  return (
    <div className="w-[232px] space-y-2.5 p-2.5">
      <div
        ref={svRef}
        role="slider"
        aria-label="Saturation and brightness"
        aria-valuenow={Math.round(hsv.v * 100)}
        tabIndex={0}
        onPointerDown={onSvPointer}
        className="relative h-32 w-full cursor-crosshair rounded-md no-touch-action"
        style={{ background: `linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, ${hueColor})` }}
      >
        <div className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow" style={{ left: `${hsv.s * 100}%`, top: `${(1 - hsv.v) * 100}%`, background: hex }} />
      </div>
      <input
        aria-label="Hue"
        type="range"
        min={0}
        max={360}
        value={hsv.h}
        onChange={(e) => emit({ ...hsv, h: parseFloat(e.target.value) })}
        onPointerUp={() => pushRecentColor(lastEmitted.current)}
        style={{ background: 'linear-gradient(to right, #f00, #ff0, #0f0, #0ff, #00f, #f0f, #f00)', borderRadius: 999, height: 8 }}
        className="hue-range"
      />
      {onAlphaChange && (
        <div className="checker rounded-full">
          <input
            aria-label="Alpha"
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={alpha ?? 1}
            onChange={(e) => onAlphaChange(parseFloat(e.target.value))}
            style={{ background: `linear-gradient(to right, transparent, ${hex})`, borderRadius: 999, height: 8 }}
            className="alpha-range"
          />
        </div>
      )}
      <div className="flex items-center gap-1.5">
        <div className="checker h-7 w-7 shrink-0 rounded-md border border-line">
          <div className="h-full w-full rounded-md" style={{ background: hex, opacity: alpha ?? 1 }} />
        </div>
        <SegmentedControl value={mode} onChange={setMode} label="Color mode" options={[{ value: 'hex', label: 'HEX' }, { value: 'rgb', label: 'RGB' }, { value: 'hsl', label: 'HSL' }]} />
      </div>
      {mode === 'hex' && (
        <input
          aria-label="Hex color"
          className="field font-mono"
          value={hexText}
          onChange={(e) => setHexText(e.target.value)}
          onBlur={() => {
            const n = normalizeHex(hexText, hex);
            lastEmitted.current = n;
            setHsv(rgbToHsv(hexToRgb(n)));
            onChange(n);
            pushRecentColor(n);
          }}
          onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
        />
      )}
      {mode === 'rgb' && (
        <div className="grid grid-cols-3 gap-1">
          {(['r', 'g', 'b'] as const).map((k) => (
            <label key={k} className="flex h-7 items-center rounded-md border border-line bg-ink-800 px-1.5">
              <span className="text-[10px] uppercase text-ink-400">{k}</span>
              <input aria-label={`${k} channel`} className="w-full bg-transparent text-right text-[11px] outline-none" type="number" min={0} max={255} value={Math.round(rgb[k])} onChange={(e) => {
                const next = { ...rgb, [k]: Math.min(255, Math.max(0, parseInt(e.target.value || '0', 10))) };
                const out = rgbToHex(next);
                lastEmitted.current = out;
                setHsv(rgbToHsv(next));
                onChange(out);
              }} />
            </label>
          ))}
        </div>
      )}
      {mode === 'hsl' && (
        <div className="grid grid-cols-3 gap-1">
          {(['h', 's', 'l'] as const).map((k) => (
            <label key={k} className="flex h-7 items-center rounded-md border border-line bg-ink-800 px-1.5">
              <span className="text-[10px] uppercase text-ink-400">{k}</span>
              <input aria-label={`${k} value`} className="w-full bg-transparent text-right text-[11px] outline-none" type="number" min={0} max={k === 'h' ? 360 : 100} value={hsl[k]} onChange={(e) => {
                const next = { ...hsl, [k]: parseInt(e.target.value || '0', 10) };
                const nrgb = hslToRgb(next);
                const out = rgbToHex(nrgb);
                lastEmitted.current = out;
                setHsv(rgbToHsv(nrgb));
                onChange(out);
              }} />
            </label>
          ))}
        </div>
      )}
      <div className="flex items-center gap-1">
        <button type="button" className="btn h-7 flex-1 text-[11px]" onClick={() => toggleSavedColor(hex)}>
          <Star size={12} className={cn(savedColors.includes(hex) && 'fill-accent text-accent')} /> {savedColors.includes(hex) ? 'Saved' : 'Save color'}
        </button>
        {eyedropperSupported && (
          <button type="button" className="btn h-7 px-2" title="Eyedropper" aria-label="Eyedropper" onClick={pickWithEyedropper}>
            <Pipette size={13} />
          </button>
        )}
      </div>
      {savedColors.length > 0 && <Swatches label="Saved" colors={savedColors} onPick={(c) => { lastEmitted.current = c; setHsv(rgbToHsv(hexToRgb(c))); onChange(c); }} />}
      {recentColors.length > 0 && <Swatches label="Recent" colors={recentColors} onPick={(c) => { lastEmitted.current = c; setHsv(rgbToHsv(hexToRgb(c))); onChange(c); }} />}
    </div>
  );
}

function Swatches({ label, colors, onPick }: { label: string; colors: string[]; onPick: (c: string) => void }) {
  return (
    <div>
      <p className="mb-1 text-[10px] uppercase tracking-wider text-ink-400">{label}</p>
      <div className="flex flex-wrap gap-1">
        {colors.map((c) => (
          <button key={c} type="button" aria-label={`Use ${c}`} title={c} onClick={() => onPick(c)} className="h-5 w-5 rounded border border-line" style={{ background: c }} />
        ))}
      </div>
    </div>
  );
}

/** Compact swatch button that opens the picker in a popover. */
export function ColorField({ color, onChange, label, alpha, onAlphaChange }: ColorPickerProps & { label?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('touchstart', onDown);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
    };
  }, [open]);
  return (
    <div ref={ref} className="relative flex items-center gap-2">
      {label && <span className="w-[72px] shrink-0 text-[11px] text-ink-300">{label}</span>}
      <button type="button" aria-label={`${label ?? 'Color'}: ${color}`} onClick={() => setOpen((o) => !o)} className="flex h-7 flex-1 items-center gap-2 rounded-md border border-line bg-ink-800 px-1.5 hover:border-line-strong">
        <span className="checker h-4 w-4 rounded border border-line"><span className="block h-full w-full rounded" style={{ background: color, opacity: alpha ?? 1 }} /></span>
        <span className="font-mono text-[11px] text-ink-200">{normalizeHex(color)}</span>
        {alpha !== undefined && <span className="ml-auto text-[10px] text-ink-400">{Math.round(alpha * 100)}%</span>}
      </button>
      {open && (
        <div className="absolute right-0 top-8 z-40 rounded-lg border border-line bg-ink-900 shadow-2xl">
          <ColorPickerPanel color={color} onChange={onChange} alpha={alpha} onAlphaChange={onAlphaChange} />
        </div>
      )}
    </div>
  );
}
