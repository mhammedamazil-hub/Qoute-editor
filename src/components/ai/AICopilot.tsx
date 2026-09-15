import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowUp,
  Check,
  Eraser,
  Layers,
  Loader2,
  Palette,
  Send,
  Settings2,
  Sparkles,
  SquareDashed,
  Wand2,
  Type,
  Sun,
  Lightbulb,
  Move,
  Download,
  Shapes,
  Undo2,
} from 'lucide-react';
import { copilotSuggestions, useAIStore, type ChatMessage } from '@/store/aiStore';
import { useEditorStore } from '@/store/editorStore';
import { useSettingsStore } from '@/store/settingsStore';
import { useVisualViewportInset } from '@/store/uiStore';
import { cn } from '@/utils/cn';
import { toolLabel } from '@/ai/agent/runtime';
import { CANVAS_PRESETS } from '@/types/project';
import { Select } from '@/components/ui';

const TOOL_ICONS: Record<string, typeof Sparkles> = {
  get_app_state: SquareDashed,
  add_text: Type,
  set_text_content: Type,
  set_typography: Type,
  add_light: Sun,
  add_shape: Shapes,
  add_decoration: Shapes,
  add_quote_mark: Type,
  apply_palette: Palette,
  set_background: Palette,
  generate_design: Wand2,
  apply_template: Layers,
  update_elements: Move,
  translate_elements: Move,
  resize_elements: Move,
  align_elements: Move,
  delete_elements: Eraser,
  export_image: Download,
  undo: Undo2,
};

function toolIcon(name: string) {
  const Icon = TOOL_ICONS[name] ?? Lightbulb;
  return <Icon size={13} />;
}

