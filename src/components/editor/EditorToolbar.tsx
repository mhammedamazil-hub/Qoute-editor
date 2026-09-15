import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Blend, Hand, Image as ImageIcon, MousePointer2, Quote, Shapes, Sparkles, Sun, Type, PaintBucket, Wand2 } from 'lucide-react';
import type { ShapeKind } from '@/types/elements';
import { BACKGROUND_ID, useEditorStore } from '@/store/editorStore';
import { createGradientLayer, createImage, createLight, createQuoteMark, createShape, createText, DECORATIONS, LIGHT_PRESETS } from '@/engine/elements/factory';
import { decodeUpload } from '@/engine/masking/imageProcessor';
import { cn } from '@/utils/cn';

const SHAPES: { kind: ShapeKind; label: string }[] = [
  { kind: 'rect', label: 'Rectangle' },
  { kind: 'roundedRect', label: 'Rounded Rect' },
  { kind: 'circle', label: 'Circle' },
  { kind: 'ellipse', label: 'Ellipse' },
  { kind: 'triangle', label: 'Triangle' },
  { kind: 'polygon', label: 'Polygon' },
  { kind: 'star', label: 'Star' },
  { kind: 'line', label: 'Line' },
  { kind: 'arrow', label: 'Arrow' },
  { kind: 'ring', label: 'Ring' },
  { kind: 'arc', label: 'Arc' },
];

/** Hook exposing all "add" actions so the desktop toolbar and mobile sheet share logic. */
export function useAddActions() {
  const addElement = useEditorStore((s) => s.addElement);
  const registerAsset = useEditorStore((s) => s.registerAsset);
  const canvas = () => useEditorStore.getState().doc.canvas;
  const center = (w: number, h: number) => ({ x: (canvas().width - w) / 2, y: (canvas().height - h) / 2, width: w, height: h });

  return {
    addText: (kind: 'quote' | 'author' | 'heading' = 'quote') => {
      const cw = canvas().width;
      if (kind === 'author') addElement(createText({ name: 'Author', content: '— Author Name', fontFamily: 'Inter', fontSize: Math.round(cw * 0.022), fontWeight: 500, letterSpacing: 3, fill: { kind: 'solid', color: '#d9a441' }, ...center(cw * 0.6, 40) }));
      else if (kind === 'heading') addElement(createText({ name: 'Heading', content: 'HEADING', fontFamily: 'Bebas Neue', fontSize: Math.round(cw * 0.12), fontWeight: 400, letterSpacing: 6, ...center(cw * 0.8, 140) }));
      else addElement(createText({ name: 'Main Quote', content: 'The quiet discipline of showing up every day is the loudest form of ambition.', fontSize: Math.round(cw * 0.056), ...center(cw * 0.72, 300) }));
    },
    addQuoteMark: () => addElement(createQuoteMark(center(160, 160))),
    addShape: (kind: ShapeKind) => {
      const base = createShape(kind);
      addElement(createShape(kind, center(base.width, base.height)));
    },
    addLight: (color: string) => {
      const cw = canvas().width;
      const size = Math.round(cw * 0.7);
      addElement(createLight(color, center(size, size)));
    },
    addGradient: () => addElement(createGradientLayer(undefined, { x: 0, y: 0, width: canvas().width, height: canvas().height })),
    addDecoration: (id: string) => {
      const def = DECORATIONS.find((d) => d.id === id);
      if (def) addElement(def.create(canvas().width, canvas().height));
    },
    addImageFile: async (file: File) => {
      const { dataUrl, width, height } = await decodeUpload(file);
      const assetId = registerAsset(dataUrl);
      const cw = canvas().width, ch = canvas().height;
      const scale = Math.min(1, (cw * 0.8) / width, (ch * 0.8) / height);
      const w = Math.round(width * scale), h = Math.round(height * scale);
      addElement(createImage(assetId, width, height, center(w, h)));
    },
    selectBackground: () => useEditorStore.getState().select([BACKGROUND_ID]),
  };
}

function Flyout({ open, children, onClose, side = 'right' }: { open: boolean; children: ReactNode; onClose: () => void; side?: 'right' | 'top' }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('touchstart', onDown);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div ref={ref} className={cn('fade-up absolute z-40 w-64 rounded-lg border border-line bg-ink-900 p-2 shadow-2xl', side === 'right' ? 'left-full top-0 ml-2' : 'bottom-full left-0 mb-2')}>
      {children}
    </div>
  );
}

