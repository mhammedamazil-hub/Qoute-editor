import { useState } from 'react';
import { Download, FileJson } from 'lucide-react';
import { useEditorStore } from '@/store/editorStore';
import { useSettingsStore } from '@/store/settingsStore';
import { useProjectStore } from '@/store/projectStore';
import { renderExport, downloadBlob, type ExportFormat } from '@/engine/export/exportImage';
import { downloadJson } from '@/engine/serialization/project';
import { Modal, NumberField, Row, SegmentedControl, Slider } from '@/components/ui';

const PRESETS = [
  { label: '1080 × 1080', w: 1080, h: 1080 },
  { label: '1080 × 1350', w: 1080, h: 1350 },
  { label: '1080 × 1920', w: 1080, h: 1920 },
  { label: '1920 × 1080', w: 1920, h: 1080 },
];

export function ExportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const canvas = useEditorStore((s) => s.doc.canvas);
  const projectName = useEditorStore((s) => s.projectName);
  const defaultFormat = useSettingsStore((s) => s.defaultFormat);
  const defaultQuality = useSettingsStore((s) => s.defaultQuality);
  const [format, setFormat] = useState<ExportFormat>(defaultFormat);
  const [quality, setQuality] = useState(defaultQuality);
  const defaultScale = useSettingsStore((s) => s.defaultScale);
  const [scale, setScale] = useState(defaultScale);
  const [custom, setCustom] = useState<{ w: number; h: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ratio = canvas.width / canvas.height;
  const outW = custom ? custom.w : Math.round(canvas.width * scale);
  const outH = custom ? custom.h : Math.round(canvas.height * scale);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const blob = await renderExport({ width: outW, height: outH, format, quality });
      const ext = format === 'jpeg' ? 'jpg' : format;
      downloadBlob(blob, `${projectName.replace(/[^\w-]+/g, '_') || 'design'}-${outW}x${outH}.${ext}`);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed');
    } finally {
      setBusy(false);
    }
  };

  const exportProject = async () => {
    const file = await useProjectStore.getState().exportProjectFile();
    downloadJson(file, `${projectName.replace(/[^\w-]+/g, '_') || 'design'}.quotecraft.json`);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Export"
      width="max-w-md"
      footer={
        <>
          <button type="button" className="btn" onClick={() => void exportProject()}><FileJson size={13} /> Project file (.json)</button>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void run()}><Download size={13} /> {busy ? 'Rendering…' : `Export ${format.toUpperCase()}`}</button>
        </>
      }
    >
      <div className="space-y-4 p-4">
        <Row label="Format">
          <SegmentedControl value={format} onChange={setFormat} label="Format" options={[{ value: 'png', label: 'PNG' }, { value: 'jpeg', label: 'JPG' }, { value: 'webp', label: 'WEBP' }]} />
        </Row>
        {format !== 'png' && <Slider label="Quality" value={Math.round(quality * 100)} min={40} max={100} onChange={(v) => setQuality(v / 100)} unit="%" />}
        <div>
          <p className="mb-1.5 text-[11px] text-ink-300">Resolution</p>
          <div className="grid grid-cols-3 gap-1.5">
            {[1, 2, 3].map((s) => (
              <button key={s} type="button" onClick={() => { setScale(s); setCustom(null); }} className={`btn ${!custom && scale === s ? 'border-accent text-accent' : ''}`}>{s}× · {Math.round(canvas.width * s)}×{Math.round(canvas.height * s)}</button>
            ))}
          </div>
          <div className="mt-1.5 grid grid-cols-2 gap-1.5">
            {PRESETS.map((p) => (
              <button key={p.label} type="button" onClick={() => setCustom({ w: p.w, h: p.h })} className={`btn ${custom?.w === p.w && custom?.h === p.h ? 'border-accent text-accent' : ''}`}>{p.label}</button>
            ))}
          </div>
          <div className="mt-1.5 grid grid-cols-2 gap-1.5">
            <NumberField label="W" value={outW} min={16} max={6000} onChange={(w) => setCustom({ w: Math.round(w), h: Math.round(w / ratio) })} />
            <NumberField label="H" value={outH} min={16} max={6000} onChange={(h) => setCustom({ w: Math.round(h * ratio), h: Math.round(h) })} />
          </div>
          {custom && Math.abs(custom.w / custom.h - ratio) > 0.01 && <p className="mt-1.5 text-[10px] text-amber-400">Aspect ratio differs from the canvas ({canvas.width}×{canvas.height}); the image will be stretched to fit.</p>}
        </div>
        <p className="text-[10px] text-ink-400">Exports render the composition only — no selection handles, guides or editor UI.</p>
        {error && <p className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-[11px] text-red-300">{error}</p>}
      </div>
    </Modal>
  );
}
