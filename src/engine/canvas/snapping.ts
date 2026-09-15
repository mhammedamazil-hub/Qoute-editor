import type { AnyElement } from '@/types/elements';
import type { Guide } from '@/store/editorStore';

export interface SnapResult {
  x: number;
  y: number;
  guides: Guide[];
}

/** Snaps a moving box (x,y,w,h in canvas units) to canvas edges/center and other elements. */
export function computeSnap(
  box: { x: number; y: number; w: number; h: number },
  others: AnyElement[],
  canvas: { width: number; height: number },
  threshold: number,
): SnapResult {
  const vLines = [0, canvas.width / 2, canvas.width];
  const hLines = [0, canvas.height / 2, canvas.height];
  for (const o of others) {
    if (o.parentId || !o.visible) continue;
    vLines.push(o.x, o.x + o.width / 2, o.x + o.width);
    hLines.push(o.y, o.y + o.height / 2, o.y + o.height);
  }
  const guides: Guide[] = [];
  let x = box.x, y = box.y;
  let bestDx = threshold + 1, bestV: number | null = null, bestOffX = 0;
  for (const line of vLines) {
    for (const off of [0, box.w / 2, box.w]) {
      const d = Math.abs(box.x + off - line);
      if (d < bestDx) {
        bestDx = d;
        bestV = line;
        bestOffX = off;
      }
    }
  }
  if (bestV !== null && bestDx <= threshold) {
    x = bestV - bestOffX;
    guides.push({ orientation: 'v', position: bestV });
  }
  let bestDy = threshold + 1, bestH: number | null = null, bestOffY = 0;
  for (const line of hLines) {
    for (const off of [0, box.h / 2, box.h]) {
      const d = Math.abs(box.y + off - line);
      if (d < bestDy) {
        bestDy = d;
        bestH = line;
        bestOffY = off;
      }
    }
  }
  if (bestH !== null && bestDy <= threshold) {
    y = bestH - bestOffY;
    guides.push({ orientation: 'h', position: bestH });
  }
  return { x, y, guides };
}
