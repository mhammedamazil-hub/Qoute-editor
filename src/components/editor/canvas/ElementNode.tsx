import { memo, useEffect, useMemo, useRef, useState } from 'react';
import Konva from 'konva';
import { Group, Rect, Ellipse, Circle, Text, Shape, Image as KImage } from 'react-konva';
import type {
  AnyElement,
  GradientElement,
  ImageElement,
  LightElement,
  ParticlesElement,
  ShapeElement,
  TextElement,
} from '@/types/elements';
import { useEditorStore } from '@/store/editorStore';
import { konvaFillProps, createCanvasGradient } from '@/engine/gradient';
import { withAlpha } from '@/engine/color';
import { getCachedImage, processImage, processKey } from '@/engine/masking/imageProcessor';

export const ELEMENT_CLASS = 'element';

/* ---------- helpers ---------- */

function compositeOp(mode: AnyElement['blendMode']): GlobalCompositeOperation {
  return mode === 'normal' ? 'source-over' : (mode as GlobalCompositeOperation);
}

function shadowProps(el: AnyElement) {
  if (el.glow.enabled) {
    return { shadowColor: el.glow.color, shadowBlur: el.glow.radius, shadowOpacity: el.glow.intensity, shadowOffsetX: 0, shadowOffsetY: 0, shadowEnabled: true };
  }
  if (el.shadow.enabled) {
    return { shadowColor: el.shadow.color, shadowBlur: el.shadow.blur, shadowOpacity: el.shadow.opacity, shadowOffsetX: el.shadow.x, shadowOffsetY: el.shadow.y, shadowEnabled: true };
  }
  return { shadowEnabled: false };
}

/** Second pass: when both glow and shadow are enabled, draw the shadow copy underneath. */
function needsShadowPass(el: AnyElement) {
  return el.glow.enabled && el.shadow.enabled;
}

function useBlurCache(ref: React.RefObject<Konva.Group | null>, el: AnyElement, extraDeps: unknown[] = []) {
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (el.blur > 0 && el.visible) {
      try {
        node.cache({ offset: Math.ceil(el.blur * 3) + 4, pixelRatio: 1 });
        node.filters([Konva.Filters.Blur]);
        node.blurRadius(el.blur);
      } catch {
        node.clearCache();
      }
    } else if (node.isCached()) {
      node.clearCache();
      node.filters([]);
    }
    node.getLayer()?.batchDraw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [el, ...extraDeps]);
}

function silentPatch(id: string, patch: Partial<AnyElement>) {
  useEditorStore.setState((s) => ({
    doc: { ...s.doc, elements: s.doc.elements.map((e) => (e.id === id ? ({ ...e, ...patch } as AnyElement) : e)) },
  }));
}

/* ---------- text ---------- */

function TextContent({ el, pass }: { el: TextElement; pass: 'main' | 'shadow' }) {
  const fontsVersion = useEditorStore((s) => s.fontsVersion);
  const ref = useRef<Konva.Text>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node || pass !== 'main') return;
    const h = node.height();
    if (Math.abs(h - el.height) > 0.5) silentPatch(el.id, { height: h });
  });
  const fill = konvaFillProps(el.fill, el.width, el.height);
  const sp = pass === 'shadow'
    ? { shadowColor: el.shadow.color, shadowBlur: el.shadow.blur, shadowOpacity: el.shadow.opacity, shadowOffsetX: el.shadow.x, shadowOffsetY: el.shadow.y, shadowEnabled: true }
    : shadowProps(el);
  return (
    <Text
      key={fontsVersion}
      ref={ref}
      text={el.content}
      width={el.width}
      fontFamily={`"${el.fontFamily}", serif`}
      fontSize={el.fontSize}
      fontStyle={`${el.italic ? 'italic ' : ''}${el.fontWeight}`}
      textDecoration={el.underline ? 'underline' : ''}
      letterSpacing={el.letterSpacing}
      lineHeight={el.lineHeight}
      align={el.align}
      wrap="word"
      stroke={el.strokeWidth > 0 ? el.stroke : undefined}
      strokeWidth={el.strokeWidth > 0 ? el.strokeWidth : 0}
      fillAfterStrokeEnabled
      perfectDrawEnabled={false}
      {...fill}
      {...sp}
    />
  );
}

/* ---------- shapes ---------- */

function polygonPoints(w: number, h: number, sides: number, innerRatio?: number): number[] {
  const pts: number[] = [];
  const cx = w / 2, cy = h / 2;
  const total = innerRatio !== undefined ? sides * 2 : sides;
  for (let i = 0; i < total; i++) {
    const a = -Math.PI / 2 + (i / total) * Math.PI * 2;
    const r = innerRatio !== undefined && i % 2 === 1 ? innerRatio : 1;
    pts.push(cx + Math.cos(a) * (w / 2) * r, cy + Math.sin(a) * (h / 2) * r);
  }
  return pts;
}

