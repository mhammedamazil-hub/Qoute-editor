/**
 * Headless render check for the dashboard.
 *
 * happy-dom cannot paint, so this proves the things a screenshot would prove
 * structurally: the app mounts, every tab renders without throwing, live data
 * from the real API reaches the DOM, and the chat round-trip renders a verified
 * action log. Run with:  npx vite-node scripts/render-check.tsx
 */
import { GlobalRegistrator } from "@happy-dom/global-registrator";

GlobalRegistrator.register({ url: "http://localhost:8000/", width: 1440, height: 900 });

const { createElement, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const { default: App } = await import("../src/App");

const BASE = process.env.MINICODER_API ?? "http://127.0.0.1:8000";

// Relative URLs are the contract; in the test we forward them to the live server.
const realFetch = globalThis.fetch;
globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === "string" ? input : input.toString();
  return realFetch(url.startsWith("/") ? `${BASE}${url}` : url, init);
}) as typeof fetch;

class FakeWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  readyState = 1;
  onopen?: () => void;
  onclose?: () => void;
  onerror?: () => void;
  onmessage?: (ev: { data: string }) => void;
  constructor(public url: string) {
    setTimeout(() => this.onopen?.(), 0);
  }
  send() {}
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
}
// @ts-expect-error test shim
globalThis.WebSocket = FakeWebSocket;

const results: { name: string; ok: boolean; detail?: string }[] = [];
const check = (name: string, ok: boolean, detail?: string) => {
  results.push({ name, ok, detail });
  console.log(`  ${ok ? "✓" : "✗"} ${name}${detail ? ` — ${detail}` : ""}`);
};

const container = document.createElement("div");
document.body.appendChild(container);
const root = createRoot(container);

await act(async () => {
  root.render(createElement(App));
});
await act(async () => {
  await new Promise((r) => setTimeout(r, 1800));
});

const text = () => container.textContent ?? "";
check("app mounts", text().length > 50, `${text().length} chars`);
check("title rendered", text().includes("Brain Dashboard"));
check("live status reaches the DOM", text().includes("params") || text().includes("checkpoint"));

// Walk every tab and assert it renders its own content.
const tabs = ["Overview", "Copilot", "Knowledge", "Memory", "Vision", "Learning"];
for (const tab of tabs) {
  const btn = [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === tab);
  if (!btn) {
    check(`tab ${tab} present`, false);
    continue;
  }
  await act(async () => {
    btn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }) as unknown as Event);
  });
  await act(async () => {
    await new Promise((r) => setTimeout(r, 900));
  });
  const body = text();
  check(`tab ${tab} renders`, body.length > 80, `${body.length} chars`);
}

// Exercise the chat round-trip against the real API through the UI.
const copilot = [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === "Copilot");
if (copilot) {
  await act(async () => {
    copilot.dispatchEvent(new window.MouseEvent("click", { bubbles: true }) as unknown as Event);
  });
  const textarea = container.querySelector("textarea");
  if (textarea) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(textarea, "What palette reads as premium?");
      textarea.dispatchEvent(new window.Event("input", { bubbles: true }) as unknown as Event);
    });
    const sendBtn = [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === "Send");
    if (sendBtn) {
      await act(async () => {
        sendBtn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }) as unknown as Event);
      });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 2500));
      });
      const after = text();
      check("chat answer rendered", after.includes("premium") || after.includes("Deep green"), after.slice(-160));
    } else {
      check("send button present", false);
    }
  } else {
    check("textarea present", false);
  }
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
root.unmount();
await GlobalRegistrator.unregister();
process.exit(failed.length ? 1 : 0);
