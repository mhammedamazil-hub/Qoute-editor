/**
 * Agent runtime: drives the Gemini function-calling loop against the editor.
 *
 *  user message → model (streaming text + tool calls) → we execute tools on the
 *  real stores → tool results go back → repeat until the model answers in prose.
 *
 * Also handles: automatic model healing (retired model → newest available),
 * cancellation, step limits and per-call status reporting for the UI.
 */

import { GeminiClient, GeminiError, type GeminiContent, type GeminiErrorCode, type GeminiGenerateResult } from '@/ai/gemini/GeminiClient';
import { FALLBACK_MODELS } from '@/ai/gemini/models';
import { AGENT_SYSTEM_PROMPT } from './prompt';
import { TOOL_DECLARATIONS, executeTool } from './tools';

export interface AgentToolEvent {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: 'running' | 'ok' | 'error';
  summary?: string;
  detail?: unknown;
  at: number;
}

export interface AgentCallbacks {
  onAssistantDelta?: (chunk: string) => void;
  onAssistantMessage?: (text: string) => void;
  onToolEvent?: (event: AgentToolEvent) => void;
  onStatus?: (status: string) => void;
  onModelChange?: (model: string, reason: string) => void;
  onError?: (message: string, code: GeminiErrorCode) => void;
}

const MAX_TOOL_ROUNDS = 12;
const MAX_TOOL_CALLS = 40;

/** Friendly labels for the activity feed. */
export const TOOL_LABELS: Record<string, string> = {
  get_app_state: 'Inspecting the design',
  new_project: 'Starting a new project',
  set_canvas_size: 'Resizing the artboard',
  set_background: 'Setting the background',
  apply_palette: 'Applying a palette',
  list_templates: 'Listing templates',
  apply_template: 'Loading a template',
  add_text: 'Adding text',
  add_quote_mark: 'Adding a quote mark',
  add_shape: 'Adding geometry',
  add_light: 'Adding light',
  add_gradient_layer: 'Adding a gradient',
  add_particles: 'Adding particles',
  add_decoration: 'Adding a decoration',
  update_elements: 'Adjusting layers',
  set_text_content: 'Rewriting text',
  set_typography: 'Setting typography',
  set_layer_style: 'Styling layers',
  translate_elements: 'Moving layers',
  resize_elements: 'Resizing layers',
  duplicate_elements: 'Duplicating layers',
  delete_elements: 'Deleting layers',
  select_elements: 'Selecting layers',
  reorder_elements: 'Reordering layers',
  group_elements: 'Grouping layers',
  ungroup_elements: 'Ungrouping layers',
  align_elements: 'Aligning layers',
  distribute_elements: 'Distributing layers',
  undo: 'Undoing',
  redo: 'Redoing',
  zoom: 'Adjusting the view',
  set_preview_mode: 'Toggling preview',
  open_panel: 'Opening a panel',
  set_ui_preference: 'Updating preferences',
  save_project: 'Saving the project',
  export_image: 'Exporting the artwork',
  generate_design: 'Composing a full design',
};

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, ' ');
}

let toolSeq = 0;

export interface AgentRuntimeOptions {
  apiKey: string;
  model: string;
  /** Called when the runtime changed the persisted model (retired model healing). */
  persistModel?: (model: string) => void;
}

export class AgentRuntime {
  private client: GeminiClient;
  contents: GeminiContent[] = [];

  constructor(private opts: AgentRuntimeOptions) {
    this.client = new GeminiClient({ apiKey: opts.apiKey, model: opts.model, timeoutMs: 120_000 });
  }

  get model() {
    return this.client.modelId;
  }

  reset() {
    this.contents = [];
  }

  /** Number of user/assistant turns kept in context (older turns are dropped). */
  private trim() {
    const MAX_TURNS = 24;
    if (this.contents.length > MAX_TURNS) {
      this.contents = this.contents.slice(this.contents.length - MAX_TURNS);
    }
  }