function ShapeContent({ el, pass }: { el: ShapeElement; pass: 'main' | 'shadow' }) {
  const w = el.width, h = el.height;
  const sp = pass === 'shadow'
    ? { shadowColor: el.shadow.color, shadowBlur: el.shadow.blur, shadowOpacity: el.shadow.opacity, shadowOffsetX: el.shadow.x, shadowOffsetY: el.shadow.y, shadowEnabled: true }
    : shadowProps(el);
  const common = {
    ...konvaFillProps(el.fill, w, h),
    stroke: el.strokeWidth > 0 ? el.stroke : undefined,
    strokeWidth: el.strokeWidth,
    dash: el.dashed ? [Math.max(4, el.strokeWidth * 4), Math.max(4, el.strokeWidth * 3)] : undefined,
    hitStrokeWidth: Math.max(12, el.strokeWidth),
    perfectDrawEnabled: false,
    ...sp,
  };
  switch (el.shape) {
    case 'rect':
    case 'roundedRect':
      return <Rect width={w} height={h} cornerRadius={el.shape === 'roundedRect' ? el.cornerRadius : 0} {...common} />;
    case 'circle':
    case 'ellipse':
      return <Ellipse x={w / 2} y={h / 2} radiusX={w / 2} radiusY={h / 2} {...common} />;
    default:
      break;
  }
  const sceneFunc = (ctx: Konva.Context, shape: Konva.Shape) => {
    const c = ctx as unknown as CanvasRenderingContext2D & Konva.Context;
    c.beginPath();
    switch (el.shape) {
      case 'triangle': {
        c.moveTo(w / 2, 0);
        c.lineTo(w, h);
        c.lineTo(0, h);
        c.closePath();
        break;
      }
      case 'polygon':
      case 'star': {
        const pts = el.shape === 'star' ? polygonPoints(w, h, Math.max(3, el.sides), el.innerRatio) : polygonPoints(w, h, Math.max(3, el.sides));
        c.moveTo(pts[0], pts[1]);
        for (let i = 2; i < pts.length; i += 2) c.lineTo(pts[i], pts[i + 1]);
        c.closePath();
        break;
      }
      case 'line': {
        if (h > w) {
          c.moveTo(w / 2, 0);
          c.lineTo(w / 2, h);
        } else {
          c.moveTo(0, h / 2);
          c.lineTo(w, h / 2);
        }
        break;
      }
      case 'arrow': {
        if (h > w) {
          const head = Math.min(h * 0.25, Math.max(10, el.strokeWidth * 5));
          c.moveTo(w / 2, 0);
          c.lineTo(w / 2, h);
          c.moveTo(w / 2 - head * 0.6, h - head);
          c.lineTo(w / 2, h);
          c.lineTo(w / 2 + head * 0.6, h - head);
        } else {
          const head = Math.min(w * 0.25, Math.max(10, el.strokeWidth * 5));
          c.moveTo(0, h / 2);
          c.lineTo(w, h / 2);
          c.moveTo(w - head, h / 2 - head * 0.6);
          c.lineTo(w, h / 2);
          c.lineTo(w - head, h / 2 + head * 0.6);
        }
        break;
      }
      case 'ring': {
        const cx = w / 2, cy = h / 2, r = Math.min(w, h) / 2;
        c.arc(cx, cy, r, 0, Math.PI * 2, false);
        c.moveTo(cx + r * el.innerRatio, cy);
        c.arc(cx, cy, Math.max(0, r * el.innerRatio), 0, Math.PI * 2, true);
        c.closePath();
        break;
      }
      case 'arc': {
        const cx = w / 2, cy = h / 2;
        const start = -Math.PI / 2 - (el.arcAngle * Math.PI) / 360;
        const end = start + (el.arcAngle * Math.PI) / 180;
        c.ellipse(cx, cy, w / 2, h / 2, 0, start, end);
        break;
      }
      case 'cornerFrame': {
        const L = Math.min(el.spacing, w / 2, h / 2);
        c.moveTo(0, L); c.lineTo(0, 0); c.lineTo(L, 0);
        c.moveTo(w - L, 0); c.lineTo(w, 0); c.lineTo(w, L);
        c.moveTo(w, h - L); c.lineTo(w, h); c.lineTo(w - L, h);
        c.moveTo(L, h); c.lineTo(0, h); c.lineTo(0, h - L);
        break;
      }
      case 'grid': {
        const s = Math.max(8, el.spacing);
        for (let x = 0; x <= w + 0.5; x += s) { c.moveTo(x, 0); c.lineTo(x, h); }
        for (let y = 0; y <= h + 0.5; y += s) { c.moveTo(0, y); c.lineTo(w, y); }
        break;
      }
      case 'dots': {
        const s = Math.max(6, el.spacing);
        const r = Math.max(0.5, s * 0.08);
        for (let x = r; x <= w; x += s) for (let y = r; y <= h; y += s) { c.moveTo(x + r, y); c.arc(x, y, r, 0, Math.PI * 2); }
        break;
      }
      case 'crosshair': {
        const cx = w / 2, cy = h / 2, r = Math.min(w, h) / 2;
        c.moveTo(cx - r, cy); c.lineTo(cx + r, cy);
        c.moveTo(cx, cy - r); c.lineTo(cx, cy + r);
        c.moveTo(cx + r * 0.55, cy); c.arc(cx, cy, r * 0.55, 0, Math.PI * 2);
        break;
      }
      case 'plus': {
        c.moveTo(0, h / 2); c.lineTo(w, h / 2);
        c.moveTo(w / 2, 0); c.lineTo(w / 2, h);
        break;
      }
      default:
        c.rect(0, 0, w, h);
    }
    ctx.fillStrokeShape(shape);
  };
  const hitFunc = (ctx: Konva.Context, shape: Konva.Shape) => {
    ctx.beginPath();
    ctx.rect(-6, -6, w + 12, h + 12);
    ctx.fillStrokeShape(shape);
  };
  return <Shape width={w} height={h} sceneFunc={sceneFunc} hitFunc={hitFunc} {...common} />;
}

