import { useEffect, useState } from 'react';
import { create } from 'zustand';

/* ------------------------------------------------------------------ *
 * Toasts — every long operation reports success/failure here so the
 * workflow never leaves the user guessing (mobile included).
 * ------------------------------------------------------------------ */

export type ToastTone = 'info' | 'success' | 'error' | 'ai';

export interface Toast {
  id: string;
  tone: ToastTone;
  message: string;
  detail?: string;
  action?: { label: string; run: () => void };
  /** ms; 0 = sticky until dismissed. */
  duration: number;
}

interface UIState {
  toasts: Toast[];
  paletteOpen: boolean;
  aiOpen: boolean;
  shortcutsOpen: boolean;
  /** Mobile: which primary sheet is open in the editor. */
  pushToast: (t: Omit<Toast, 'id' | 'duration'> & { duration?: number }) => string;
  dismissToast: (id: string) => void;
  setPalette: (open: boolean) => void;
  setAIOpen: (open: boolean) => void;
  setShortcuts: (open: boolean) => void;
}

let toastSeq = 0;

export const useUIStore = create<UIState>()((set, get) => ({
  toasts: [],
  paletteOpen: false,
  aiOpen: false,
  shortcutsOpen: false,

  pushToast: (t) => {
    const id = `toast-${++toastSeq}`;
    const toast: Toast = { duration: 4200, ...t, id };
    set((s) => ({ toasts: [...s.toasts.slice(-3), toast] }));
    if (toast.duration > 0) {
      window.setTimeout(() => get().dismissToast(id), toast.duration);
    }
    return id;
  },

  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  setPalette: (paletteOpen) => set({ paletteOpen }),
  setAIOpen: (aiOpen) => set({ aiOpen }),
  setShortcuts: (shortcutsOpen) => set({ shortcutsOpen }),
}));

export function toast(message: string, tone: ToastTone = 'info', detail?: string, action?: Toast['action']) {
  return useUIStore.getState().pushToast({ message, tone, detail, action });
}

/* ------------------------------------------------------------------ *
 * Device / environment hooks — used everywhere so the UI adapts to
 * phones, tablets, foldables, desktop and TV-ish large screens.
 * ------------------------------------------------------------------ */

export type DeviceClass = 'phone' | 'tablet' | 'desktop' | 'wide';

export function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(() => (typeof window === 'undefined' ? false : window.matchMedia(query).matches));
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia(query);
    const handler = () => setMatches(mq.matches);
    handler();
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [query]);
  return matches;
}

/** Coarse viewport class. Portrait phones and short landscape phones both map to 'phone'. */
export function useDevice(): DeviceClass {
  const wide = useMedia('(min-width: 1600px)');
  const desktop = useMedia('(min-width: 1100px)');
  const tablet = useMedia('(min-width: 768px) and (orientation: landscape)');
  const short = useMedia('(max-height: 520px)');
  if (wide) return 'wide';
  if (desktop) return 'desktop';
  if (tablet && !short) return 'tablet';
  return 'phone';
}

export function useIsTouch(): boolean {
  return useMedia('(hover: none) and (pointer: coarse)');
}

export function usePrefersReducedMotion(): boolean {
  return useMedia('(prefers-reduced-motion: reduce)');
}

/**
 * Tracks the visual viewport so the mobile layout can stay above the
 * on-screen keyboard and iOS Safari's dynamic toolbars.
 */
export function useVisualViewportInset(): number {
  const [inset, setInset] = useState(0);
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const update = () => {
      const gap = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      setInset(gap > 60 ? gap : 0);
    };
    update();
    vv.addEventListener('resize', update);
    vv.addEventListener('scroll', update);
    return () => {
      vv.removeEventListener('resize', update);
      vv.removeEventListener('scroll', update);
    };
  }, []);
  return inset;
}

export function isStandalone(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(display-mode: standalone)').matches || (navigator as unknown as { standalone?: boolean }).standalone === true;
}
