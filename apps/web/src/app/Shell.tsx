/* The workbench frame: top bar with the pipeline stepper, and a full-bleed
 * viewport the stage fills. docs/FRONTEND-DESIGN.md section 1. */

import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useMe } from "../api/queries";
import { Icon } from "../components/Icon";

export const STAGES = ["Capture", "Process", "Model", "Plan", "Report"] as const;
export type Stage = (typeof STAGES)[number];

export interface StageLink { stage: Stage; to?: string; state: "done" | "current" | "locked" | "idle"; note?: string }

export function Shell({ crumb, stages, status, jobs, children }: { crumb: ReactNode; stages?: StageLink[]; status?: ReactNode; jobs?: ReactNode; children: ReactNode }) {
  const me = useMe();
  const nav = useNavigate();
  const initials = me.data?.name?.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase() ?? "?";
  return (
    <div style={{ width: "100%", height: "100%", position: "relative", overflow: "hidden" }}>
      <div style={{ height: 44, display: "flex", alignItems: "center", padding: "0 14px", gap: 14, borderBottom: "1px solid var(--color-line)", background: "var(--color-bg-deep)", boxSizing: "border-box" }}>
        <div className="row" style={{ gap: 8, width: 300, minWidth: 0 }}>
          <Link to="/" className="row" style={{ gap: 8, color: "inherit" }}>
            <span style={{ color: "var(--color-acc)", display: "inline-flex" }}><Icon name="target" size={18} /></span>
            <span style={{ fontWeight: 800, fontSize: 15, letterSpacing: "0.06em" }}>ADCP</span>
          </Link>
          <span style={{ color: "var(--color-ink-3)", fontSize: 12 }}>/</span>
          <span style={{ fontSize: 12, color: "var(--color-ink-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{crumb}</span>
          {status}
        </div>
        <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>{stages && <Stepper stages={stages} />}</div>
        <div className="row" style={{ gap: 10, width: 300, justifyContent: "flex-end" }}>
          {jobs && <span className="m" style={{ fontSize: 11, color: "var(--color-ink-2)", whiteSpace: "nowrap" }}>{jobs}</span>}
          <Link to="/jobs" className="chip" style={{ height: 26 }}>Jobs</Link>
          {me.data?.role === "admin" && <Link to="/admin" className="chip" style={{ height: 26 }}>Admin</Link>}
          <button title={`${me.data?.email ?? ""} · sign out`} onClick={async () => { await api.post("/api/auth/logout"); nav("/login"); }} style={{ width: 24, height: 24, borderRadius: "50%", background: "#2b3441", color: "var(--color-ink)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, border: "none", cursor: "pointer" }}>{initials}</button>
        </div>
      </div>
      <div style={{ position: "absolute", top: 44, left: 0, right: 0, bottom: 0, overflow: "hidden" }}>{children}</div>
    </div>
  );
}

function Stepper({ stages }: { stages: StageLink[] }) {
  return (
    <div style={{ display: "flex", alignItems: "center" }}>
      {stages.map((s, i) => {
        const dot = s.state === "current" ? { background: "var(--color-acc)", boxShadow: "0 0 0 3px var(--color-acc-dim)" } : s.state === "done" ? { background: "var(--color-ok)" } : { border: "1.5px solid var(--color-ink-3)", boxSizing: "border-box" as const };
        const color = s.state === "current" ? "var(--color-ink)" : s.state === "done" ? "var(--color-ink-2)" : "var(--color-ink-3)";
        const inner = (
          <div className="row" style={{ gap: 7, padding: "0 4px" }} title={s.note}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", display: "inline-block", ...dot }} />
            <span style={{ fontSize: 12, fontWeight: s.state === "current" ? 700 : 500, color, letterSpacing: "0.02em" }}>{s.stage}</span>
            {s.note && s.state === "locked" && <span className="tag t-mute" style={{ fontSize: 9.5, height: 15 }}>{s.note}</span>}
          </div>
        );
        return (
          <span key={s.stage} className="row" style={{ gap: 0 }}>
            {s.to && s.state !== "locked" ? <Link to={s.to} style={{ color: "inherit" }}>{inner}</Link> : inner}
            {i < stages.length - 1 && <span style={{ width: 26, height: 1, background: "var(--color-line-2)", margin: "0 4px", display: "inline-block" }} />}
          </span>
        );
      })}
    </div>
  );
}