/* ---------- light ---------- */

function lightStops(el: LightElement): (number | string)[] {
  const stops: (number | string)[] = [];
  const hard = 1 - Math.min(0.999, el.softness);
  for (let i = 0; i <= 12; i++) {
    const t = i / 12;
    let a: number;
    if (t <= hard) a = 1;
    else {
      const k = (t - hard) / Math.max(0.001, 1 - hard);
      a = Math.pow(1 - k, 2.2);
    }
    stops.push(t, withAlpha(el.color, el.intensity * a));
  }
  return stops;
}

function LightContent({ el }: { el: LightElement }) {
  const w = el.width, h = el.height;
  const stops = useMemo(() => lightStops(el), [el]);
  const R = Math.max(w, h) / 2;
  return (
    <Circle
      x={w / 2}
      y={h / 2}
      radius={R}
      scaleX={w / (2 * R)}
      scaleY={h / (2 * R)}
      fillPriority="radial-gradient"
      fillRadialGradientStartPoint={{ x: 0, y: 0 }}
      fillRadialGradientEndPoint={{ x: 0, y: 0 }}
      fillRadialGradientStartRadius={0}
      fillRadialGradientEndRadius={R}
      fillRadialGradientColorStops={stops}
      perfectDrawEnabled={false}
      hitFunc={(ctx, shape) => {
        ctx.beginPath();
        ctx.arc(0, 0, R * 0.35, 0, Math.PI * 2);
        ctx.fillStrokeShape(shape);
      }}
    />
  );
}

/* ---------- gradient layer ---------- */

function GradientContent({ el }: { el: GradientElement }) {
  const w = el.width, h = el.height;
  return (
    <Shape
      width={w}
      height={h}
      perfectDrawEnabled={false}
      sceneFunc={(ctx, shape) => {
        const native = ctx._context;
        native.save();
        native.fillStyle = createCanvasGradient(native, el.gradient, w, h);
        native.fillRect(0, 0, w, h);
        native.restore();
        void shape;
      }}
      hitFunc={(ctx, shape) => {
        ctx.beginPath();
        ctx.rect(0, 0, w, h);
        ctx.fillStrokeShape(shape);
      }}
    />
  );
}

/* ---------- particles ---------- */

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function ParticlesContent({ el }: { el: ParticlesElement }) {
  const pts = useMemo(() => {
    const rnd = mulberry32(el.seed);
    return Array.from({ length: Math.min(600, el.count) }, () => ({ x: rnd(), y: rnd(), r: el.minSize + rnd() * (el.maxSize - el.minSize), a: 0.3 + rnd() * 0.7 }));
  }, [el.seed, el.count, el.minSize, el.maxSize]);
  const w = el.width, h = el.height;
  return (
    <Shape
      width={w}
      height={h}
      perfectDrawEnabled={false}
      sceneFunc={(ctx, shape) => {
        const c = ctx._context;
        for (const p of pts) {
          c.beginPath();
          c.fillStyle = withAlpha(el.color, p.a);
          c.arc(p.x * w, p.y * h, p.r, 0, Math.PI * 2);
          c.fill();
        }
        void shape;
      }}
      hitFunc={(ctx, shape) => {
        ctx.beginPath();
        ctx.rect(0, 0, w, h);
        ctx.fillStrokeShape(shape);
      }}
    />
  );
}

/* ---------- image ---------- */

