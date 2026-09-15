import { memo, useState } from 'react';
import { Shape } from 'react-konva';
import type { BackgroundFill } from '@/types/elements';
import { createCanvasGradient } from '@/engine/gradient';
import { getCachedImage } from '@/engine/masking/imageProcessor';
import { useEditorStore } from '@/store/editorStore';

export const BACKGROUND_NODE_NAME = 'background';

export const BackgroundNode = memo(function BackgroundNode({ width, height, fill }: { width: number; height: number; fill: BackgroundFill }) {
  const src = useEditorStore((s) => (fill.kind === 'image' ? s.assets[fill.assetId] : undefined));
  const [, force] = useState(0);
  const img = fill.kind === 'image' ? getCachedImage(fill.assetId, src, () => force((n) => n + 1)) : null;
  return (
    <Shape
      name={BACKGROUND_NODE_NAME}
      width={width}
      height={height}
      perfectDrawEnabled={false}
      sceneFunc={(ctx, shape) => {
        const c = ctx._context;
        c.save();
        if (fill.kind === 'solid') {
          c.fillStyle = fill.color;
          c.fillRect(0, 0, width, height);
        } else if (fill.kind === 'gradient') {
          c.fillStyle = createCanvasGradient(c, fill.gradient, width, height);
          c.fillRect(0, 0, width, height);
        } else {
          c.fillStyle = '#0b0c0f';
          c.fillRect(0, 0, width, height);
          if (img) {
            const scale = Math.max(width / img.naturalWidth, height / img.naturalHeight);
            const dw = img.naturalWidth * scale, dh = img.naturalHeight * scale;
            c.drawImage(img, (width - dw) / 2, (height - dh) / 2, dw, dh);
          }
        }
        c.restore();
        void shape;
      }}
      hitFunc={(ctx, shape) => {
        ctx.beginPath();
        ctx.rect(0, 0, width, height);
        ctx.fillStrokeShape(shape);
      }}
    />
  );
});
