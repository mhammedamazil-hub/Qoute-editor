import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { AlertTriangle, Check, ChevronDown, Info, Sparkles, X } from 'lucide-react';
import { cn } from '@/utils/cn';
import { useUIStore, type Toast } from '@/store/uiStore';

/* ------------------------------------------------------------------ *
 * layout
 * ------------------------------------------------------------------ */

export function Section({ title, children, defaultOpen = true, action, dense = false }: { title: string; children: ReactNode; defaultOpen?: boolean; action?: ReactNode; dense?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-line">
      <div className="flex items-center justify-between px-3 py-2">
        <button type="button" onClick={() => setOpen((o) => !o)} className="flex flex-1 items-center gap-1.5 text-left text-[11px] font-semibold uppercase tracking-wider text-ink-300 hover:text-ink-100" aria-expanded={open}>
          <ChevronDown size={12} className={cn('transition-transform', !open && '-rotate-90')} />
          {title}
        </button>
        {action}
      </div>
      {open && <div className={cn('space-y-2.5 px-3 pb-3', dense && 'space-y-1.5 pb-2')}>{children}</div>}
    </div>
  );
}

export function Row({ label, children, className, stack = false }: { label?: string; children: ReactNode; className?: string; stack?: boolean }) {
  if (stack) {
    return (
      <div className={cn('space-y-1', className)}>
        {label !== undefined && <span className="block text-[11px] text-ink-300">{label}</span>}
        <div className="flex min-w-0 items-center gap-2">{children}</div>
      </div>
    );
  }
  return (
    <div className={cn('flex items-center gap-2', className)}>
      {label !== undefined && <span className="w-[72px] shrink-0 truncate text-[11px] text-ink-300">{label}</span>}
      <div className="flex min-w-0 flex-1 items-center gap-2">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * inputs
 * ------------------------------------------------------------------ */

interface SliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
  unit?: string;
  /** Optional CSS background for the track (used by colour pickers). */
  trackStyle?: React.CSSProperties;
}

export function Slider({ label, value, min, max, step = 1, onChange, format, unit, trackStyle }: SliderProps) {
  const [text, setText] = useState(String(value));
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    if (!editing) setText(format ? format(value) : String(Math.round(value * 100) / 100));
  }, [value, editing, format]);
  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between">
        <span className="text-[11px] text-ink-300">{label}</span>
        <div className="flex items-center gap-0.5">
          <input
            aria-label={`${label} value`}
            className="mono-num h-5 w-14 rounded border border-transparent bg-transparent text-right text-[11px] text-ink-100 outline-none hover:border-line focus:border-accent/60 focus:bg-ink-800"
            value={text}
            inputMode="decimal"
            onFocus={() => setEditing(true)}
            onChange={(e) => setText(e.target.value)}
            onBlur={() => {
              setEditing(false);
              const n = parseFloat(text);
              if (!Number.isNaN(n)) onChange(Math.min(max, Math.max(min, n)));
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
            }}
          />
          {unit && <span className="text-[10px] text-ink-400">{unit}</span>}
        </div>
      </div>
      <input
        aria-label={label}
        type="range"
        className={cn(trackStyle && 'fancy-range rounded-full')}
        style={trackStyle}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
    </div>
  );
}

export function NumberField({ label, value, onChange, step = 1, min, max, className }: { label: string; value: number; onChange: (v: number) => void; step?: number; min?: number; max?: number; className?: string }) {
  const [text, setText] = useState(String(Math.round(value * 10) / 10));
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (!focused) setText(String(Math.round(value * 10) / 10));
  }, [value, focused]);
  const commit = () => {
    const n = parseFloat(text);
    if (!Number.isNaN(n)) onChange(Math.min(max ?? Infinity, Math.max(min ?? -Infinity, n)));
  };
  return (
    <label className={cn('flex items-center gap-1 rounded-md border border-line bg-ink-800 px-1.5 focus-within:border-accent/60', className)} style={{ height: 'var(--control-h)' }}>
      <span className="w-5 shrink-0 text-[10px] font-medium text-ink-400">{label}</span>
      <input
        aria-label={label}
        className="mono-num w-full min-w-0 bg-transparent text-right text-[12px] text-ink-100 outline-none"
        value={text}
        step={step}
        inputMode="decimal"
        onFocus={() => setFocused(true)}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          setFocused(false);
          commit();
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
          if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            e.preventDefault();
            const d = (e.key === 'ArrowUp' ? 1 : -1) * (e.shiftKey ? step * 10 : step);
            onChange(Math.min(max ?? Infinity, Math.max(min ?? -Infinity, value + d)));
          }
        }}
      />
    </label>
  );
}

