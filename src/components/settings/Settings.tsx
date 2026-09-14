import { useState } from 'react';
import { Check, Cpu, Eye, EyeOff, HardDrive, Loader2, RefreshCw, Sparkles, Trash2, Wand2 } from 'lucide-react';
import { useSettingsStore, type Density, type ThemeChoice } from '@/store/settingsStore';
import { GeminiClient, GeminiError } from '@/ai/gemini/GeminiClient';
import { DEFAULT_MODEL, GEMINI_MODELS, mergeWithLiveModels, modelRank } from '@/ai/gemini/models';
import { Modal, Row, SegmentedControl, Select, Slider, Toggle } from '@/components/ui';
import { toast } from '@/store/uiStore';
import { cn } from '@/utils/cn';
import type { AIStatus } from '@/types/ai';

type SectionId = 'general' | 'editor' | 'appearance' | 'export' | 'ai';

const STATUS_LABEL: Record<AIStatus, { text: string; color: string }> = {
  'not-configured': { text: 'Not configured', color: 'bg-ink-400' },
  configured: { text: 'Configured — not tested', color: 'bg-amber-400' },
  connected: { text: 'Gemini connected', color: 'bg-emerald-400' },
  invalid: { text: 'Invalid key', color: 'bg-red-400' },
  failed: { text: 'Connection failed', color: 'bg-red-400' },
};

const ACCENTS = ['#d9a441', '#e879f9', '#22d3ee', '#3fbf7f', '#ff8a3d', '#8b5cf6', '#3a7bff', '#e0453b'];

