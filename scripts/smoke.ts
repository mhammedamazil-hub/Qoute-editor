/**
 * Headless smoke test for the AI tool layer + store wiring.
 *
 * Run with:  npm run smoke
 *
 * It exercises the exact functions the copilot calls, so a regression in the
 * editor stores or a tool signature shows up before it reaches the browser.
 */

import { executeTool } from '@/ai/agent/tools';
import { useEditorStore } from '@/store/editorStore';
import { useSettingsStore } from '@/store/settingsStore';
import { DEFAULT_MODEL, FALLBACK_MODELS, migrateModelId, modelRank, pickBestAvailableModel } from '@/ai/gemini/models';
import { TOOL_DECLARATIONS } from '@/ai/agent/tools';

const ctx = { apiKey: 'test-key', model: DEFAULT_MODEL };
let failures = 0;

function check(label: string, condition: boolean, detail = '') {
  if (condition) {
    console.log(`  ✓ ${label}`);
  } else {
    failures += 1;
    console.error(`  ✗ ${label}${detail ? ` — ${detail}` : ''}`);
  }
}

async function run() {
  console.log('\nModel catalog');
  check('default model is the latest Flash', DEFAULT_MODEL === 'gemini-3.8-flash', DEFAULT_MODEL);
  check('retired 2.5 Flash migrates to the default', migrateModelId('gemini-2.5-flash').model === DEFAULT_MODEL);
  check('retired 2.0 Flash migrates to the default', migrateModelId('gemini-2.0-flash').model === DEFAULT_MODEL);
  check('a valid model is kept', migrateModelId('gemini-3.7-flash').model === 'gemini-3.7-flash');
  check('unknown-but-newer models outrank the curated list', modelRank('gemini-4.0-flash') > modelRank('gemini-3.8-flash'));
  check('best available model picks the newest', pickBestAvailableModel(['gemini-2.5-flash', 'gemini-3.8-flash']) === 'gemini-3.8-flash');
  check('fallback chain starts at the default', FALLBACK_MODELS[0] === DEFAULT_MODEL);
  check('tool declarations are unique', new Set(TOOL_DECLARATIONS.map((d) => d.name)).size === TOOL_DECLARATIONS.length);

  console.log('\nTool layer');
  useEditorStore.getState().newDocument(1080, 1350);
  check('canvas created at the requested size', useEditorStore.getState().doc.canvas.width === 1080);

  const state = await executeTool('get_app_state', {}, ctx);
  check('get_app_state returns the canvas', state.ok && (state.data?.state as { canvas: { width: number } }).canvas.width === 1080);

  const text = await executeTool('add_text', { role: 'quote', content: 'Discipline is freedom.', x: 140, y: 520, width: 800, fontSize: 64 }, ctx);
  check('add_text adds a text layer', text.ok && useEditorStore.getState().doc.elements.some((e) => e.type === 'text'));

  await executeTool('add_text', { role: 'author', content: '— A. LINCOLN', x: 140, y: 900 }, ctx);
  await executeTool('add_shape', { shape: 'circle', x: 600, y: 120, width: 420, height: 420, fill: null, stroke: '#d9a441', strokeWidth: 1.5, opacity: 0.35 }, ctx);
  const light = await executeTool('add_light', { x: 520, y: -200, radius: 900, color: '#d89b35', intensity: 0.5 }, ctx);
  check('add_light adds and orders a light', light.ok && useEditorStore.getState().doc.elements[0].type === 'light');

  const palette = await executeTool('apply_palette', { palette: 'emerald-luxury' }, ctx);
  check('apply_palette restyles the scene', palette.ok && useEditorStore.getState().doc.canvas.background.kind === 'solid');

  const typo = await executeTool('set_typography', { types: ['text'], fontFamily: 'Cormorant Garamond', fontSize: 58, align: 'center' }, ctx);
  const firstText = useEditorStore.getState().doc.elements.find((e) => e.type === 'text')!;
  check('set_typography applies font + size', typo.ok && firstText.type === 'text' && firstText.fontFamily === 'Cormorant Garamond' && firstText.fontSize === 58, firstText.type === 'text' ? `${firstText.fontFamily}/${firstText.fontSize}` : 'n/a');
  check('unknown fonts fall back safely', (await executeTool('set_typography', { types: ['text'], fontFamily: 'Comic Sans MS' }, ctx)).ok && useEditorStore.getState().doc.elements.find((e) => e.type === 'text')!.fontFamily !== 'Comic Sans MS');

  const moved = await executeTool('translate_elements', { types: ['text'], dx: 0, dy: 40 }, ctx);
  check('translate_elements moves layers', moved.ok);

  await executeTool('duplicate_elements', { types: ['shape'] }, ctx);
  check('duplicate_elements copies', useEditorStore.getState().doc.elements.filter((e) => e.type === 'shape').length === 2);

  const align = await executeTool('align_elements', { types: ['text'], mode: 'canvas' }, ctx);
  check('align_elements centres layers', align.ok);

  const group = await executeTool('group_elements', { types: ['text'] }, ctx);
  check('group_elements groups two text layers', group.ok && useEditorStore.getState().doc.elements.some((e) => e.type === 'group'));

  const clean = await executeTool('delete_elements', { types: ['shape'] }, ctx);
  check('delete_elements removes geometry', clean.ok && useEditorStore.getState().doc.elements.every((e) => e.type !== 'shape'));

  const guard = await executeTool('delete_elements', { types: ['text'] }, ctx);
  check('delete guard keeps a text layer', guard.ok && useEditorStore.getState().doc.elements.some((e) => e.type === 'text'));

  const undo = await executeTool('undo', {}, ctx);
  check('undo restores layers', undo.ok);

  const zoom = await executeTool('zoom', { level: '100%' }, ctx);
  check('zoom works headlessly', zoom.ok);

  const ui = await executeTool('set_ui_preference', { theme: 'light', accent: '#22d3ee', density: 'compact' }, ctx);
  check('set_ui_preference writes settings', ui.ok && useSettingsStore.getState().theme === 'light' && useSettingsStore.getState().accent === '#22d3ee');
  await executeTool('set_ui_preference', { theme: 'dark', accent: '#d9a441', density: 'comfortable' }, ctx);

  const template = await executeTool('apply_template', { id: 'black-gold', quote: 'Test quote for the template.' }, ctx);
  check('apply_template loads a template', template.ok && useEditorStore.getState().doc.elements.length > 3);
  check('template quote replacement works', useEditorStore.getState().doc.elements.some((e) => e.type === 'text' && e.content === 'Test quote for the template.'));

  const bad = await executeTool('not_a_tool', {}, ctx);
  check('unknown tools fail gracefully', !bad.ok);

  console.log(`\n${failures === 0 ? '✅ all checks passed' : `❌ ${failures} check(s) failed`}\n`);
  process.exit(failures === 0 ? 0 : 1);
}

void run();
