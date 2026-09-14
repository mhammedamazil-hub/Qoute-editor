/**
 * Headless UI smoke test (happy-dom).
 *
 * Run with:  npm run smoke:ui
 *
 * Renders the real React tree — start screen, command palette, panels, copilot —
 * with the real stores, so runtime regressions in the UI surface before shipping.
 * Canvas rendering (Konva) still needs a real browser; that part is skipped.
 */

import { GlobalRegistrator } from '@happy-dom/global-registrator';

GlobalRegistrator.register({ url: 'http://localhost:5173/', width: 1280, height: 900 });

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Minimal shims for APIs happy-dom does not implement.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = RO;
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => undefined;

const { createElement } = await import('react');
const { createRoot } = await import('react-dom/client');
const { act } = await import('react');
const { App } = await import('./app-under-test');
const { useEditorStore } = await import('@/store/editorStore');
const { useSettingsStore } = await import('@/store/settingsStore');
const { useUIStore } = await import('@/store/uiStore');
const { LayerPanel } = await import('@/components/editor/LayerPanel');
const { SelectionToolbar } = await import('@/components/editor/SelectionToolbar');

let failures = 0;
function check(label: string, condition: boolean, detail = '') {
  if (condition) console.log(`  ✓ ${label}`);
  else {
    failures += 1;
    console.error(`  ✗ ${label}${detail ? ` — ${detail}` : ''}`);
  }
}

// happy-dom starts with an empty body — create the app mount point ourselves.
const mount = document.createElement('div');
mount.id = 'root';
document.body.appendChild(mount);
const root = createRoot(mount);

function render(node: unknown) {
  act(() => {
    root.render(node as never);
  });
}

async function typeInto(el: HTMLElement, value: string) {
  await act(async () => {
    const input = el as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
    setter.call(input, value);
    input.dispatchEvent(new window.Event('input', { bubbles: true }));
  });
}

async function click(el: Element) {
  await act(async () => {
    el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  });
}

async function run() {
  console.log('\nStart screen');
  render(createElement(App));
  await act(async () => undefined);
  const body = document.body.textContent ?? '';
  check('renders the app shell', body.includes('QuoteCraft'), body.slice(0, 80));
  check('shows the hero headline', body.includes('Create visually powerful quotes'));
  check('offers the AI entry point', body.includes('Design with AI'));
  check('lists template quick-starts', !!document.querySelector('[data-template]'), String(document.querySelectorAll('[data-template]').length));

  console.log('\nCommand palette');
  await act(async () => {
    useUIStore.getState().setPalette(true);
  });
  let text = document.body.textContent ?? '';
  check('opens', !!document.querySelector('input[aria-label="Search commands"]'));
  check('offers the copilot entry', text.includes('Ask the Copilot'));
  check('offers palettes', text.includes('Midnight & Gold'));
  // Filter by typing.
  const search = document.querySelector('input[aria-label="Search commands"]') as HTMLInputElement;
  await typeInto(search, 'export');
  text = document.body.textContent ?? '';
  check('filters as you type', text.includes('Export image') && !text.includes('Undo'), text.slice(0, 120));
  await act(async () => {
    useUIStore.getState().setPalette(false);
  });

  console.log('\nAppearance');
  await act(async () => {
    useSettingsStore.getState().update({ theme: 'light', accent: '#22d3ee', uiDensity: 'compact' });
  });
  check('light theme applied to <html>', document.documentElement.dataset.theme === 'light', document.documentElement.dataset.theme ?? '');
  check('density attribute applied', document.documentElement.dataset.density === 'compact');
  check('accent variable applied', document.documentElement.style.getPropertyValue('--color-accent') === '#22d3ee');
  await act(async () => {
    useSettingsStore.getState().update({ theme: 'dark', accent: '#d9a441', uiDensity: 'comfortable' });
  });

  console.log('\nCopilot panel');
  await act(async () => {
    useUIStore.getState().setAIOpen(true);
  });
  text = document.body.textContent ?? '';
  check('opens without a key and asks for one', text.includes('Connect Gemini to unlock the copilot'));
  await act(async () => {
    useUIStore.getState().setAIOpen(false);
  });

  console.log('\nEditor panels (canvas-free)');
  // Unmount the app shell first: switching to the editor screen would mount the
  // Konva stage, which needs a real canvas implementation (browser only).
  act(() => root.unmount());
  await act(async () => {
    useEditorStore.getState().newDocument(1080, 1350);
  });
  useEditorStore.getState().clearSelection();
  const panelHost = document.createElement('div');
  document.body.appendChild(panelHost);
  const panelRoot = createRoot(panelHost);
  act(() => {
    panelRoot.render(createElement(LayerPanel) as never);
  });
  check('layer panel renders the empty state', (panelHost.textContent ?? '').includes('No layers yet'));
  await act(async () => {
    const s = useEditorStore.getState();
    const el = {
      ...s.doc.elements[0],
      id: 'layer-test-1',
      name: 'Main Quote',
      type: 'text' as const,
    };
    s.addElement(el as never);
  });
  check('layer panel lists a new layer', (panelHost.textContent ?? '').includes('Main Quote'), (panelHost.textContent ?? '').slice(0, 80));
  check('background row is present', (panelHost.textContent ?? '').includes('Background'));

  useEditorStore.getState().clearSelection();
  const toolbarHost = document.createElement('div');
  document.body.appendChild(toolbarHost);
  const toolbarRoot = createRoot(toolbarHost);
  act(() => {
    toolbarRoot.render(createElement(SelectionToolbar) as never);
  });
  check('selection toolbar hides without a selection', toolbarHost.querySelector('button') === null);
  await act(async () => {
    useEditorStore.getState().select(['layer-test-1']);
  });
  act(() => {
    toolbarRoot.render(createElement(SelectionToolbar) as never);
  });
  const dupBtn = toolbarHost.querySelector('button[aria-label^="Duplicate"]');
  check('selection toolbar appears with a selection', !!dupBtn, toolbarHost.textContent ?? '');
  if (dupBtn) {
    await click(dupBtn);
    check('duplicate action adds a copy', useEditorStore.getState().doc.elements.length === 2, String(useEditorStore.getState().doc.elements.length));
  }

  console.log(`\n${failures === 0 ? '✅ all checks passed' : `❌ ${failures} check(s) failed`}\n`);
  process.exit(failures === 0 ? 0 : 1);
}

await run();
