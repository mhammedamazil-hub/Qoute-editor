export type AIStatus = 'not-configured' | 'configured' | 'connected' | 'invalid' | 'failed';

export type AIActionId =
  | 'improve'
  | 'premium'
  | 'minimal'
  | 'cinematic'
  | 'elegant'
  | 'colors'
  | 'typography'
  | 'rearrange'
  | 'add-lighting'
  | 'remove-decorations'
  | 'increase-contrast'
  | 'reduce-contrast'
  | 'negative-space'
  | 'dramatic-lighting';

export interface AIAction {
  id: AIActionId;
  label: string;
  instruction: string;
}

export const AI_ACTIONS: AIAction[] = [
  { id: 'improve', label: 'Improve Design', instruction: 'Improve the overall design quality: hierarchy, spacing, alignment, and polish. Keep the content and general concept.' },
  { id: 'premium', label: 'Make Premium', instruction: 'Make this design feel more premium and luxurious: refined typography, restrained gold/warm lighting, thin lines, generous negative space.' },
  { id: 'minimal', label: 'Make Minimal', instruction: 'Make the design more minimal. Remove or reduce unnecessary decorative elements, keep the quote and author, simplify colors. Never remove the main quote text.' },
  { id: 'cinematic', label: 'Make Cinematic', instruction: 'Make the design more cinematic: darker background, atmospheric soft lights, dramatic contrast, subtle particles.' },
  { id: 'elegant', label: 'Make Elegant', instruction: 'Make the design more elegant: serif typography, soft tones, balanced composition, delicate lines.' },
  { id: 'colors', label: 'Change Colors', instruction: 'Propose a new harmonious color palette for backgrounds, lights, and text. Keep layout and content unchanged.' },
  { id: 'typography', label: 'Change Typography', instruction: 'Change the typography to a different but well-paired font combination. Keep the text content and approximate layout.' },
  { id: 'rearrange', label: 'Rearrange', instruction: 'Rearrange the composition into a different but balanced layout while keeping all content.' },
  { id: 'add-lighting', label: 'Add Lighting', instruction: 'Add one or two atmospheric light layers that complement the palette. Do not change text.' },
  { id: 'remove-decorations', label: 'Remove Decorations', instruction: 'Remove decorative shapes, lines, particles and quote marks. Keep background, lights, text.' },
  { id: 'increase-contrast', label: 'Increase Contrast', instruction: 'Increase visual contrast between text and background: brighter text, darker or more focused background, stronger lighting differences.' },
  { id: 'reduce-contrast', label: 'Reduce Contrast', instruction: 'Reduce harshness: soften contrast slightly, mute lights, warm the text color a little. Keep readability.' },
  { id: 'negative-space', label: 'More Negative Space', instruction: 'Create more negative space: reduce element sizes, tighten the text block, move decorations toward edges.' },
  { id: 'dramatic-lighting', label: 'Dramatic Lighting', instruction: 'Make the lighting more dramatic: stronger focused light source with a deeper dark falloff, secondary cool rim light.' },
];

export interface AIGenerateOptions {
  brief: string;
  style: string;
  mood: string;
  colors: string;
  width: number;
  height: number;
  includeImage: boolean;
}
