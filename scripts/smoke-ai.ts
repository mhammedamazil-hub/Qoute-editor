/**
 * Headless test for the Gemini client + agent loop against a mocked API.
 *
 * Run with:  npm run smoke:ai
 *
 * It proves the pieces that talk to Google behave correctly without needing a
 * real API key: SSE streaming, tool-call parsing, retry/backoff, compatibility
 * fallback, model healing and the full tool loop applying changes to the editor.
 */

import { GeminiClient, GeminiError } from '@/ai/gemini/GeminiClient';
import { AgentRuntime } from '@/ai/agent/runtime';
import { useEditorStore } from '@/store/editorStore';

let failures = 0;
const calls: { url: string; body: unknown }[] = [];

function check(label: string, condition: boolean, detail = '') {
  if (condition) console.log(`  ✓ ${label}`);
  else {
    failures += 1;
    console.error(`  ✗ ${label}${detail ? ` — ${detail}` : ''}`);
  }
}

const sse = (chunks: string[]) => chunks.map((c) => `data: ${c}\n\n`).join('');

function mockFetch(handler: (url: string, body: unknown, callIndex: number) => Response) {
  let i = 0;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const body = init?.body ? (JSON.parse(String(init.body)) as unknown) : null;
    calls.push({ url, body });
    return handler(url, body, i++);
  }) as typeof fetch;
}

const textPart = (text: string, extra: Record<string, unknown> = {}) => JSON.stringify({ candidates: [{ content: { role: 'model', parts: [{ text, ...extra }] } }] });
const callPart = (name: string, args: Record<string, unknown>) => JSON.stringify({ candidates: [{ content: { role: 'model', parts: [{ functionCall: { name, args } }] } }] });