export function AddMenuContent({ onDone, layout = 'grid' }: { onDone?: () => void; layout?: 'grid' | 'list' }) {
  const actions = useAddActions();
  const fileRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<'text' | 'shapes' | 'lights' | 'elements'>('text');
  const done = () => onDone?.();
  const tabs = [
    { id: 'text', label: 'Text' },
    { id: 'shapes', label: 'Shapes' },
    { id: 'lights', label: 'Lights' },
    { id: 'elements', label: 'Elements' },
  ] as const;
  return (
    <div className={cn(layout === 'grid' && 'p-1')}>
      <div className="mb-2 flex gap-1 border-b border-line pb-2">
        {tabs.map((t) => (
          <button key={t.id} type="button" onClick={() => setTab(t.id)} className={cn('rounded px-2 py-1 text-[11px]', tab === t.id ? 'bg-ink-700 text-ink-100' : 'text-ink-300 hover:text-ink-100')}>{t.label}</button>
        ))}
      </div>
      {tab === 'text' && (
        <div className="grid grid-cols-2 gap-1">
          <MenuItem label="Quote text" onClick={() => { actions.addText('quote'); done(); }} preview={<span className="font-serif text-lg" style={{ fontFamily: 'Playfair Display' }}>Aa</span>} />
          <MenuItem label="Author" onClick={() => { actions.addText('author'); done(); }} preview={<span className="text-[11px] tracking-[0.2em] text-accent">— NAME</span>} />
          <MenuItem label="Heading" onClick={() => { actions.addText('heading'); done(); }} preview={<span className="text-xl" style={{ fontFamily: 'Bebas Neue' }}>HEAD</span>} />
          <MenuItem label="Quote mark" onClick={() => { actions.addQuoteMark(); done(); }} preview={<span className="text-3xl leading-none text-accent" style={{ fontFamily: 'Playfair Display' }}>“</span>} />
          <MenuItem label="Upload image" onClick={() => fileRef.current?.click()} preview={<ImageIcon size={18} />} />
          <MenuItem label="Gradient layer" onClick={() => { actions.addGradient(); done(); }} preview={<span className="h-5 w-8 rounded" style={{ background: 'radial-gradient(circle at 30% 30%, #d89b35, transparent 70%)' }} />} />
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void actions.addImageFile(f).then(done).catch((err) => alert(err instanceof Error ? err.message : 'Failed to load image')); e.target.value = ''; }} />
        </div>
      )}
      {tab === 'shapes' && (
        <div className="grid grid-cols-3 gap-1">
          {SHAPES.map((s) => (
            <MenuItem key={s.kind} label={s.label} onClick={() => { actions.addShape(s.kind); done(); }} preview={<ShapeGlyph kind={s.kind} />} />
          ))}
        </div>
      )}
      {tab === 'lights' && (
        <div className="grid grid-cols-3 gap-1">
          {LIGHT_PRESETS.map((p) => (
            <MenuItem key={p.id} label={p.label} onClick={() => { actions.addLight(p.color); done(); }} preview={<span className="h-6 w-6 rounded-full" style={{ background: `radial-gradient(circle, ${p.color}, transparent 70%)` }} />} />
          ))}
          <MenuItem label="Custom" onClick={() => { actions.addLight('#ff7a3d'); done(); }} preview={<span className="h-6 w-6 rounded-full border border-dashed border-ink-400" />} />
        </div>
      )}
      {tab === 'elements' && (
        <div className="grid max-h-72 grid-cols-3 gap-1 overflow-y-auto">
          {DECORATIONS.map((d) => (
            <MenuItem key={d.id} label={d.label} onClick={() => { actions.addDecoration(d.id); done(); }} preview={<DecoGlyph id={d.id} />} />
          ))}
        </div>
      )}
    </div>
  );
}

function MenuItem({ label, onClick, preview }: { label: string; onClick: () => void; preview: ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="flex h-16 flex-col items-center justify-center gap-1 rounded-md border border-line bg-ink-850 px-1 text-ink-200 transition-colors hover:border-line-strong hover:bg-ink-800 hover:text-ink-100">
      <span className="flex h-7 items-center justify-center">{preview}</span>
      <span className="w-full truncate text-center text-[10px]">{label}</span>
    </button>
  );
}

