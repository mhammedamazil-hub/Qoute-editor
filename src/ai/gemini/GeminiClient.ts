/**
 * Browser-side Gemini client (no server, no bundled key).
 *
 * Supports everything the assistant needs:
 *  - live model discovery + key validation
 *  - plain JSON generation (structured design specs)
 *  - streaming generation (SSE) so replies appear token-by-token
 *  - function/tool calling (the "AI can control the whole app" layer)
 *  - robust error mapping, retries with backoff, abort support, and a
 *    compatibility fallback for model families that reject newer request fields.
 */

const BASE = 'https://generativelanguage.googleapis.com/v1beta';

export type GeminiErrorCode =
  | 'invalid-key'
  | 'rate-limit'
  | 'quota'
  | 'network'
  | 'timeout'
  | 'model'
  | 'malformed'
  | 'blocked'
  | 'aborted'
  | 'unsupported'
  | 'unknown';

export class GeminiError extends Error {
  constructor(
    message: string,
    public code: GeminiErrorCode,
    /** True when a different model might succeed (used for auto-fallback). */
    public retryable = false,
  ) {
    super(message);
    this.name = 'GeminiError';
  }
}

/* ------------------------------------------------------------------ *
 * Types
 * ------------------------------------------------------------------ */

export interface GeminiPart {
  text?: string;
  functionCall?: { name: string; args?: Record<string, unknown> };
  functionResponse?: { name: string; response: Record<string, unknown> };
  inlineData?: { mimeType: string; data: string };
  /** Gemini 3 returns these on model parts; they must be echoed back verbatim. */
  thoughtSignature?: string;
  thought?: boolean;
  [key: string]: unknown;
}

export interface GeminiContent {
  role: 'user' | 'model';
  parts: GeminiPart[];
}

export interface GeminiFunctionDeclaration {
  name: string;
  description: string;
  parameters: {
    type: 'object';
    properties: Record<string, unknown>;
    required?: string[];
  };
}

export interface GeminiGenerateOptions {
  systemInstruction?: string;
  contents: GeminiContent[];
  tools?: GeminiFunctionDeclaration[];
  temperature?: number;
  topP?: number;
  maxOutputTokens?: number;
  /** Force JSON output (`responseMimeType`). */
  jsonMode?: boolean;
  /** Optional structured-output schema (OpenAPI subset). */
  responseSchema?: Record<string, unknown>;
  /** Called for every streamed text chunk. */
  onText?: (chunk: string) => void;
  signal?: AbortSignal;
  /** Low-latency hint passed as `thinkingLevel` where supported. */
  thinkingLevel?: 'low' | 'high';
}

export interface GeminiGenerateResult {
  /** Concatenated text output ('' when the model only requested tools). */
  text: string;
  /** Raw model parts, including thought signatures, so they can be echoed back. */
  parts: GeminiPart[];
  functionCalls: { name: string; args: Record<string, unknown> }[];
  finishReason?: string;
  /** Warnings from the compatibility fallback (e.g. dropped schema). */
  warnings: string[];
}

export interface GeminiModelListItem {
  id: string;
  label: string;
  description?: string;
  inputTokenLimit?: number;
  supportsGenerateContent: boolean;
}

export interface GeminiClientOptions {
  apiKey: string;
  model: string;
  timeoutMs?: number;
}

interface RawResponse {
  candidates?: { content?: { parts?: GeminiPart[]; role?: string }; finishReason?: string }[];
  promptFeedback?: { blockReason?: string; blockReasonMessage?: string };
  error?: { code?: number; message?: string; status?: string };
  models?: {
    name?: string;
    displayName?: string;
    description?: string;
    inputTokenLimit?: number;
    supportedGenerationMethods?: string[];
  }[];
  nextPageToken?: string;
  usageMetadata?: { promptTokenCount?: number; candidatesTokenCount?: number; totalTokenCount?: number };
}

/* ------------------------------------------------------------------ *
 * Helpers
 * ------------------------------------------------------------------ */

