import { type ReactNode } from "react";

export function Panel({ title, right, children, className = "" }: {
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel p-4 ${className}`}>
      {(title || right) && (
        <header className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">{title}</h2>}
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, tone = "default" }: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "good" | "bad" | "accent";
}) {
  const color =
    tone === "good" ? "text-[var(--color-good)]" : tone === "bad" ? "text-[var(--color-bad)]" : tone === "accent" ? "text-[var(--color-accent)]" : "text-[var(--color-bright)]";
  return (
    <div className="rounded-lg border border-[var(--color-edge)] bg-[#0e1016] p-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">{label}</div>
      <div className={`mt-1 font-mono text-xl tabular-nums ${color}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-[var(--color-muted)]">{hint}</div>}
    </div>
  );
}

export function Bar({ value, max = 1, tone = "accent" }: { value: number; max?: number; tone?: "accent" | "good" | "bad" | "info" }) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100));
  const bg =
    tone === "good" ? "var(--color-good)" : tone === "bad" ? "var(--color-bad)" : tone === "info" ? "var(--color-info)" : "var(--color-accent)";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#1a1f2b]">
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: bg }} />
    </div>
  );
}

export function Badge({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "good" | "bad" | "accent" | "info" }) {
  const map: Record<string, string> = {
    muted: "text-[var(--color-muted)] border-[var(--color-edge)] bg-[#161a24]",
    good: "text-[var(--color-good)] border-[color-mix(in_oklab,var(--color-good)_40%,transparent)] bg-[color-mix(in_oklab,var(--color-good)_12%,transparent)]",
    bad: "text-[var(--color-bad)] border-[color-mix(in_oklab,var(--color-bad)_40%,transparent)] bg-[color-mix(in_oklab,var(--color-bad)_12%,transparent)]",
    accent: "text-[var(--color-accent)] border-[color-mix(in_oklab,var(--color-accent)_40%,transparent)] bg-[color-mix(in_oklab,var(--color-accent)_12%,transparent)]",
    info: "text-[var(--color-info)] border-[color-mix(in_oklab,var(--color-info)_40%,transparent)] bg-[color-mix(in_oklab,var(--color-info)_12%,transparent)]",
  };
  return <span className={`chip ${map[tone]}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-[var(--color-edge)] p-6 text-center text-[12px] text-[var(--color-muted)]">{children}</div>;
}

export function fmtBytes(n: number): string {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${units[i]}`;
}

export function fmtNum(n: number): string {
  return n.toLocaleString("en-US");
}