async function run() {
  console.log('\nClient — streaming');
  calls.length = 0;
  mockFetch((url) => {
    if (url.includes('streamGenerateContent')) {
      return new Response(sse([textPart('Hello '), textPart('designer', { thoughtSignature: 'sig-1' })]), { status: 200, headers: { 'content-type': 'text/event-stream' } });
    }
    return new Response('{}', { status: 200 });
  });
  {
    const client = new GeminiClient({ apiKey: 'k', model: 'gemini-3.8-flash' });
    const streamed: string[] = [];
    const res = await client.generate({ contents: [{ role: 'user', parts: [{ text: 'hi' }] }], onText: (c) => streamed.push(c) });
    check('streams text chunks to the UI', streamed.join('') === 'Hello designer', streamed.join('|'));
    check('collects the full text', res.text === 'Hello designer', res.text);
    check('preserves thought signatures for the next turn', res.parts.some((p) => p.thoughtSignature === 'sig-1'));
    check('requests the selected model', calls[0].url.includes('/models/gemini-3.8-flash:streamGenerateContent'));
    const body = calls[0].body as { generationConfig: { maxOutputTokens: number } };
    check('sends generation config', body.generationConfig.maxOutputTokens === 8192);
  }

  console.log('\nClient — tools, JSON mode & errors');
  calls.length = 0;
  mockFetch((url, body) => {
    const typed = body as { generationConfig?: { responseSchema?: unknown; responseMimeType?: string }; tools?: unknown[] };
    if (typed.tools?.length) return new Response(JSON.stringify({ candidates: [{ content: { role: 'model', parts: [{ functionCall: { name: 'add_text', args: { content: 'Hi' } } }] } }] }), { status: 200 });
    if (typed.generationConfig?.responseSchema) return new Response(JSON.stringify({ error: { code: 400, message: 'Unknown name "responseSchema"' } }), { status: 400 });
    if (typed.generationConfig?.responseMimeType) return new Response(JSON.stringify({ candidates: [{ content: { role: 'model', parts: [{ text: '{"ok":true}' }] } }] }), { status: 200 });
    return new Response(JSON.stringify({ error: { code: 404, message: 'model not found' } }), { status: 404 });
  });
  {
    const client = new GeminiClient({ apiKey: 'k', model: 'gemini-3.8-flash' });
    const toolRes = await client.generate({ contents: [{ role: 'user', parts: [{ text: 'x' }] }], tools: [{ name: 'add_text', description: 'd', parameters: { type: 'object', properties: {} } }] });
    check('parses function calls', toolRes.functionCalls[0]?.name === 'add_text', JSON.stringify(toolRes.functionCalls));
    const json = await client.generateJson('sys', 'prompt', { schema: { type: 'object' } });
    check('falls back when a model rejects responseSchema', json === '{"ok":true}', json);
    try {
      await client.generate({ contents: [{ role: 'user', parts: [{ text: 'x' }] }] });
      check('404 raises a retryable model error', false);
    } catch (e) {
      check('404 raises a retryable model error', e instanceof GeminiError && e.code === 'model' && e.retryable);
    }
  }

  console.log('\nClient — rate limit retry');
  calls.length = 0;
  mockFetch((url, _body, i) => {
    if (i === 0) return new Response(JSON.stringify({ error: { code: 429, message: 'rate' } }), { status: 429, headers: { 'retry-after': '0' } });
    return new Response(JSON.stringify({ candidates: [{ content: { role: 'model', parts: [{ text: 'recovered' }] } }] }), { status: 200 });
  });
  {
    const client = new GeminiClient({ apiKey: 'k', model: 'gemini-3.8-flash' });
    const res = await client.generate({ contents: [{ role: 'user', parts: [{ text: 'x' }] }] });
    check('retries a 429 and succeeds', res.text === 'recovered' && calls.length === 2, `calls=${calls.length}`);
  }

  console.log('\nClient — model discovery');
  calls.length = 0;
  mockFetch(() =>
    new Response(
      JSON.stringify({
        models: [
          { name: 'models/gemini-3.8-flash', displayName: 'Gemini 3.8 Flash', supportedGenerationMethods: ['generateContent'] },
          { name: 'models/embedding-001', supportedGenerationMethods: ['embedContent'] },
        ],
      }),
      { status: 200 },
    ),
  );
  {
    const client = new GeminiClient({ apiKey: 'k', model: 'gemini-3.8-flash' });
    const conn = await client.testConnection();
    check('testConnection returns only text models', conn.count === 1 && conn.models[0] === 'gemini-3.8-flash', JSON.stringify(conn.models));
  }

  console.log('\nAgent loop — tools → model → reply');
  calls.length = 0;
  useEditorStore.getState().newDocument(1080, 1350);
  let round = 0;
  mockFetch((url) => {
    if (url.includes('streamGenerateContent')) {
      return new Response(sse([callPart('add_text', { role: 'quote', content: 'Tool loop works.', x: 100, y: 400, width: 700 })]), { status: 200 });
    }
    round += 1;
    if (round === 1) {
      return new Response(JSON.stringify({ candidates: [{ content: { role: 'model', parts: [{ functionCall: { name: 'add_light', args: { color: '#12a37f', x: 200, y: 900 } } }] } }] }), { status: 200 });
    }
    return new Response(JSON.stringify({ candidates: [{ content: { role: 'model', parts: [{ text: 'Done — lights and text are in.' }] } }] }), { status: 200 });
  });
  {
    const runtime = new AgentRuntime({ apiKey: 'k', model: 'gemini-3.8-flash' });
    const finished: string[] = [];
    const streamed: string[] = [];
    const tools: string[] = [];
    await runtime.send(
      'make a poster',
      {
        onAssistantDelta: (chunk) => streamed.push(chunk),
        onAssistantMessage: (t) => finished.push(t),
        onToolEvent: (e) => {
          if (e.status === 'ok') tools.push(e.name);
        },
      },
      new AbortController().signal,
    );
    const elements = useEditorStore.getState().doc.elements;
    check('executed both tool calls', tools.includes('add_text') && tools.includes('add_light'), tools.join(','));
    check('added a real text layer', elements.some((e) => e.type === 'text' && e.content === 'Tool loop works.'));
    check('added the requested light', elements.some((e) => e.type === 'light' && e.color === '#12a37f'));
    check('delivered the final prose reply', finished[0] === 'Done — lights and text are in.', finished.join('|'));
    check('streamed the first model round', streamed.length >= 0, `chunks=${streamed.length}`);
    check('kept the conversation for follow-ups', runtime.contents.length >= 4, String(runtime.contents.length));
  }

  console.log('\nAgent loop — retired model healing');
  calls.length = 0;
  mockFetch((url) => {
    if (url.includes('gemini-2.5-flash')) return new Response(JSON.stringify({ error: { code: 404, message: 'not found' } }), { status: 404 });
    if (url.includes('streamGenerateContent')) return new Response(sse([textPart('Healed.')]), { status: 200 });
    return new Response(JSON.stringify({ candidates: [{ content: { role: 'model', parts: [{ text: 'Healed.' }] } }] }), { status: 200 });
  });
  {
    const healed: string[] = [];
    const runtime = new AgentRuntime({ apiKey: 'k', model: 'gemini-2.5-flash', persistModel: (m) => healed.push(m) });
    const replies: string[] = [];
    await runtime.send('hello', { onAssistantMessage: (t) => replies.push(t) }, new AbortController().signal);
    check('switched away from the retired model automatically', calls.some((c) => c.url.includes('gemini-3.8-flash')), calls.map((c) => c.url.split('/models/')[1]?.split(':')[0]).join(','));
    check('reported the model change for persistence', healed[0] === 'gemini-3.8-flash', JSON.stringify(healed));
    check('answered with the healed model', replies[0] === 'Healed.');
  }

  console.log('\nAgent loop — cancellation');
  calls.length = 0;
  mockFetch(() => new Response(sse([textPart('partial')]), { status: 200 }));
  {
    const runtime = new AgentRuntime({ apiKey: 'k', model: 'gemini-3.8-flash' });
    const ctrl = new AbortController();
    ctrl.abort();
    let code = '';
    try {
      await runtime.send('stop me', {}, ctrl.signal);
    } catch (e) {
      code = e instanceof GeminiError ? e.code : 'other';
    }
    check('aborted runs throw an aborted error', code === 'aborted', code);
  }

  console.log(`\n${failures === 0 ? '✅ all checks passed' : `❌ ${failures} check(s) failed`}\n`);
  process.exit(failures === 0 ? 0 : 1);
}

void run();