function mapHttpError(status: number, body: RawResponse | null): GeminiError {
  const msg = body?.error?.message ?? '';
  const statusName = body?.error?.status ?? '';
  if (status === 400 && /api[ _-]?key/i.test(msg)) return new GeminiError('The Gemini API key looks invalid.', 'invalid-key');
  if (status === 401 || status === 403) {
    return new GeminiError('Gemini rejected the key (invalid, expired, or missing permission). Check the key in Google AI Studio.', 'invalid-key');
  }
  if (status === 404) {
    return new GeminiError('That Gemini model is not available for this key — it may be retired.', 'model', true);
  }
  if (status === 429) {
    return /quota|billing|exceeded/i.test(msg)
      ? new GeminiError('Gemini quota exceeded for this key.', 'quota', true)
      : new GeminiError('Gemini rate limit reached — retrying shortly.', 'rate-limit', true);
  }
  if (status === 400 && /blocked|safety|prohibited/i.test(msg)) {
    return new GeminiError('Gemini blocked this request. Try rephrasing.', 'blocked');
  }
  if (status === 400 && /unknown name|invalid json payload|unsupported|not supported/i.test(msg)) {
    return new GeminiError(msg || 'This model rejected part of the request.', 'unsupported');
  }
  if (status >= 500) return new GeminiError('Gemini service error — retrying.', 'network', true);
  if (status === 499) return new GeminiError('Request cancelled.', 'aborted');
  return new GeminiError(msg || `Gemini request failed (${status}${statusName ? ` ${statusName}` : ''}).`, 'unknown', status >= 500);
}

function isAbort(e: unknown): boolean {
  return (e as { name?: string } | null)?.name === 'AbortError';
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new GeminiError('Cancelled.', 'aborted'));
    }, { once: true });
  });
}

/** Extracts JSON from a model reply that may be fenced or padded with prose. */
export function extractJson(text: string): unknown {
  const trimmed = text.trim().replace(/^```(?:json)?/i, '').replace(/```\s*$/, '').trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const start = trimmed.indexOf('{');
    const end = trimmed.lastIndexOf('}');
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(trimmed.slice(start, end + 1));
      } catch {
        /* fallthrough */
      }
    }
    throw new GeminiError('The model returned malformed JSON. Please try again.', 'malformed');
  }
}

/* ------------------------------------------------------------------ *
 * Client
 * ------------------------------------------------------------------ */

export class GeminiClient {
  private apiKey: string;
  private model: string;
  private timeoutMs: number;
  /** Set after a 400 caused by request fields the selected model doesn't know. */
  private compatMode = false;

  constructor(opts: GeminiClientOptions) {
    this.apiKey = opts.apiKey;
    this.model = opts.model;
    this.timeoutMs = opts.timeoutMs ?? 90_000;
  }

  get modelId() {
    return this.model;
  }

  setModel(model: string) {
    this.model = model;
  }

  private headers() {
    return { 'Content-Type': 'application/json', 'x-goog-api-key': this.apiKey };
  }

  /** Lists models that support text generation for this key. */
  async listModels(): Promise<GeminiModelListItem[]> {
    const out: GeminiModelListItem[] = [];
    let pageToken: string | undefined;
    for (let page = 0; page < 4; page += 1) {
      const url = new URL(`${BASE}/models`);
      url.searchParams.set('pageSize', '100');
      if (pageToken) url.searchParams.set('pageToken', pageToken);
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 20_000);
      try {
        const res = await fetch(url.toString(), { headers: this.headers(), signal: ctrl.signal });
        const body = (await res.json().catch(() => null)) as RawResponse | null;
        if (!res.ok) throw mapHttpError(res.status, body);
        for (const m of body?.models ?? []) {
          const id = (m.name ?? '').replace(/^models\//, '');
          if (!id) continue;
          out.push({
            id,
            label: m.displayName ?? id,
            description: m.description,
            inputTokenLimit: m.inputTokenLimit,
            supportsGenerateContent: (m.supportedGenerationMethods ?? []).includes('generateContent'),
          });
        }
        pageToken = body?.nextPageToken;
        if (!pageToken) break;
      } catch (e) {
        if (e instanceof GeminiError) throw e;
        if (isAbort(e)) throw new GeminiError('Connection to Gemini timed out.', 'timeout');
        throw new GeminiError('Could not reach Gemini. Check your network connection.', 'network');
      } finally {
        clearTimeout(t);
      }
    }
    return out;
  }

