/**
 * Editor bridge — exposes the real tool layer (`src/ai/agent/tools.ts`) to the
 * Python brain over newline-delimited JSON on stdin/stdout.
 *
 * This is what makes MiniCoder's "autonomous software engineer" claim real: the
 * Python side does not simulate an editor, it drives the shipped one, and the
 * resulting store state is the ground truth used to verify an action.
 *
 * Protocol (one JSON object per line):
 *   -> {"id":"1","op":"list"}
 *   <- {"id":"1","ok":true,"tools":[{"name":"add_text","description":"..."}]}
 *   -> {"id":"2","op":"call","tool":"add_text","args":{...}}
 *   <- {"id":"2","ok":true,"result":{"ok":true,"summary":"..."},"state":{...}}
 *   -> {"id":"3","op":"state"}
 *   <- {"id":"3","ok":true,"state":{...}}
 *   -> {"id":"4","op":"reset","width":1080,"height":1350}
 *   <- {"id":"4","ok":true}
 *
 * Run: npx vite-node scripts/editor-bridge.ts
 */
import readline from 'node:readline';

import { TOOL_DECLARATIONS, executeTool, designSnapshot, type ToolContext } from '@/ai/agent/tools';
import { useEditorStore } from '@/store/editorStore';

const ctx: ToolContext = { apiKey: 'bridge', model: 'bridge' };

function compactState() {
  const s = useEditorStore.getState();
  const canvas = s.canvas;
  const doc = (s as unknown as { doc?: { elements?: unknown[] } }).doc;
  const elements = (doc?.elements ?? canvas?.elements ?? []) as Array<Record<string, unknown>>;
  return {
    canvas: canvas ? { width: canvas.width, height: canvas.height, background: canvas.background } : null,
    elementCount: elements.length,
    elements: elements.slice(0, 40).map((el) => ({
      id: el.id,
      type: el.type,
      name: el.name,
      text: typeof el.text === 'string' ? el.text.slice(0, 80) : undefined,
      x: el.x,
      y: el.y,
      width: el.width ?? (el as { w?: number }).w,
      height: el.height ?? (el as { h?: number }).h,
      parentId: (el as { parentId?: string }).parentId,
    })),
    selection: (s as unknown as { selection?: string[] }).selection ?? [],
    snapshot: designSnapshot(false),
  };
}

function reply(obj: unknown) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on('line', async (line: string) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let msg: Record<string, unknown>;
  try {
    msg = JSON.parse(trimmed);
  } catch {
    reply({ ok: false, error: 'invalid json' });
    return;
  }
  const id = msg.id ?? null;
  try {
    switch (msg.op) {
      case 'list': {
        reply({
          id,
          ok: true,
          tools: TOOL_DECLARATIONS.map((d) => ({
            name: d.name,
            description: d.description,
            parameters: d.parameters ?? null,
          })),
        });
        break;
      }
      case 'reset': {
        const width = Number(msg.width ?? 1080);
        const height = Number(msg.height ?? 1350);
        useEditorStore.getState().newDocument(width, height);
        reply({ id, ok: true, state: compactState() });
        break;
      }
      case 'state': {
        reply({ id, ok: true, state: compactState() });
        break;
      }
      case 'call': {
        const tool = String(msg.tool ?? '');
        const args = (msg.args ?? {}) as Record<string, unknown>;
        const result = await executeTool(tool, args, ctx);
        reply({ id, ok: true, result, state: compactState() });
        break;
      }
      default:
        reply({ id, ok: false, error: `unknown op ${String(msg.op)}` });
    }
  } catch (err) {
    reply({ id, ok: false, error: err instanceof Error ? err.message : String(err) });
  }
});

rl.on('close', () => process.exit(0));
reply({ ready: true, pid: process.pid });
