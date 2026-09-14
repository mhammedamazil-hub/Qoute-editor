import type { AnyElement } from '@/types/elements';
import type { SceneDocument } from '@/types/project';
import type { AIGenerateOptions } from '@/types/ai';
import { GeminiClient, GeminiError } from './GeminiClient';
import { SYSTEM_INSTRUCTION } from './GeminiSchemas';
import { validateDesignSpec, type ValidationResult } from './GeminiValidator';

/** Serialize the current scene into the same compact spec the model produces, so it can modify it. */
export function sceneToSpec(doc: SceneDocument): Record<string, unknown> {
  const bg = doc.canvas.background;
  const background = bg.kind === 'solid' ? { type: 'solid', color: bg.color } : bg.kind === 'gradient' ? { type: 'gradient', gradient: bg.gradient } : { type: 'image' };
  const base = (e: AnyElement) => ({
    id: e.id,
    name: e.name,
    opacity: e.opacity,
    rotation: e.rotation || undefined,
    blendMode: e.blendMode !== 'normal' ? e.blendMode : undefined,
    blur: e.blur || undefined,
    glow: e.glow.enabled ? { color: e.glow.color, radius: e.glow.radius, intensity: e.glow.intensity } : undefined,
    shadow: e.shadow.enabled ? { x: e.shadow.x, y: e.shadow.y, blur: e.shadow.blur, color: e.shadow.color, opacity: e.shadow.opacity } : undefined,
  });
  const elements = doc.elements.map((e) => {
      switch (e.type) {
        case 'light':
          return { type: 'light', ...base(e), x: e.x + e.width / 2, y: e.y + e.height / 2, radius: e.width / 2, color: e.color, intensity: e.intensity, softness: e.softness };
        case 'gradient':
          return { type: 'gradient', ...base(e), x: e.x, y: e.y, width: e.width, height: e.height, gradient: e.gradient };
        case 'text':
          return { type: 'text', ...base(e), content: e.content, fontFamily: e.fontFamily, fontSize: e.fontSize, fontWeight: e.fontWeight, italic: e.italic, letterSpacing: e.letterSpacing, lineHeight: e.lineHeight, align: e.align, color: e.fill.kind === 'solid' ? e.fill.color : e.fill.gradient.stops[0].color, x: e.x, y: e.y, width: e.width };
        case 'quoteMark':
          return { type: 'quoteMark', ...base(e), glyph: e.content, fontFamily: e.fontFamily, fontSize: e.fontSize, color: e.fill.kind === 'solid' ? e.fill.color : e.fill.gradient.stops[0].color, x: e.x, y: e.y };
        case 'shape':
          return { type: 'shape', ...base(e), shape: e.shape, x: e.x, y: e.y, width: e.width, height: e.height, fill: e.fill ? (e.fill.kind === 'solid' ? e.fill.color : e.fill.gradient.stops[0].color) : null, stroke: e.stroke, strokeWidth: e.strokeWidth, cornerRadius: e.cornerRadius, sides: e.sides, innerRatio: e.innerRatio, arcAngle: e.arcAngle, spacing: e.spacing };
        case 'particles':
          return { type: 'particle', ...base(e), count: e.count, color: e.color, minSize: e.minSize, maxSize: e.maxSize };
        case 'image':
          return { type: 'image', ...base(e), x: e.x, y: e.y, width: e.width, height: e.height };
        case 'group':
          return { type: 'shape', ...base(e), shape: 'rect', x: e.x, y: e.y, width: e.width, height: e.height, fill: null, stroke: '#000000', strokeWidth: 0 };
      }
    });
  return { canvas: { width: doc.canvas.width, height: doc.canvas.height }, background, elements };
}

function parseJson(text: string): unknown {
  const trimmed = text.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const start = trimmed.indexOf('{'), end = trimmed.lastIndexOf('}');
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(trimmed.slice(start, end + 1));
      } catch {
        /* fallthrough */
      }
    }
    throw new GeminiError('Gemini returned malformed JSON. Please try again.', 'malformed');
  }
}

export class GeminiDesignService {
  constructor(private client: GeminiClient) {}

  async generate(opts: AIGenerateOptions): Promise<ValidationResult> {
    const prompt = [
      `Create a complete, editable quote poster design.`,
      `Brief: ${opts.brief || 'A premium cinematic quote poster.'}`,
      opts.style && `Style: ${opts.style}.`,
      opts.mood && `Mood: ${opts.mood}.`,
      opts.colors && `Color preference: ${opts.colors}.`,
      `Canvas: ${opts.width}×${opts.height} px. Design for exactly this size.`,
      opts.includeImage ? 'The user may add a photo later; leave a natural area for it.' : 'Do not include image elements.',
      `Write an original, meaningful quote if the brief does not provide one; include an author or attribution line.`,
      `Return between 5 and 14 elements: background lighting, 1–3 geometric accents, quote text, author text, optionally a quote mark and particles.`,
    ]
      .filter(Boolean)
      .join('\n');
    const text = await this.client.generateJson(SYSTEM_INSTRUCTION, prompt, { temperature: 0.9 });
    return validateDesignSpec(parseJson(text), null, { width: opts.width, height: opts.height });
  }

  async modify(current: SceneDocument, instruction: string): Promise<ValidationResult> {
    const spec = JSON.stringify(sceneToSpec(current));
    const prompt = [
      `Here is the user's CURRENT design as JSON:`,
      spec,
      ``,
      `Instruction: ${instruction}`,
      ``,
      `Return the FULL updated design in the same JSON format.`,
      `Rules: keep the "id" of every element you retain; keep all text content unchanged unless the instruction asks to change the words;`,
      `never remove the main quote text; keep existing "image" elements (reference by id) unless asked to remove them;`,
      `change only what the instruction requires and leave other properties as they are.`,
    ].join('\n');
    const text = await this.client.generateJson(SYSTEM_INSTRUCTION, prompt, { temperature: 0.5 });
    return validateDesignSpec(parseJson(text), current, { width: current.canvas.width, height: current.canvas.height });
  }
}