function ShapeGlyph({ kind }: { kind: ShapeKind }) {
  const s = 'stroke-current fill-none';
  switch (kind) {
    case 'rect': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><rect x="3" y="3" width="16" height="16" /></svg>;
    case 'roundedRect': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><rect x="3" y="3" width="16" height="16" rx="4" /></svg>;
    case 'circle': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><circle cx="11" cy="11" r="8" /></svg>;
    case 'ellipse': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><ellipse cx="11" cy="11" rx="9" ry="6" /></svg>;
    case 'triangle': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><path d="M11 3 L19 19 L3 19 Z" /></svg>;
    case 'polygon': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><path d="M11 2 L19 6.5 L19 15.5 L11 20 L3 15.5 L3 6.5 Z" /></svg>;
    case 'star': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><path d="M11 2 L13.5 8 L20 8.5 L15 12.8 L16.6 19 L11 15.6 L5.4 19 L7 12.8 L2 8.5 L8.5 8 Z" /></svg>;
    case 'line': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><path d="M3 11 H19" /></svg>;
    case 'arrow': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><path d="M3 11 H19 M14 6 L19 11 L14 16" /></svg>;
    case 'ring': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><circle cx="11" cy="11" r="8" /><circle cx="11" cy="11" r="4" /></svg>;
    case 'arc': return <svg width="22" height="22" viewBox="0 0 22 22" className={s} strokeWidth="1.5"><path d="M4 16 A8 8 0 1 1 18 16" /></svg>;
    default: return null;
  }
}

function DecoGlyph({ id }: { id: string }) {
  const s = 'stroke-current fill-none';
  switch (id) {
    case 'thin-line': case 'hline': return <svg width="22" height="22" className={s} strokeWidth="1"><path d="M2 11 H20" /></svg>;
    case 'vline': return <svg width="22" height="22" className={s} strokeWidth="1.5"><path d="M11 2 V20" /></svg>;
    case 'corner': return <svg width="22" height="22" className={s} strokeWidth="1"><path d="M2 7 V2 H7 M15 2 H20 V7 M20 15 V20 H15 M7 20 H2 V15" /></svg>;
    case 'circle': return <svg width="22" height="22" className={s} strokeWidth="1"><circle cx="11" cy="11" r="8" /></svg>;
    case 'ring': return <svg width="22" height="22" className={s} strokeWidth="1"><circle cx="11" cy="11" r="8" /><circle cx="11" cy="11" r="6.5" /></svg>;
    case 'arc': return <svg width="22" height="22" className={s} strokeWidth="1"><path d="M4 15 A8 8 0 1 1 18 15" /></svg>;
    case 'grid': return <svg width="22" height="22" className={s} strokeWidth="0.75"><path d="M6 2 V20 M11 2 V20 M16 2 V20 M2 6 H20 M2 11 H20 M2 16 H20" /></svg>;
    case 'dots': return <svg width="22" height="22" className="fill-current"><circle cx="5" cy="5" r="1" /><circle cx="11" cy="5" r="1" /><circle cx="17" cy="5" r="1" /><circle cx="5" cy="11" r="1" /><circle cx="11" cy="11" r="1" /><circle cx="17" cy="11" r="1" /><circle cx="5" cy="17" r="1" /><circle cx="11" cy="17" r="1" /><circle cx="17" cy="17" r="1" /></svg>;
    case 'particles': return <Sparkles size={16} />;
    case 'crosshair': return <svg width="22" height="22" className={s} strokeWidth="1"><circle cx="11" cy="11" r="5" /><path d="M11 2 V20 M2 11 H20" /></svg>;
    case 'plus': return <svg width="22" height="22" className={s} strokeWidth="1.5"><path d="M11 4 V18 M4 11 H18" /></svg>;
    case 'star': return <svg width="22" height="22" className="fill-current"><path d="M11 3 L13 9 L19 9.3 L14.3 13 L15.8 19 L11 15.6 L6.2 19 L7.7 13 L3 9.3 L9 9 Z" /></svg>;
    case 'frame': return <svg width="22" height="22" className={s} strokeWidth="1"><rect x="3" y="3" width="16" height="16" /></svg>;
    case 'quote-open': return <span className="text-2xl leading-none" style={{ fontFamily: 'Playfair Display' }}>“</span>;
    case 'quote-close': return <span className="text-2xl leading-none" style={{ fontFamily: 'Playfair Display' }}>”</span>;
    case 'quote-heavy': return <span className="text-xl leading-none">❝</span>;
    case 'triangle': return <svg width="22" height="22" className={s} strokeWidth="1"><path d="M11 3 L19 19 L3 19 Z" /></svg>;
    case 'hexagon': return <svg width="22" height="22" className={s} strokeWidth="1"><path d="M11 2 L19 6.5 L19 15.5 L11 20 L3 15.5 L3 6.5 Z" /></svg>;
    default: return <Shapes size={16} />;
  }
}