  /** Lightweight connectivity + key check with the models that are actually usable. */
  async testConnection(): Promise<{ ok: true; models: string[]; count: number }> {
    const models = await this.listModels();
    const usable = models.filter((m) => m.supportsGenerateContent).map((m) => m.id);
    if (!usable.length) throw new GeminiError('The key works but no text-generation models are available.', 'model', true);
    return { ok: true, models: usable, count: usable.length };
  }

  /** True when the given model id is listed for this key. */
  async modelExists(id: string, known?: string[]): Promise<boolean> {
    const list = known ?? (await this.listModels()).map((m) => m.id);
    return list.includes(id);
  }

  /* ---------------- core generation ---------------- */

  private buildBody(opts: GeminiGenerateOptions, streaming: boolean): Record<string, unknown> {
    const generationConfig: Record<string, unknown> = {};
    if (typeof opts.temperature === 'number') generationConfig.temperature = opts.temperature;
    if (typeof opts.topP === 'number') generationConfig.topP = opts.topP;
    generationConfig.maxOutputTokens = opts.maxOutputTokens ?? 8192;
    if (opts.jsonMode) generationConfig.responseMimeType = 'application/json';
    if (opts.responseSchema && !this.compatMode) generationConfig.responseSchema = opts.responseSchema;
    if (opts.thinkingLevel && !this.compatMode) generationConfig.thinkingConfig = { thinkingLevel: opts.thinkingLevel };

    const body: Record<string, unknown> = {
      contents: opts.contents,
      generationConfig,
    };
    if (opts.systemInstruction) body.systemInstruction = { parts: [{ text: opts.systemInstruction }] };
    if (opts.tools?.length) {
      body.tools = [{ functionDeclarations: opts.tools }];
      body.toolConfig = { functionCallingConfig: { mode: 'AUTO' } };
    }
    if (streaming) body.alt = 'sse';
    return body;
  }

  private async request(
    method: 'generate' | 'stream',
    opts: GeminiGenerateOptions,
    attempt = 0,
  ): Promise<GeminiGenerateResult> {
    const url = `${BASE}/models/${encodeURIComponent(this.model)}:${method === 'stream' ? 'streamGenerateContent' : 'generateContent'}${method === 'stream' ? '?alt=sse' : ''}`;
    const body = this.buildBody(opts, method === 'stream');

    const ctrl = new AbortController();
    const onOuterAbort = () => ctrl.abort();
    opts.signal?.addEventListener('abort', onOuterAbort, { once: true });
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: this.headers(),
        signal: ctrl.signal,
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errBody = (await res.json().catch(() => null)) as RawResponse | null;
        const err = mapHttpError(res.status, errBody);
        // Compatibility fallback: some models reject schema/thinking fields.
        if (err.code === 'unsupported' && !this.compatMode) {
          this.compatMode = true;
          return this.request(method, opts, attempt);
        }
        // Automatic retry with backoff for rate limits / transient errors.
        if (err.retryable && attempt < 3) {
          const retryAfter = Number(res.headers.get('retry-after'));
          const wait = Number.isFinite(retryAfter) && retryAfter > 0 ? Math.min(retryAfter * 1000, 12_000) : 700 * 2 ** attempt + Math.random() * 250;
          await sleep(wait, opts.signal);
          return this.request(method, opts, attempt + 1);
        }
        throw err;
      }