function AISettings() {
  const s = useSettingsStore();
  const [draft, setDraft] = useState(s.geminiKey);
  const [show, setShow] = useState(false);
  const [persist, setPersist] = useState(s.geminiKeyPersisted || !s.geminiKey);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const status = STATUS_LABEL[s.aiStatus];

  const models = mergeWithLiveModels(s.discoveredModels);
  const current = models.find((m) => m.id === s.geminiModel);
  const isLegacy = current?.family === 'legacy' && s.geminiModel !== 'gemini-flash-latest';

  const save = () => {
    s.setGeminiKey(draft, persist);
    setMessage(draft.trim() ? (persist ? 'Key saved in this browser.' : 'Key kept for this session only.') : 'Key cleared.');
  };

  const test = async () => {
    const key = draft.trim();
    if (!key) return;
    setTesting(true);
    setMessage(null);
    try {
      s.setGeminiKey(key, persist);
      const client = new GeminiClient({ apiKey: key, model: s.geminiModel });
      const res = await client.testConnection();
      s.setDiscoveredModels(res.models);
      s.setAIStatus('connected');
      // Auto-heal: if the selected model is missing from the key, move to the newest available.
      if (!res.models.includes(s.geminiModel)) {
        const best = [...res.models].sort((a, b) => modelRank(b) - modelRank(a))[0];
        if (best) {
          s.update({ geminiModel: best });
          setMessage(`Connected — ${res.count} models available. “${s.geminiModel}” is not enabled on this key, switched to ${best}.`);
          return;
        }
      }
      setMessage(`Connected — ${res.count} text models available on this key.`);
    } catch (e) {
      if (e instanceof GeminiError) {
        s.setAIStatus(e.code === 'invalid-key' ? 'invalid' : 'failed');
        setMessage(e.message);
      } else {
        s.setAIStatus('failed');
        setMessage('Connection failed.');
      }
    } finally {
      setTesting(false);
    }
  };

  const refreshModels = async () => {
    const key = draft.trim() || s.geminiKey;
    if (!key) return;
    setTesting(true);
    try {
      const list = await new GeminiClient({ apiKey: key, model: s.geminiModel }).listModels();
      s.setDiscoveredModels(list.filter((m) => m.supportsGenerateContent).map((m) => m.id));
      toast('Model list refreshed', 'success', `${list.filter((m) => m.supportsGenerateContent).length} text models found on your key.`);
    } catch (e) {
      toast('Could not refresh models', 'error', e instanceof Error ? e.message : undefined);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-[13px] font-semibold">Gemini API</h3>
        <p className="mt-1 text-[11px] leading-relaxed text-ink-300">
          Optional but recommended. You supply <strong className="text-ink-100">your own</strong> Gemini API key — it is stored only in this browser (if you choose) and sent directly to Google. QuoteCraft ships with no key and no backend.
        </p>
      </div>

      <div className="rounded-lg border border-line bg-ink-850 p-3">
        <label className="text-[11px] text-ink-300" htmlFor="gemini-key">
          API key
        </label>
        <div className="mt-1 flex gap-1.5">
          <input
            id="gemini-key"
            type={show ? 'text' : 'password'}
            autoComplete="off"
            spellCheck={false}
            inputMode="text"
            className="field font-mono"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Paste your Gemini API key"
          />
          <button type="button" className="btn px-2" onClick={() => setShow((v) => !v)} aria-label={show ? 'Hide key' : 'Show key'}>
            {show ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <Toggle checked={persist} onChange={setPersist} label="Save locally" />
          <span className="text-[11px] text-ink-300">Save in this browser — otherwise the key lasts for this session only</span>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <button type="button" className="btn btn-primary" onClick={save} disabled={draft === s.geminiKey && persist === s.geminiKeyPersisted}>
            <Check size={13} /> Save key
          </button>
          <button type="button" className="btn" onClick={() => void test()} disabled={!draft.trim() || testing}>
            {testing ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} Test & connect
          </button>
          <button type="button" className="btn" onClick={() => void refreshModels()} disabled={(!draft.trim() && !s.geminiKey) || testing}>
            <RefreshCw size={13} /> Refresh models
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => {
              s.removeGeminiKey();
              setDraft('');
              setMessage('Key removed from this browser.');
            }}
            disabled={!s.geminiKey && !draft}
          >
            <Trash2 size={13} /> Remove
          </button>
        </div>
        <div className="mt-3 flex items-center gap-2 text-[11px]">
          <span className={cn('h-2 w-2 rounded-full', status.color)} />
          <span className="text-ink-200">Status: {status.text}</span>
        </div>
        {message && <p className="mt-1.5 text-[11px] leading-snug text-ink-300">{message}</p>}
      </div>

      <Row label="Model">
        <Select
          label="Gemini model"
          value={s.geminiModel}
          onChange={(geminiModel) => s.update({ geminiModel })}
          options={models.map((m) => ({ value: m.id, label: m.recommended ? `${m.label} — recommended` : m.label }))}
        />
      </Row>
      <p className="text-[10.5px] leading-snug text-ink-500">
        {current?.blurb ?? 'Model detected on your API key.'}
        {s.discoveredAt ? ` Discovered ${new Date(s.discoveredAt).toLocaleTimeString()} from your key.` : ' Press “Refresh models” to read the live list from Google.'}
      </p>
      {(isLegacy || s.modelMigratedFrom) && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-400/30 bg-amber-400/10 p-2.5 text-[11px] text-amber-200">
          <Cpu size={14} className="mt-0.5 shrink-0" />
          <span>
            {s.modelMigratedFrom ? (
              <>
                Your saved model <strong>{s.modelMigratedFrom}</strong> is retired (Google closed it), so QuoteCraft moved you to <strong>{s.geminiModel}</strong> automatically.
              </>
            ) : (
              <>
                This is a legacy model. The current default is <strong>{DEFAULT_MODEL}</strong> — newest Flash, better at design and tool use.
              </>
            )}
          </span>
        </div>
      )}

      <div className="space-y-2 rounded-lg border border-line bg-ink-850 p-3">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-300">
          <Wand2 size={12} className="text-accent" /> Copilot behaviour
        </p>
        <Row label="Show activity">
          <Toggle checked={s.aiShowToolActivity} onChange={(aiShowToolActivity) => s.update({ aiShowToolActivity })} label="Show tool activity" />
          <span className="text-[11px] text-ink-400">List every editor action the copilot performs</span>
        </Row>
      </div>

      <div className="flex flex-wrap gap-2">
        {GEMINI_MODELS.filter((m) => m.recommended).map((m) => (
          <button key={m.id} type="button" className="btn" onClick={() => s.update({ geminiModel: m.id })}>
            Use recommended · {m.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Settings({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [section, setSection] = useState<SectionId>('general');
  const s = useSettingsStore();
  const sections: { id: SectionId; label: string }[] = [
    { id: 'general', label: 'General' },
    { id: 'editor', label: 'Editor' },
    { id: 'appearance', label: 'Appearance' },
    { id: 'export', label: 'Export' },
    { id: 'ai', label: 'AI' },
  ];

  return (
    <Modal open={open} onClose={onClose} title="Settings" width="max-w-3xl">
      <div className="flex min-h-0 flex-col sm:flex-row">
        <nav className="safe-x flex gap-1 overflow-x-auto border-b border-line p-2 sm:w-44 sm:flex-col sm:border-b-0 sm:border-r" aria-label="Settings sections">
          {sections.map((sec) => (
            <button
              key={sec.id}
              type="button"
              onClick={() => setSection(sec.id)}
              className={cn('flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-1.5 text-left text-[12px]', section === sec.id ? 'bg-ink-750 text-ink-100' : 'text-ink-300 hover:bg-ink-800 hover:text-ink-100')}
            >
              {sec.label}
              {sec.id === 'ai' && <span className={cn('ml-auto inline-block h-1.5 w-1.5 rounded-full', STATUS_LABEL[s.aiStatus].color)} />}
            </button>
          ))}
        </nav>
        <div className="min-w-0 flex-1 space-y-4 p-4">
          {section === 'general' && (
            <>
              <h3 className="text-[13px] font-semibold">General</h3>
              <Row label="Autosave">
                <Toggle checked={s.autosave} onChange={(autosave) => s.update({ autosave })} label="Autosave" />
                <span className="text-[11px] text-ink-400">Save changes to this browser automatically</span>
              </Row>
              <Slider label="Autosave delay" value={Math.round(s.autosaveDelayMs / 100) / 10} min={0.5} max={6} step={0.5} onChange={(v) => s.update({ autosaveDelayMs: Math.round(v * 1000) })} unit="s" />
              <Row label="Confirm delete">
                <Toggle checked={s.confirmDelete} onChange={(confirmDelete) => s.update({ confirmDelete })} label="Confirm delete" />
                <span className="text-[11px] text-ink-400">Ask before deleting layers with the keyboard</span>
              </Row>
              <div className="rounded-lg border border-line bg-ink-850 p-3">
                <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-300">
                  <HardDrive size={12} /> Local data
                </p>
                <p className="mt-1 text-[11px] leading-snug text-ink-400">Projects, assets and settings live in this browser only. Nothing is uploaded except your prompts to Google (when you use the AI).</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className="btn" onClick={() => { s.resetAll(); toast('Interface settings reset', 'success'); }}>
                    Reset interface settings
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={() => {
                      if (confirm('Erase all QuoteCraft data in this browser (projects + settings + API key)? This cannot be undone.')) {
                        try {
                          localStorage.clear();
                          indexedDB.deleteDatabase('quotecraft');
                        } catch {
                          /* ignore */
                        }
                        location.reload();
                      }
                    }}
                  >
                    <Trash2 size={13} /> Erase local data
                  </button>
                </div>
              </div>
            </>
          )}

          {section === 'editor' && (
            <>
              <h3 className="text-[13px] font-semibold">Editor</h3>
              <Row label="Snapping">
                <Toggle checked={s.snapping} onChange={(snapping) => s.update({ snapping })} label="Smart snapping" />
                <span className="text-[11px] text-ink-400">Snap to canvas centre, edges and other layers</span>
              </Row>
              <Row label="Guides">
                <Toggle checked={s.showGuides} onChange={(showGuides) => s.update({ showGuides })} label="Show guides" />
                <span className="text-[11px] text-ink-400">Show alignment guides while moving</span>
              </Row>
              <Slider label="Handle size" value={s.handleSize} min={6} max={18} onChange={(handleSize) => s.update({ handleSize })} unit="px" />
            </>
          )}

          {section === 'appearance' && (
            <>
              <h3 className="text-[13px] font-semibold">Appearance</h3>
              <Row label="Theme">
                <SegmentedControl<ThemeChoice>
                  value={s.theme}
                  onChange={(theme) => s.update({ theme })}
                  label="Theme"
                  options={[
                    { value: 'dark', label: 'Dark' },
                    { value: 'light', label: 'Light' },
                    { value: 'system', label: 'System' },
                  ]}
                />
              </Row>
              <div>
                <p className="mb-1.5 text-[11px] text-ink-300">Accent colour</p>
                <div className="flex flex-wrap items-center gap-1.5">
                  {ACCENTS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      aria-label={`Accent ${c}`}
                      onClick={() => s.update({ accent: c })}
                      className={cn('h-7 w-7 rounded-full border transition-transform hover:scale-105', s.accent.toLowerCase() === c.toLowerCase() ? 'border-ink-100 ring-2 ring-accent/50' : 'border-line')}
                      style={{ background: c }}
                    />
                  ))}
                  <input
                    type="color"
                    aria-label="Custom accent"
                    className="h-7 w-9 cursor-pointer rounded border border-line bg-ink-800"
                    value={s.accent}
                    onChange={(e) => s.update({ accent: e.target.value })}
                  />
                </div>
              </div>
              <Row label="Density">
                <SegmentedControl<Density>
                  value={s.uiDensity}
                  onChange={(uiDensity) => s.update({ uiDensity })}
                  label="Interface density"
                  options={[
                    { value: 'comfortable', label: 'Comfortable' },
                    { value: 'compact', label: 'Compact' },
                  ]}
                />
              </Row>
              <Row label="Backdrop">
                <SegmentedControl
                  value={s.canvasBackdrop}
                  onChange={(canvasBackdrop) => s.update({ canvasBackdrop })}
                  label="Canvas backdrop"
                  options={[
                    { value: 'dark', label: 'Dark' },
                    { value: 'gray', label: 'Gray' },
                    { value: 'black', label: 'Black' },
                  ]}
                />
              </Row>
              <Row label="Motion">
                <Toggle checked={s.reduceMotion} onChange={(reduceMotion) => s.update({ reduceMotion })} label="Reduce motion" />
                <span className="text-[11px] text-ink-400">Reduce interface animations</span>
              </Row>
            </>
          )}

          {section === 'export' && (
            <>
              <h3 className="text-[13px] font-semibold">Export defaults</h3>
              <Row label="Format">
                <SegmentedControl
                  value={s.defaultFormat}
                  onChange={(defaultFormat) => s.update({ defaultFormat })}
                  label="Default format"
                  options={[
                    { value: 'png', label: 'PNG' },
                    { value: 'jpeg', label: 'JPG' },
                    { value: 'webp', label: 'WEBP' },
                  ]}
                />
              </Row>
              <Slider label="Default quality" value={Math.round(s.defaultQuality * 100)} min={40} max={100} onChange={(v) => s.update({ defaultQuality: v / 100 })} unit="%" />
              <Slider label="Default scale" value={s.defaultScale} min={0.5} max={3} step={0.5} onChange={(defaultScale) => s.update({ defaultScale })} unit="×" />
              <p className="text-[11px] text-ink-400">PNG keeps transparency and is best for text. JPG/WEBP are smaller for photos. Exports are limited to 36 megapixels by the browser.</p>
            </>
          )}

          {section === 'ai' && <AISettings />}
        </div>
      </div>
    </Modal>
  );
}