/** Desktop vertical toolbar. */
export function EditorToolbar() {
  const tool = useEditorStore((s) => s.tool);
  const setTool = useEditorStore((s) => s.setTool);
  const setModal = useEditorStore((s) => s.setModal);
  const actions = useAddActions();
  const [open, setOpen] = useState<null | 'add' | 'shapes' | 'lights' | 'elements'>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const Btn = ({ id, label, icon, onClick, active }: { id?: string; label: string; icon: ReactNode; onClick: () => void; active?: boolean }) => (
    <button type="button" className={cn('icon-btn h-9 w-9', active && 'active')} title={label} aria-label={label} onClick={onClick} data-id={id}>
      {icon}
    </button>
  );

  return (
    <div className="relative flex w-12 flex-col items-center gap-1 border-r border-line bg-ink-900 py-2" role="toolbar" aria-label="Tools">
      <Btn label="Select (V)" icon={<MousePointer2 size={17} />} active={tool === 'select'} onClick={() => setTool('select')} />
      <Btn label="Hand / Pan (H)" icon={<Hand size={17} />} active={tool === 'hand'} onClick={() => setTool('hand')} />
      <div className="my-1 h-px w-6 bg-line" />
      <div className="relative">
        <Btn label="Add text (T)" icon={<Type size={17} />} onClick={() => actions.addText('quote')} />
      </div>
      <Btn label="Quote mark" icon={<Quote size={17} />} onClick={actions.addQuoteMark} />
      <div className="relative">
        <Btn label="Shapes" icon={<Shapes size={17} />} active={open === 'shapes'} onClick={() => setOpen(open === 'shapes' ? null : 'shapes')} />
        <Flyout open={open === 'shapes'} onClose={() => setOpen(null)}>
          <p className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Shapes</p>
          <div className="grid grid-cols-3 gap-1">
            {SHAPES.map((s) => <MenuItem key={s.kind} label={s.label} onClick={() => { actions.addShape(s.kind); setOpen(null); }} preview={<ShapeGlyph kind={s.kind} />} />)}
          </div>
        </Flyout>
      </div>
      <div className="relative">
        <Btn label="Lights" icon={<Sun size={17} />} active={open === 'lights'} onClick={() => setOpen(open === 'lights' ? null : 'lights')} />
        <Flyout open={open === 'lights'} onClose={() => setOpen(null)}>
          <p className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Atmospheric light</p>
          <div className="grid grid-cols-3 gap-1">
            {LIGHT_PRESETS.map((p) => <MenuItem key={p.id} label={p.label} onClick={() => { actions.addLight(p.color); setOpen(null); }} preview={<span className="h-6 w-6 rounded-full" style={{ background: `radial-gradient(circle, ${p.color}, transparent 70%)` }} />} />)}
            <MenuItem label="Custom" onClick={() => { actions.addLight('#ff7a3d'); setOpen(null); }} preview={<span className="h-6 w-6 rounded-full border border-dashed border-ink-400" />} />
          </div>
        </Flyout>
      </div>
      <div className="relative">
        <Btn label="Elements library" icon={<Sparkles size={17} />} active={open === 'elements'} onClick={() => setOpen(open === 'elements' ? null : 'elements')} />
        <Flyout open={open === 'elements'} onClose={() => setOpen(null)}>
          <p className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Elements</p>
          <div className="grid max-h-80 grid-cols-3 gap-1 overflow-y-auto">
            {DECORATIONS.map((d) => <MenuItem key={d.id} label={d.label} onClick={() => { actions.addDecoration(d.id); setOpen(null); }} preview={<DecoGlyph id={d.id} />} />)}
          </div>
        </Flyout>
      </div>
      <Btn label="Gradient layer" icon={<Blend size={17} />} onClick={actions.addGradient} />
      <Btn label="Upload image" icon={<ImageIcon size={17} />} onClick={() => fileRef.current?.click()} />
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void actions.addImageFile(f).catch((err) => alert(err instanceof Error ? err.message : 'Failed to load image')); e.target.value = ''; }} />
      <div className="my-1 h-px w-6 bg-line" />
      <Btn label="Background" icon={<PaintBucket size={17} />} onClick={actions.selectBackground} />
      <div className="mt-auto" />
      <Btn label="Design with AI" icon={<Wand2 size={17} className="text-accent" />} onClick={() => setModal('ai')} />
    </div>
  );
}