      return method === 'stream' ? await this.readStream(res, opts) : await this.readJson(res);
    } catch (e) {
      if (e instanceof GeminiError) {
        if (e.code === 'network' && attempt < 2 && !opts.signal?.aborted) {
          await sleep(500 * 2 ** attempt, opts.signal);
          return this.request(method, opts, attempt + 1);
        }
        throw e;
      }
      if (isAbort(e)) {
        if (opts.signal?.aborted) throw new GeminiError('Cancelled.', 'aborted');
        throw new GeminiError('Gemini took too long to respond.', 'timeout', true);
      }
      throw new GeminiError('Could not reach Gemini. Check your network connection.', 'network', true);
    } finally {
      clearTimeout(timer);
      opts.signal?.removeEventListener('abort', onOuterAbort);
    }
  }

  private async readJson(res: Response): Promise<GeminiGenerateResult> {
    const body = (await res.json().catch(() => null)) as RawResponse | null;
    if (body?.promptFeedback?.blockReason) {
      throw new GeminiError(body.promptFeedback.blockReasonMessage || 'Gemini blocked this request. Try rephrasing.', 'blocked');
    }
    const candidate = body?.candidates?.[0];
    const parts = candidate?.content?.parts ?? [];
    return this.collect(parts, candidate?.finishReason);
  }

  private async readStream(res: Response, opts: GeminiGenerateOptions): Promise<GeminiGenerateResult> {
    const reader = res.body?.getReader();
    if (!reader) throw new GeminiError('Streaming is not supported in this browser.', 'unsupported');
    const decoder = new TextDecoder();
    const parts: GeminiPart[] = [];
    let finishReason: string | undefined;
    let buffer = '';
    const warnings: string[] = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const raw of lines) {
        const line = raw.trim();
        if (!line || !line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === '[DONE]') continue;
        let chunk: RawResponse;
        try {
          chunk = JSON.parse(payload) as RawResponse;
        } catch {
          continue;
        }
        if (chunk.promptFeedback?.blockReason) {
          throw new GeminiError(chunk.promptFeedback.blockReasonMessage || 'Gemini blocked this request. Try rephrasing.', 'blocked');
        }
        const cand = chunk.candidates?.[0];
        if (cand?.finishReason) finishReason = cand.finishReason;
        for (const part of cand?.content?.parts ?? []) {
          // Merge consecutive text parts into one so the transcript stays tidy.
          const last = parts[parts.length - 1];
          if (part.text !== undefined && last?.text !== undefined && part.functionCall === undefined) {
            if (part.thought !== true) opts.onText?.(part.text);
            last.text = (last.text ?? '') + part.text;
            if (part.thoughtSignature) last.thoughtSignature = part.thoughtSignature;
            continue;
          }
          parts.push({ ...part });
          if (part.text && !part.thought) opts.onText?.(part.text);
        }
      }
    }

    if (!parts.length) throw new GeminiError('Gemini returned an empty response.', 'malformed');
    return this.collect(parts, finishReason, warnings);
  }

  private collect(rawParts: GeminiPart[], finishReason?: string, warnings: string[] = []): GeminiGenerateResult {
    const text = rawParts
      .filter((p) => p.thought !== true)
      .map((p) => p.text ?? '')
      .join('');
    const functionCalls = rawParts
      .filter((p) => !!p.functionCall?.name)
      .map((p) => ({ name: p.functionCall!.name, args: (p.functionCall!.args ?? {}) as Record<string, unknown> }));
    if (!text.trim() && !functionCalls.length) {
      const why = finishReason && finishReason !== 'STOP' ? ` (finish reason: ${finishReason})` : '';
      throw new GeminiError(`Gemini returned an empty response${why}.`, finishReason === 'SAFETY' ? 'blocked' : 'malformed');
    }
    if (finishReason === 'MAX_TOKENS' && !functionCalls.length) {
      warnings.push('The reply hit the output limit and may be cut short.');
    }
    return { text, parts: rawParts, functionCalls, finishReason, warnings };
  }

  /* ---------------- public helpers ---------------- */

  /** Structured / plain generation with tools + streaming support. */
  async generate(opts: GeminiGenerateOptions): Promise<GeminiGenerateResult> {
    return this.request(opts.onText ? 'stream' : 'generate', opts);
  }

  /** Convenience wrapper used by the design studio: returns raw JSON text. */
  async generateJson(
    systemInstruction: string,
    prompt: string,
    opts: { temperature?: number; schema?: Record<string, unknown> } = {},
  ): Promise<string> {
    const res = await this.generate({
      systemInstruction,
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      temperature: opts.temperature ?? 0.8,
      jsonMode: true,
      responseSchema: opts.schema,
    });
    return res.text;
  }
}