  /** One model round, with automatic model healing + one schema/compat retry. */
  private async modelRound(
    onText: ((chunk: string) => void) | undefined,
    cb: AgentCallbacks,
    signal: AbortSignal,
  ): Promise<GeminiGenerateResult> {
    const tried: string[] = [this.client.modelId];
    const chain = [this.client.modelId, ...FALLBACK_MODELS.filter((m) => m !== this.client.modelId)];
    let lastError: unknown;

    for (const model of chain) {
      if (signal.aborted) throw new GeminiError('Cancelled.', 'aborted');
      this.client.setModel(model);
      try {
        const res = await this.client.generate({
          systemInstruction: AGENT_SYSTEM_PROMPT,
          contents: this.contents,
          tools: TOOL_DECLARATIONS,
          temperature: 0.65,
          maxOutputTokens: 8192,
          onText,
          signal,
        });
        if (model !== tried[0]) {
          this.opts.persistModel?.(model);
          cb.onModelChange?.(model, `${tried[0]} is unavailable on this key — switched automatically.`);
        }
        return res;
      } catch (e) {
        lastError = e;
        const healable = e instanceof GeminiError && (e.code === 'model' || (model !== tried[0] && e.code === 'quota'));
        if (e instanceof GeminiError && e.code === 'aborted') throw e;
        if (!healable) {
          // Non-model errors: retry once with the next Flash if it looks transient, else fail.
          if (e instanceof GeminiError && (e.code === 'rate-limit' || e.code === 'quota') && chain.indexOf(model) < 2) continue;
          throw e;
        }
      }
    }
    throw lastError instanceof Error ? lastError : new GeminiError('No usable Gemini model responded.', 'model');
  }

  /** Sends a user message and runs the full tool loop. */
  async send(userText: string, cb: AgentCallbacks, signal: AbortSignal): Promise<void> {
    this.contents.push({ role: 'user', parts: [{ text: userText }] });
    this.trim();
    let toolCalls = 0;

    for (let round = 0; round < MAX_TOOL_ROUNDS; round += 1) {
      if (signal.aborted) throw new GeminiError('Cancelled.', 'aborted');
      cb.onStatus?.(round === 0 ? 'Thinking…' : 'Working on the canvas…');

      const result = await this.modelRound(round === 0 ? cb.onAssistantDelta : undefined, cb, signal);

      // Keep raw parts (with thought signatures) so follow-up turns stay valid.
      this.contents.push({ role: 'model', parts: result.parts });

      if (!result.functionCalls.length) {
        const text = result.text.trim();
        if (text) cb.onAssistantMessage?.(text);
        if (result.warnings.length) cb.onStatus?.(result.warnings[0]);
        return;
      }

      const responseParts: GeminiContent['parts'] = [];
      for (const call of result.functionCalls) {
        if (toolCalls >= MAX_TOOL_CALLS) {
          responseParts.push({ functionResponse: { name: call.name, response: { ok: false, error: 'Tool budget reached for this turn.' } } });
          continue;
        }
        toolCalls += 1;
        const id = `tool-${++toolSeq}`;
        const event: AgentToolEvent = { id, name: call.name, args: call.args, status: 'running', at: Date.now() };
        cb.onToolEvent?.(event);
        try {
          const outcome = await executeTool(call.name, call.args ?? {}, {
            apiKey: this.opts.apiKey,
            model: this.client.modelId,
            signal,
            onStatus: (s) => cb.onStatus?.(s),
          });
          cb.onToolEvent?.({
            ...event,
            status: outcome.ok ? 'ok' : 'error',
            summary: outcome.summary,
            detail: outcome.data,
          });
          responseParts.push({ functionResponse: { name: call.name, response: { ok: outcome.ok, summary: outcome.summary, ...(outcome.data ?? {}) } } });
        } catch (e) {
          const message = e instanceof Error ? e.message : 'Tool failed.';
          cb.onToolEvent?.({ ...event, status: 'error', summary: message });
          responseParts.push({ functionResponse: { name: call.name, response: { ok: false, error: message } } });
        }
      }

      this.contents.push({ role: 'user', parts: responseParts });
      this.trim();
    }

    cb.onAssistantMessage?.('I made a lot of changes — take a look and tell me what to refine next.');
  }
}
