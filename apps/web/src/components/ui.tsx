import type { ReactNode } from "react";
import { Icon } from "./Icon";

export const Tag = ({ tone = "mute", children }: { tone?: "ok" | "warn" | "bad" | "acc" | "mute" | "proposed"; children: ReactNode }) => <span className={`tag t-${tone}`}>{children}</span>;

export const Bar = ({ pct, color, width }: { pct: number; color: string; width?: number | string }) => (
  <div className="bar" style={{ width }}><div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }} /></div>
);

export const Kv = ({ k, v, mono = true }: { k: string; v: ReactNode; mono?: boolean }) => (
  <div className="row" style={{ justifyContent: "space-between", padding: "3px 0" }}>
    <span style={{ color: "var(--color-ink-2)", fontSize: 12 }}>{k}</span>
    <span className={mono ? "m" : ""} style={{ fontSize: 12 }}>{v}</span>
  </div>
);

export function ToolRail({ tools, active, onPick }: { tools: string[]; active: string; onPick: (t: string) => void }) {
  return (
    <div className="panel" style={{ position: "absolute", left: 12, top: 12, padding: 4, display: "flex", flexDirection: "column", gap: 2, zIndex: 5 }}>
      {tools.map((t) => (
        <button key={t} className={`tool ${t === active ? "on" : ""}`} title={t} onClick={() => onPick(t)}><Icon name={t} /></button>
      ))}
    </div>
  );
}

export function Chips({ items, left = 58 }: { items: { key: string; label: string; on: boolean; onToggle: () => void }[]; left?: number }) {
  return (
    <div style={{ position: "absolute", left, top: 12, display: "flex", gap: 6, zIndex: 5, flexWrap: "wrap", maxWidth: "calc(100% - 460px)" }}>
      {items.map((c) => (
        <button key={c.key} className={`chip ${c.on ? "on" : ""}`} onClick={c.onToggle}>{c.label}</button>
      ))}
    </div>
  );
}

export function Dock({ children, width = 372 }: { children: ReactNode; width?: number }) {
  return (
    <div className="panel" style={{ position: "absolute", right: 12, top: 12, bottom: 12, width, boxSizing: "border-box", display: "flex", flexDirection: "column", overflow: "hidden", zIndex: 5 }}>{children}</div>
  );
}

export function DockHeader({ eyebrow, title, tag, meta }: { eyebrow: string; title: ReactNode; tag?: ReactNode; meta?: ReactNode }) {
  return (
    <div style={{ padding: "14px 14px 10px" }}>
      <div className="lbl">{eyebrow}</div>
      <div className="row" style={{ justifyContent: "space-between", marginTop: 2 }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>{title}</div>
        {tag}
      </div>
      {meta && <div className="m" style={{ fontSize: 11, color: "var(--color-ink-2)", marginTop: 3 }}>{meta}</div>}
    </div>
  );
}

export function DockTabs({ tabs, active, onPick }: { tabs: string[]; active: string; onPick: (t: string) => void }) {
  return (
    <div style={{ display: "flex", borderBottom: "1px solid var(--color-line)" }}>
      {tabs.map((t) => (
        <button key={t} onClick={() => onPick(t)} style={{ padding: "9px 12px", fontSize: 12, fontWeight: 600, color: t === active ? "var(--color-ink)" : "var(--color-ink-3)", borderBottom: `2px solid ${t === active ? "var(--color-acc)" : "transparent"}`, marginBottom: -1, background: "none", border: "none", borderBottomWidth: 2, borderBottomStyle: "solid", cursor: "pointer", fontFamily: "inherit" }}>{t}</button>
      ))}
    </div>
  );
}

export function DockFooter({ children }: { children: ReactNode }) {
  return <div style={{ padding: "10px 14px", borderTop: "1px solid var(--color-line)", display: "flex", gap: 8, alignItems: "center" }}>{children}</div>;
}

export function Strip({ children, height = 150, right = 396, open = true }: { children: ReactNode; height?: number; right?: number; open?: boolean }) {
  if (!open) return null;
  return (
    <div className="panel" style={{ position: "absolute", left: 58, right, bottom: 12, height, boxSizing: "border-box", overflow: "hidden", zIndex: 5 }}>{children}</div>
  );
}

export function Hud({ lines, bottom = 12 }: { lines: ReactNode[]; bottom?: number }) {
  return (
    <div className="m" style={{ position: "absolute", left: 58, bottom, fontSize: 11, color: "var(--color-ink-2)", lineHeight: 1.7, textShadow: "0 1px 2px #000", zIndex: 4, pointerEvents: "none" }}>
      {lines.map((l, i) => <div key={i}>{l}</div>)}
    </div>
  );
}

export function ViewControl({ view, onPick, bottom = 12, x = "50%" }: { view: string; onPick: (v: "plan" | "3d" | "photo") => void; bottom?: number; x?: string | number }) {
  const modes: ["plan" | "3d" | "photo", string][] = [["plan", "Plan"], ["3d", "3D"], ["photo", "Photo"]];
  return (
    <div className="panel" style={{ position: "absolute", left: x, transform: "translateX(-50%)", bottom, padding: 3, display: "flex", gap: 2, alignItems: "center", zIndex: 6 }}>
      {modes.map(([v, l]) => (
        <button key={v} onClick={() => onPick(v)} style={{ padding: "0 12px", height: 28, display: "inline-flex", alignItems: "center", fontSize: 12, fontWeight: 600, color: view === v ? "var(--color-ink)" : "var(--color-ink-2)", background: view === v ? "var(--color-acc-dim)" : "transparent", borderRadius: 4, border: "none", cursor: "pointer", fontFamily: "inherit" }}>{l}</button>
      ))}
      <span style={{ width: 1, height: 18, background: "var(--color-line-2)", margin: "0 6px" }} />
      <span style={{ color: "var(--color-ink-2)", display: "inline-flex", padding: "0 6px" }}><Icon name="compass" /></span>
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4, padding: "40px 16px", textAlign: "center" }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-ink-2)" }}>{title}</div>
      {hint && <div style={{ fontSize: 12, color: "var(--color-ink-3)" }}>{hint}</div>}
    </div>
  );
}

export const Slider = ({ label, value, min, max, step = 1, unit = "", onChange, format }: { label: string; value: number; min: number; max: number; step?: number; unit?: string; onChange: (v: number) => void; format?: (v: number) => string }) => (
  <div>
    <div className="row" style={{ justifyContent: "space-between" }}>
      <span style={{ fontSize: 11, color: "var(--color-ink-2)" }}>{label}</span>
      <span className="m" style={{ fontSize: 11 }}>{format ? format(value) : `${value}${unit}`}</span>
    </div>
    <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} style={{ width: "100%", accentColor: "var(--color-acc)", height: 18 }} />
  </div>
);
