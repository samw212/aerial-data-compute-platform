import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useQueryClient } from "@tanstack/react-query";
import { Icon } from "../components/Icon";

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const qc = useQueryClient();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/login", { email, password });
      await qc.invalidateQueries({ queryKey: ["/api/auth/me"] });
      nav("/");
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : "could not sign in");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "radial-gradient(1200px 600px at 30% 20%, #131a24 0%, #0e1116 60%)" }}>
      <form onSubmit={submit} className="panel" style={{ width: 360, padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="row" style={{ gap: 8 }}>
          <span style={{ color: "var(--color-acc)", display: "inline-flex" }}><Icon name="target" size={20} /></span>
          <span style={{ fontWeight: 800, fontSize: 16, letterSpacing: "0.06em" }}>ADCP</span>
          <span style={{ color: "var(--color-ink-3)", fontSize: 12 }}>Aerial Data Compute Platform</span>
        </div>
        <label><div className="lbl" style={{ marginBottom: 4 }}>Email</div><input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></label>
        <label><div className="lbl" style={{ marginBottom: 4 }}>Password</div><input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {error && <div className="tag t-bad" style={{ height: "auto", padding: "6px 8px", whiteSpace: "normal" }}>{error}</div>}
        <button className="btn acc" type="submit" disabled={busy} style={{ justifyContent: "center" }}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </div>
  );
}
