/* Jobs and Admin: dock-only pages. */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { Job, User } from "../api/contracts";
import { useInvalidate, useMe } from "../api/queries";
import { Shell } from "../app/Shell";
import { Dock, DockFooter, DockHeader, Empty, Tag } from "../components/ui";

const JOB_TONE: Record<string, "ok" | "warn" | "bad" | "acc" | "mute"> = { succeeded: "ok", failed: "bad", cancelled: "warn", running: "acc", queued: "mute" };

export function JobsPage() {
  const jobs = useQuery({ queryKey: ["/api/jobs"], queryFn: () => api.get<(Job & { created_at?: string })[]>("/api/jobs"), refetchInterval: 3000 });
  return (
    <Shell crumb="Jobs">
      <div style={{ position: "absolute", inset: 0, background: "var(--color-bg)" }} />
      <Dock width={520}>
        <DockHeader eyebrow="System" title="Jobs" meta="rows survive a worker restart; the worker re-attaches to external tasks" />
        <div className="scroll" style={{ flex: 1 }}>
          {(jobs.data ?? []).map((j) => (
            <div key={j.id} style={{ padding: "8px 14px", borderBottom: "1px solid var(--color-line)" }}>
              <div className="row" style={{ justifyContent: "space-between" }}><span style={{ fontWeight: 600 }}>{j.kind}</span><Tag tone={JOB_TONE[j.status] ?? "mute"}>{j.status}</Tag></div>
              <div className="m" style={{ fontSize: 11, color: "var(--color-ink-2)", marginTop: 2 }}>{j.id.slice(0, 8)} · {j.stage ?? "—"} · {(j.progress * 100).toFixed(0)}% · {j.created_at?.slice(0, 16).replace("T", " ")}</div>
              {j.message && <div style={{ fontSize: 11.5, color: "var(--color-ink-2)" }}>{j.message}</div>}
              {j.error && <div style={{ fontSize: 11.5, color: "var(--color-bad)" }}>{j.error}</div>}
            </div>
          ))}
          {!jobs.data?.length && <Empty title="No jobs" hint="Fine coverage grids and processing tasks appear here." />}
        </div>
      </Dock>
    </Shell>
  );
}

export function AdminPage() {
  const me = useMe();
  const users = useQuery({ queryKey: ["/api/users"], queryFn: () => api.get<User[]>("/api/users"), enabled: me.data?.role === "admin" });
  const inv = useInvalidate();
  const health = useQuery({ queryKey: ["/api/health"], queryFn: () => api.get<{ status: string; version: string; kernel_version: string; checks: Record<string, Record<string, unknown>> }>("/api/health"), refetchInterval: 10000 });
  const [form, setForm] = useState({ email: "", name: "", role: "viewer", password: "" });
  const [err, setErr] = useState<string | null>(null);
  const create = async () => {
    setErr(null);
    try { await api.post("/api/users", form); setForm({ email: "", name: "", role: "viewer", password: "" }); inv("/api/users"); } catch (e) { setErr(e instanceof ApiError ? e.message : "failed"); }
  };
  const h = health.data;
  return (
    <Shell crumb="Admin">
      <div style={{ position: "absolute", inset: 0, background: "var(--color-bg)", padding: 24, paddingRight: 420 }}>
        <div className="panel" style={{ padding: 16, maxWidth: 560 }}>
          <div className="lbl">Service</div>
          {h ? (
            <div className="m" style={{ fontSize: 12, lineHeight: 1.8, marginTop: 6 }}>
              <div>status <Tag tone={h.status === "ok" ? "ok" : "bad"}>{h.status}</Tag> · version {h.version} · kernel {h.kernel_version}</div>
              {Object.entries(h.checks).map(([k, v]) => <div key={k}>{k}: <Tag tone={v.ok ? "ok" : "bad"}>{v.ok ? "ok" : "down"}</Tag> {Object.entries(v).filter(([kk]) => kk !== "ok").map(([kk, vv]) => `${kk} ${String(vv)}`).join(" · ")}</div>)}
            </div>
          ) : <Empty title="…" />}
        </div>
      </div>
      <Dock width={396}>
        <DockHeader eyebrow="System" title="Users" meta="viewer · surveyor (reviews, marks GCPs) · admin (users)" />
        <div className="scroll" style={{ flex: 1 }}>
          {(users.data ?? []).map((u) => (
            <div key={u.id} className="row" style={{ padding: "8px 14px", borderBottom: "1px solid var(--color-line)", justifyContent: "space-between" }}>
              <div><div style={{ fontWeight: 600 }}>{u.name}</div><div className="m" style={{ fontSize: 11, color: "var(--color-ink-2)" }}>{u.email}</div></div>
              <select className="input" style={{ width: "auto", height: 24 }} value={u.role} onChange={async (e) => { await api.patch(`/api/users/${u.id}`, { role: e.target.value }); inv("/api/users"); }}>
                {["viewer", "surveyor", "admin"].map((r) => <option key={r}>{r}</option>)}
              </select>
            </div>
          ))}
        </div>
        <div style={{ padding: "10px 14px", borderTop: "1px solid var(--color-line)", display: "flex", flexDirection: "column", gap: 6 }}>
          <div className="lbl">Add user</div>
          <input className="input" placeholder="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input" placeholder="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <div className="row"><select className="input" style={{ width: "auto" }} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{["viewer", "surveyor", "admin"].map((r) => <option key={r}>{r}</option>)}</select><input className="input" type="password" placeholder="password (10+ chars)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
          {err && <div className="tag t-bad" style={{ height: "auto", whiteSpace: "normal" }}>{err}</div>}
        </div>
        <DockFooter><button className="btn acc" onClick={create}>Create</button></DockFooter>
      </Dock>
    </Shell>
  );
}
