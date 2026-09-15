import {
  AlignCenterHorizontal,
  AlignCenterVertical,
  AlignEndHorizontal,
  AlignEndVertical,
  AlignHorizontalDistributeCenter,
  AlignStartHorizontal,
  AlignStartVertical,
  AlignVerticalDistributeCenter,
  Crosshair,
} from 'lucide-react';
import { useEditorStore } from '@/store/editorStore';

const BUTTONS = [
  { mode: 'left', label: 'Align left', Icon: AlignStartVertical },
  { mode: 'hcenter', label: 'Center horizontally', Icon: AlignCenterVertical },
  { mode: 'right', label: 'Align right', Icon: AlignEndVertical },
  { mode: 'top', label: 'Align top', Icon: AlignStartHorizontal },
  { mode: 'vcenter', label: 'Center vertically', Icon: AlignCenterHorizontal },
  { mode: 'bottom', label: 'Align bottom', Icon: AlignEndHorizontal },
  { mode: 'dist-h', label: 'Distribute horizontally', Icon: AlignHorizontalDistributeCenter },
  { mode: 'dist-v', label: 'Distribute vertically', Icon: AlignVerticalDistributeCenter },
  { mode: 'canvas', label: 'Center on canvas', Icon: Crosshair },
] as const;

export function AlignmentToolbar() {
  const align = useEditorStore((s) => s.alignSelected);
  const count = useEditorStore((s) => s.selectedIds.length);
  return (
    <div className="flex flex-wrap gap-0.5" role="toolbar" aria-label="Alignment">
      {BUTTONS.map(({ mode, label, Icon }) => (
        <button key={mode} type="button" className="icon-btn h-7 w-7" title={label} aria-label={label} disabled={(mode === 'dist-h' || mode === 'dist-v') && count < 3} onClick={() => align(mode)}>
          <Icon size={14} />
        </button>
      ))}
    </div>
  );
}