/** Very small markdown renderer: bold, italics, inline code, bullets, headings. */
function RichText({ text }: { text: string }) {
  const blocks = useMemo(() => {
    const lines = text.split('\n');
    const out: { kind: 'p' | 'li' | 'h'; text: string }[] = [];
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (!line.trim()) continue;
      if (/^[-*•]\s+/.test(line.trim())) out.push({ kind: 'li', text: line.trim().replace(/^[-*•]\s+/, '') });
      else if (/^#{1,3}\s+/.test(line.trim())) out.push({ kind: 'h', text: line.trim().replace(/^#{1,3}\s+/, '') });
      else out.push({ kind: 'p', text: line });
    }
    return out;
  }, [text]);

  const inline = (s: string) =>
    s.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g).map((part, i) => {
      if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={i} className="font-semibold text-ink-100">{part.slice(2, -2)}</strong>;
      if (/^`[^`]+`$/.test(part)) return <code key={i} className="rounded bg-ink-800 px-1 py-0.5 font-mono text-[11px]">{part.slice(1, -1)}</code>;
      if (/^\*[^*]+\*$/.test(part)) return <em key={i}>{part.slice(1, -1)}</em>;
      return <span key={i}>{part}</span>;
    });

  return (
    <div className="space-y-1.5 text-[12.5px] leading-relaxed text-ink-100">
      {blocks.map((b, i) =>
        b.kind === 'li' ? (
          <div key={i} className="flex gap-2">
            <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-accent" />
            <span>{inline(b.text)}</span>
          </div>
        ) : b.kind === 'h' ? (
          <p key={i} className="pt-1 text-[11px] font-semibold uppercase tracking-wider text-ink-300">{b.text}</p>
        ) : (
          <p key={i}>{inline(b.text)}</p>
        ),
      )}
    </div>
  );
}

function ToolActivity({ message, showActivity }: { message: ChatMessage; showActivity: boolean }) {
  const undo = useEditorStore((s) => s.undo);
  if (!showActivity || !message.tools.length) return null;
  return (
    <div className="mt-2 space-y-1">
      {message.tools.map((t) => (
        <div key={t.id} className={cn('flex items-start gap-2 rounded-md border px-2 py-1.5 text-[11px]', t.status === 'error' ? 'border-red-500/30 bg-red-500/5' : 'border-line bg-ink-850/70')}>
          <span className={cn('mt-0.5 shrink-0', t.status === 'running' ? 'text-accent' : t.status === 'error' ? 'text-red-400' : 'text-emerald-400')}>
            {t.status === 'running' ? <Loader2 size={13} className="animate-spin" /> : t.status === 'error' ? <AlertCircle size={13} /> : toolIcon(t.name)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-ink-200">{toolLabel(t.name)}</p>
            {t.summary && <p className="truncate text-ink-400">{t.summary}</p>}
          </div>
          {t.status === 'ok' && (
            <button type="button" className="btn btn-ghost h-6 shrink-0 px-1.5 text-[10px]" title="Undo this change" onClick={() => undo()}>
              <Undo2 size={11} />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

export function AICopilot({ open, onClose }: { open: boolean; onClose: () => void }) {
  const messages = useAIStore((s) => s.messages);
  const busy = useAIStore((s) => s.busy);
  const status = useAIStore((s) => s.status);
  const send = useAIStore((s) => s.send);
  const stop = useAIStore((s) => s.stop);
  const clear = useAIStore((s) => s.clear);

  const geminiKey = useSettingsStore((s) => s.geminiKey);
  const model = useSettingsStore((s) => s.geminiModel);
  const showActivity = useSettingsStore((s) => s.aiShowToolActivity);
  const setModal = useEditorStore((s) => s.setModal);
  const elementCount = useEditorStore((s) => s.doc.elements.length);
  const keyboardInset = useVisualViewportInset();

  const [draft, setDraft] = useState('');
  const [studio, setStudio] = useState({ brief: '', style: 'Cinematic', size: 'current' });
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const suggestions = useMemo(() => copilotSuggestions(), [elementCount, open]);

  useEffect(() => {
    if (!open) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open, status]);

  useEffect(() => {
    if (open && geminiKey) setTimeout(() => inputRef.current?.focus(), 120);
  }, [open, geminiKey]);

  const submit = (text: string) => {
    const t = text.trim();
    if (!t || busy) return;
    setDraft('');
    void send(t);
  };

  const studioSubmit = () => {
    const preset = CANVAS_PRESETS.find((p) => p.id === studio.size);
    const sizeLine = preset ? ` Canvas size ${preset.width}×${preset.height}.` : '';
    const brief = studio.brief.trim() || 'a striking, premium quote poster';
    submit(`Create a full design from scratch. Brief: ${brief}. Style: ${studio.style}.${sizeLine} Then tell me what you did.`);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center sm:items-center sm:p-6" role="dialog" aria-modal="true" aria-label="QuoteCraft Copilot">
      <div className="absolute inset-0" style={{ background: 'var(--scrim)' }} onClick={onClose} aria-hidden />
      <div className="pop-in relative flex h-full w-full flex-col border border-line bg-ink-900 shadow-2xl sm:h-[86vh] sm:max-w-3xl sm:rounded-2xl">
        {/* header */}
        <div className="flex shrink-0 items-center gap-2 border-b border-line px-3 py-2.5" style={{ paddingTop: 'max(10px, env(safe-area-inset-top))' }}>
          <span className="flex h-7 w-7 items-center justify-center rounded-full border border-accent/40 bg-accent-soft text-accent">
            <Sparkles size={14} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[12.5px] font-semibold">Copilot</p>
            <p className="truncate text-[10.5px] text-ink-400">{busy ? status || 'Working…' : `${messages.length ? 'Ready' : 'Controls the whole editor'} · ${model}`}</p>
          </div>
          {messages.length > 0 && (
            <button type="button" className="icon-btn icon-btn-sm" title="Clear conversation" aria-label="Clear conversation" onClick={clear}>
              <Eraser size={15} />
            </button>
          )}
          <button type="button" className="icon-btn icon-btn-sm" title="AI settings" aria-label="AI settings" onClick={() => setModal('settings')}>
            <Settings2 size={15} />
          </button>
          <button type="button" className="btn btn-ghost h-7 px-2 text-[11px]" onClick={onClose}>
            Close
          </button>
        </div>

        {!geminiKey ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
            <span className="flex h-11 w-11 items-center justify-center rounded-full border border-line bg-ink-850 text-accent">
              <Sparkles size={20} />
            </span>
            <h3 className="text-[15px] font-semibold">Connect Gemini to unlock the copilot</h3>
            <p className="max-w-sm text-[12px] leading-relaxed text-ink-300">
              The copilot reads your canvas and drives the editor with real tools — adding layers, restyling typography, changing palettes, exporting. You supply your own API key; it stays in this browser and goes only to Google.
            </p>
            <button type="button" className="btn btn-primary mt-1" onClick={() => setModal('settings')}>
              <Settings2 size={14} /> Add API key
            </button>
            <p className="text-[10.5px] text-ink-500">Everything in the manual editor keeps working without a key.</p>
          </div>
        ) : (
          <>
            <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-3 py-3">
              {messages.length === 0 && (
                <div className="space-y-3">
                  <div className="rounded-xl border border-line bg-ink-850 p-3">
                    <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-300">
                      <Wand2 size={12} className="text-accent" /> Design studio
                    </p>
                    <p className="mt-1 text-[11.5px] text-ink-400">Describe the poster — the copilot writes it with real, editable layers.</p>
                    <textarea
                      aria-label="Design brief"
                      className="field mt-2 resize-none"
                      rows={2}
                      placeholder="A calm, premium quote poster about patience — dark background, warm amber light, gold hairline."
                      value={studio.brief}
                      onChange={(e) => setStudio((s) => ({ ...s, brief: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) studioSubmit();
                      }}
                    />
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <div className="min-w-[130px] flex-1">
                        <Select
                          label="Style"
                          value={studio.style}
                          onChange={(style) => setStudio((s) => ({ ...s, style }))}
                          options={['Cinematic', 'Minimal', 'Editorial', 'Luxury', 'Neon', 'Monochrome', 'Elegant serif', 'Modern typography'].map((v) => ({ value: v, label: v }))}
                        />
                      </div>
                      <div className="min-w-[150px] flex-1">
                        <Select
                          label="Canvas"
                          value={studio.size}
                          onChange={(size) => setStudio((s) => ({ ...s, size }))}
                          options={[{ value: 'current', label: 'Current canvas' }, ...CANVAS_PRESETS.map((p) => ({ value: p.id, label: `${p.label} · ${p.width}×${p.height}` }))]}
                        />
                      </div>
                      <button type="button" className="btn btn-primary" disabled={busy} onClick={studioSubmit}>
                        <Wand2 size={13} /> Generate
                      </button>
                    </div>
                  </div>

                  <div className="grid gap-2 sm:grid-cols-3">
                    {[
                      { icon: <Layers size={14} />, title: 'Edits real layers', text: 'Adds text, shapes, lights and gradients you can still drag, restyle and delete.' },
                      { icon: <Palette size={14} />, title: 'Knows design', text: 'Composition, hierarchy, contrast and restraint baked into the system prompt.' },
                      { icon: <Shapes size={14} />, title: 'Runs the app', text: 'Panels, zoom, preview, theme, saving and exporting are all tools it can call.' },
                    ].map((c) => (
                      <div key={c.title} className="rounded-lg border border-line bg-ink-850 p-2.5">
                        <span className="text-accent">{c.icon}</span>
                        <p className="mt-1 text-[11.5px] font-medium">{c.title}</p>
                        <p className="mt-0.5 text-[10.5px] leading-snug text-ink-400">{c.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((m) =>
                m.role === 'user' ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[86%] rounded-2xl rounded-br-sm bg-accent px-3 py-1.5 text-[12.5px] font-medium text-ink-950">{m.text}</div>
                  </div>
                ) : (
                  <div key={m.id} className="space-y-1">
                    {(m.text || m.status === 'pending') && (
                      <div className="max-w-[92%] rounded-2xl rounded-bl-sm border border-line bg-ink-850 px-3 py-2">
                        {m.text ? <RichText text={m.text} /> : <p className="pulse-soft text-[12px] text-ink-400">Working…</p>}
                        {m.status === 'stopped' && <p className="mt-1 text-[10.5px] text-ink-400">Stopped.</p>}
                      </div>
                    )}
                    <ToolActivity message={m} showActivity={showActivity} />
                    {m.error && (
                      <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-2.5 py-2 text-[11.5px] text-red-200">
                        <AlertCircle size={14} className="mt-0.5 shrink-0" />
                        <span>{m.error}</span>
                      </div>
                    )}
                  </div>
                ),
              )}
            </div>

            {/* composer */}
            <div className="shrink-0 border-t border-line px-3 pb-2 pt-2" style={{ paddingBottom: keyboardInset ? keyboardInset + 8 : undefined }}>
              {messages.length > 0 && (
                <div className="mb-2 flex gap-1.5 overflow-x-auto pb-0.5">
                  {suggestions.map((s) => (
                    <button key={s} type="button" disabled={busy} className="btn btn-ghost h-7 shrink-0 px-2 text-[11px] text-ink-300" onClick={() => submit(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              )}
              <div className="flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  aria-label="Message the copilot"
                  className="field max-h-32 min-h-[var(--control-h)] flex-1 resize-none py-2"
                  rows={1}
                  placeholder="Ask for anything: “make it more premium”, “switch to the navy palette”, “export 2× PNG”…"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      submit(draft);
                    }
                  }}
                />
                {busy ? (
                  <button type="button" className="btn h-9 px-3" onClick={stop} title="Stop">
                    <Loader2 size={14} className="animate-spin" /> Stop
                  </button>
                ) : (
                  <button type="button" className="btn btn-primary h-9 px-3" disabled={!draft.trim()} onClick={() => submit(draft)} title="Send (Enter)">
                    {draft.trim() ? <ArrowUp size={15} /> : <Send size={14} />}
                  </button>
                )}
              </div>
              <p className="mt-1.5 flex items-center gap-1 text-[10px] text-ink-500">
                <Check size={10} className="text-emerald-400" /> Every action is undoable · Enter to send, Shift+Enter for a new line
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