function ImageContent({ el, pass }: { el: ImageElement; pass: 'main' | 'shadow' }) {
  const src = useEditorStore((s) => s.assets[el.assetId]);
  const [, force] = useState(0);
  const img = getCachedImage(el.assetId, src, () => force((n) => n + 1));
  const key = processKey(el, el.width, el.height);
  const processed = useMemo(() => (img ? processImage(img, el, el.width, el.height) : null), [img, key]); // eslint-disable-line react-hooks/exhaustive-deps
  const imgRef = useRef<Konva.Image>(null);
  // If the wrapping element group is blur-cached, refresh the cache once the image is ready.
  useEffect(() => {
    const node = imgRef.current;
    if (!node || !processed) return;
    const parent = node.findAncestor(`.${ELEMENT_CLASS}`) as Konva.Group | null;
    if (parent && parent.isCached()) {
      parent.clearCache();
      parent.cache({ offset: Math.ceil(el.blur * 3) + 4, pixelRatio: 1 });
    }
    node.getLayer()?.batchDraw();
  }, [processed, el.blur]);
  const sp = pass === 'shadow'
    ? { shadowColor: el.shadow.color, shadowBlur: el.shadow.blur, shadowOpacity: el.shadow.opacity, shadowOffsetX: el.shadow.x, shadowOffsetY: el.shadow.y, shadowEnabled: true }
    : shadowProps(el);
  if (!processed) return <Rect width={el.width} height={el.height} fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" dash={[6, 6]} />;
  return <KImage ref={imgRef} image={processed} width={el.width} height={el.height} perfectDrawEnabled={false} {...sp} />;
}

/* ---------- main ---------- */

export interface ElementNodeProps {
  el: AnyElement;
  children?: AnyElement[];
  allElements: AnyElement[];
  interactive: boolean;
  isSelected: boolean;
  editingGroupId: string | null;
  onDragMove: (e: Konva.KonvaEventObject<DragEvent>, el: AnyElement) => void;
  onDragEnd: (e: Konva.KonvaEventObject<DragEvent>, el: AnyElement) => void;
  onTransformEnd: (e: Konva.KonvaEventObject<Event>, el: AnyElement) => void;
}

function renderContent(el: AnyElement, pass: 'main' | 'shadow') {
  switch (el.type) {
    case 'text':
    case 'quoteMark':
      return <TextContent el={el} pass={pass} />;
    case 'shape':
      return <ShapeContent el={el} pass={pass} />;
    case 'light':
      return <LightContent el={el} />;
    case 'gradient':
      return <GradientContent el={el} />;
    case 'particles':
      return <ParticlesContent el={el} />;
    case 'image':
      return <ImageContent el={el} pass={pass} />;
    default:
      return null;
  }
}

export const ElementNode = memo(function ElementNode(props: ElementNodeProps) {
  const { el, children, allElements, interactive, isSelected, editingGroupId } = props;
  const ref = useRef<Konva.Group>(null);
  const fontsVersion = useEditorStore((s) => s.fontsVersion);
  useBlurCache(ref, el, [children, fontsVersion]);

  const editableHere = interactive && !el.locked && (el.parentId ?? null) === editingGroupId;
  const passiveType = el.type === 'gradient' || el.type === 'particles' || (el.type === 'shape' && el.shape === 'grid');
  const listening = interactive && el.visible && (!passiveType || isSelected);

  if (!el.visible) return null;

  const isGroup = el.type === 'group';

  return (
    <Group
      ref={ref}
      id={el.id}
      name={ELEMENT_CLASS}
      x={el.x}
      y={el.y}
      rotation={el.rotation}
      scaleX={isGroup ? el.scaleX : 1}
      scaleY={isGroup ? el.scaleY : 1}
      opacity={el.opacity}
      globalCompositeOperation={compositeOp(el.blendMode)}
      draggable={editableHere}
      listening={listening}
      onDragMove={(e) => props.onDragMove(e, el)}
      onDragEnd={(e) => props.onDragEnd(e, el)}
      onTransformEnd={(e) => props.onTransformEnd(e, el)}
    >
      {isGroup ? (
        <>
          <Rect width={el.width} height={el.height} fill="transparent" listening={listening} />
          {(children ?? []).map((child) => (
            <ElementNode
              key={child.id}
              el={child}
              allElements={allElements}
              children={allElements.filter((c) => c.parentId === child.id)}
              interactive={interactive}
              isSelected={isSelected}
              editingGroupId={editingGroupId}
              onDragMove={props.onDragMove}
              onDragEnd={props.onDragEnd}
              onTransformEnd={props.onTransformEnd}
            />
          ))}
        </>
      ) : (
        <>
          {needsShadowPass(el) && <Group listening={false}>{renderContent(el, 'shadow')}</Group>}
          {renderContent(el, 'main')}
        </>
      )}
    </Group>
  );
});