export function Select<T extends string>({ value, onChange, options, label, className }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label?: string; className?: string }) {
  return (
    <select aria-label={label} className={cn('field cursor-pointer appearance-none pr-6', className)} value={value} onChange={(e) => onChange(e.target.value as T)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn('relative shrink-0 rounded-full border transition-colors', checked ? 'border-accent bg-accent' : 'border-ink-500 bg-ink-700')}
      style={{ height: 18, width: 32 }}
    >
      <span className={cn('absolute top-0.5 h-3 w-3 rounded-full bg-ink-950 transition-transform', checked ? 'left-0.5 translate-x-3.5' : 'left-0.5')} />
    </button>
  );
}

export function SegmentedControl<T extends string>({ value, onChange, options, label, compact = false }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; title?: string }[]; label?: string; compact?: boolean }) {
  const id = useId();
  return (
    <div role="radiogroup" aria-label={label} className={cn('flex w-full overflow-hidden rounded-md border border-line bg-ink-800 p-0.5', !compact && 'min-h-[var(--control-h)]')}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          title={o.title}
          aria-checked={value === o.value}
          role="radio"
          id={`${id}-${o.value}`}
          onClick={() => onChange(o.value)}
          className={cn('flex flex-1 items-center justify-center rounded px-1 text-[11px] transition-colors', value === o.value ? 'bg-ink-600 text-ink-100' : 'text-ink-300 hover:text-ink-100')}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function TextArea({ value, onChange, rows = 3, placeholder, label, onKeyDown, autoFocus }: { value: string; onChange: (v: string) => void; rows?: number; placeholder?: string; label?: string; onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void; autoFocus?: boolean }) {
  return (
    <textarea
      aria-label={label}
      autoFocus={autoFocus}
      className="field resize-y py-1.5 leading-snug"
      rows={rows}
      value={value}
      placeholder={placeholder}
      onKeyDown={onKeyDown}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

/* ------------------------------------------------------------------ *
 * overlays
 * ------------------------------------------------------------------ */

export function Modal({
  open,
  onClose,
  title,
  children,
  width = 'max-w-2xl',
  footer,
  fullscreenOnMobile = true,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  width?: string;
  footer?: ReactNode;
  fullscreenOnMobile?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6" onMouseDown={(e) => e.target === e.currentTarget && onClose()} role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0" style={{ background: 'var(--scrim)' }} aria-hidden />
      <div
        className={cn(
          'pop-in relative flex w-full flex-col border border-line bg-ink-900 shadow-2xl',
          fullscreenOnMobile ? 'h-[100dvh] max-h-[100dvh] rounded-none sm:h-auto sm:max-h-[92vh] sm:rounded-xl' : 'max-h-[92vh] rounded-t-xl sm:rounded-xl',
          width,
        )}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-line px-4 py-3" style={{ paddingTop: 'max(12px, env(safe-area-inset-top))' }}>
          <h2 className="truncate text-[13px] font-semibold text-ink-100">{title}</h2>
          <button className="icon-btn icon-btn-sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{children}</div>
        {footer && <div className="safe-bottom flex shrink-0 items-center justify-end gap-2 border-t border-line px-4 py-3">{footer}</div>}
      </div>
    </div>
  );
}

/** Mobile bottom sheet with drag-to-dismiss and safe-area padding. */
export function BottomSheet({
  open,
  onClose,
  title,
  children,
  height = '58vh',
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  height?: string;
  footer?: ReactNode;
}) {
  const startY = useRef<number | null>(null);
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    if (!open) setOffset(0);
  }, [open]);
  if (!open) return null;
  return (
    <>
      <div className="absolute inset-0 z-20" style={{ background: 'var(--scrim)' }} onClick={onClose} aria-hidden />
      <div
        className="sheet-up absolute inset-x-0 bottom-0 z-30 flex flex-col rounded-t-2xl border-t border-line sheet elevated"
        style={{ height, transform: offset ? `translateY(${offset}px)` : undefined, transition: offset ? 'none' : 'transform 180ms' }}
        role="dialog"
        aria-label={title}
      >
        <div
          className="flex shrink-0 cursor-grab touch-none items-center justify-between px-3 pb-1 pt-2"
          onPointerDown={(e) => {
            startY.current = e.clientY;
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (startY.current === null) return;
            setOffset(Math.max(0, e.clientY - startY.current));
          }}
          onPointerUp={() => {
            if (offset > 90) onClose();
            startY.current = null;
            setOffset(0);
          }}
        >
          <span className="grabber mx-auto" />
        </div>
        <div className="flex shrink-0 items-center justify-between px-3 pb-2">
          <span className="truncate text-[12px] font-semibold">{title}</span>
          <button className="icon-btn icon-btn-sm" onClick={onClose} aria-label="Close sheet">
            <X size={15} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-0 pb-2">{children}</div>
        {footer && <div className="safe-bottom shrink-0 border-t border-line px-3 py-2">{footer}</div>}
      </div>
    </>
  );
}

export function EmptyState({ title, hint, icon, action }: { title: string; hint?: string; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="px-4 py-10 text-center">
      {icon && <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-full border border-line bg-ink-850 text-ink-300">{icon}</div>}
      <p className="text-[12px] font-medium text-ink-200">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-[260px] text-[11px] leading-relaxed text-ink-400">{hint}</p>}
      {action && <div className="mt-3 flex justify-center">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * feedback
 * ------------------------------------------------------------------ */

export function Tooltip({ label, children, side = 'top' }: { label: string; children: ReactNode; side?: 'top' | 'bottom' | 'right' }) {
  return (
    <span className="group/tt relative inline-flex">
      {children}
      <span
        role="tooltip"
        className={cn(
          'pointer-events-none absolute z-50 hidden whitespace-nowrap rounded-md border border-line bg-ink-800 px-1.5 py-0.5 text-[10px] text-ink-100 opacity-0 shadow-lg transition-opacity group-hover/tt:opacity-100 group-focus-within/tt:opacity-100 md:block',
          side === 'top' && 'bottom-full left-1/2 mb-1.5 -translate-x-1/2',
          side === 'bottom' && 'top-full left-1/2 mt-1.5 -translate-x-1/2',
          side === 'right' && 'left-full top-1/2 ml-1.5 -translate-y-1/2',
        )}
      >
        {label}
      </span>
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd>{children}</kbd>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('shimmer relative overflow-hidden rounded-md bg-ink-800', className)} />;
}

export function ToastHost() {
  const toasts = useUIStore((s) => s.toasts);
  const dismiss = useUIStore((s) => s.dismissToast);
  if (!toasts.length) return null;
  const icon: Record<Toast['tone'], ReactNode> = {
    info: <Info size={14} className="text-ink-300" />,
    success: <Check size={14} className="text-emerald-400" />,
    error: <AlertTriangle size={14} className="text-red-400" />,
    ai: <Sparkles size={14} className="text-accent" />,
  };
  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-[60] flex flex-col items-center gap-2 px-3 pt-3" style={{ paddingTop: 'max(12px, env(safe-area-inset-top))' }}>
      {toasts.map((t) => (
        <div key={t.id} className="fade-up pointer-events-auto flex w-full max-w-md items-start gap-2 rounded-lg border border-line glass px-3 py-2 shadow-xl">
          <span className="mt-0.5">{icon[t.tone]}</span>
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-medium text-ink-100">{t.message}</p>
            {t.detail && <p className="mt-0.5 text-[11px] leading-snug text-ink-300">{t.detail}</p>}
          </div>
          {t.action && (
            <button
              type="button"
              className="btn btn-ghost h-7 shrink-0 px-2 text-[11px]"
              onClick={() => {
                t.action?.run();
                dismiss(t.id);
              }}
            >
              {t.action.label}
            </button>
          )}
          <button className="icon-btn icon-btn-sm shrink-0" onClick={() => dismiss(t.id)} aria-label="Dismiss">
            <X size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * media queries (legacy helper kept for existing components)
 * ------------------------------------------------------------------ */

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => (typeof window !== 'undefined' ? window.matchMedia(query).matches : false));
  useEffect(() => {
    const mq = window.matchMedia(query);
    const handler = () => setMatches(mq.matches);
    handler();
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [query]);
  return matches;
}
