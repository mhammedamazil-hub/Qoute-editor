import { create } from 'zustand';
import { AgentRuntime, type AgentToolEvent } from '@/ai/agent/runtime';
import { useEditorStore } from './editorStore';
import { useSettingsStore } from './settingsStore';
import { toast } from './uiStore';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  tools: AgentToolEvent[];
  status: 'pending' | 'done' | 'error' | 'stopped';
  error?: string;
  createdAt: number;
}

interface AIState {
  messages: ChatMessage[];
  busy: boolean;
  status: string;
  clear: () => void;
  send: (text: string) => Promise<void>;
  stop: () => void;
  retry: () => Promise<void>;
  dismissMessage: (id: string) => void;
}

let runtime: AgentRuntime | null = null;
let controller: AbortController | null = null;
let seq = 0;

function nextId() {
  seq += 1;
  return `msg-${Date.now().toString(36)}-${seq}`;
}

/** Fresh runtime whenever the key or model changes. */
function getRuntime(): AgentRuntime {
  const { geminiKey, geminiModel } = useSettingsStore.getState();
  if (!runtime || runtime.model !== geminiModel) {
    runtime = new AgentRuntime({
      apiKey: geminiKey,
      model: geminiModel,
      persistModel: (model) => {
        useSettingsStore.getState().update({ geminiModel: model });
        toast('Switched Gemini model', 'ai', `Now using ${model} (the previous model is not available for this key).`);
      },
    });
  }
  return runtime;
}

export function resetRuntime() {
  runtime = null;
}

export const useAIStore = create<AIState>()((set, get) => ({
  messages: [],
  busy: false,
  status: '',

  clear: () => {
    runtime?.reset();
    set({ messages: [], status: '', busy: false });
  },

  stop: () => {
    controller?.abort();
    set((s) => ({
      busy: false,
      status: 'Stopped',
      messages: s.messages.map((m) => (m.status === 'pending' ? { ...m, status: 'stopped' as const } : m)),
    }));
  },

  dismissMessage: (id) => set((s) => ({ messages: s.messages.filter((m) => m.id !== id) })),

  send: async (text) => {
    const trimmed = text.trim();
    if (!trimmed || get().busy) return;
    const settings = useSettingsStore.getState();
    if (!settings.geminiKey) {
      set((s) => ({
        messages: [
          ...s.messages,
          { id: nextId(), role: 'user', text: trimmed, tools: [], status: 'done', createdAt: Date.now() },
          {
            id: nextId(),
            role: 'assistant',
            text: '',
            tools: [],
            status: 'error',
            error: 'Add your Gemini API key in Settings to use the copilot. Your key stays in this browser and is sent only to Google.',
            createdAt: Date.now(),
          },
        ],
      }));
      return;
    }

    const userMsg: ChatMessage = { id: nextId(), role: 'user', text: trimmed, tools: [], status: 'done', createdAt: Date.now() };
    const assistantId = nextId();
    const assistantMsg: ChatMessage = { id: assistantId, role: 'assistant', text: '', tools: [], status: 'pending', createdAt: Date.now() };
    set((s) => ({ messages: [...s.messages, userMsg, assistantMsg], busy: true, status: 'Thinking…' }));

    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      set((s) => ({ messages: s.messages.map((m) => (m.id === assistantId ? fn(m) : m)) }));

    controller = new AbortController();
    try {
      await getRuntime().send(
        trimmed,
        {
          onAssistantDelta: (chunk) => patch((m) => ({ ...m, text: m.text + chunk })),
          onAssistantMessage: (full) => patch((m) => ({ ...m, text: full || m.text, status: 'done' })),
          onToolEvent: (event) =>
            patch((m) => {
              const existing = m.tools.findIndex((t) => t.id === event.id);
              const tools = existing >= 0 ? m.tools.map((t, i) => (i === existing ? event : t)) : [...m.tools, event];
              return { ...m, tools };
            }),
          onStatus: (status) => set({ status }),
          onModelChange: (model) => {
            useSettingsStore.getState().update({ geminiModel: model });
          },
          onError: (message, code) => {
            useSettingsStore.getState().setAIStatus(code === 'invalid-key' ? 'invalid' : 'failed');
            patch((m) => ({ ...m, status: 'error', error: message }));
          },
        },
        controller.signal,
      );
      useSettingsStore.getState().setAIStatus('connected');
      patch((m) => ({ ...m, status: m.status === 'error' ? 'error' : m.status === 'stopped' ? 'stopped' : 'done' }));
    } catch (e) {
      const message = e instanceof Error ? e.message : 'The assistant failed.';
      const code = (e as { code?: string }).code;
      const stopped = code === 'aborted';
      if (stopped) {
        patch((m) => ({ ...m, status: 'stopped' }));
      } else {
        if (code === 'invalid-key') useSettingsStore.getState().setAIStatus('invalid');
        else if (code === 'network' || code === 'timeout') useSettingsStore.getState().setAIStatus('failed');
        patch((m) => ({ ...m, status: 'error', error: message }));
      }
    } finally {
      controller = null;
      set({ busy: false, status: '' });
    }
  },

  retry: async () => {
    const messages = get().messages;
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (!lastUser) return;
    set((s) => ({ messages: s.messages.filter((m) => !(m.role === 'assistant' && m.id === s.messages[s.messages.length - 1]?.id && m.status === 'error')) }));
    await get().send(lastUser.text);
  },
}));

/** Context-aware starter prompts shown above the composer. */
export function copilotSuggestions(): string[] {
  const ed = useEditorStore.getState();
  const count = ed.doc.elements.length;
  const hasText = ed.doc.elements.some((e) => e.type === 'text');
  if (!count) {
    return [
      'Create a cinematic poster about discipline with a dark background and warm amber light',
      'Design an elegant cream poster: “Simplicity is the ultimate sophistication.”',
      'Make a bold neon quote poster for a 9:16 story',
    ];
  }
  const out: string[] = [];
  if (!hasText) out.push('Add the main quote text and an author line');
  out.push('Make it look more premium');
  out.push('Switch to the Emerald Luxury palette');
  out.push('Increase contrast and add a bit more negative space');
  if (count > 6) out.push('Simplify — remove the busiest decorations');
  out.push('Export at 2× as PNG');
  return out.slice(0, 4);
}
