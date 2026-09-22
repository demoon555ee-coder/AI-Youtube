"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [organizationName, setOrganizationName] = useState("My YouTube Studio");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const path = mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register";
      const body = mode === "login"
        ? { email, password }
        : { email, password, name, organization_name: organizationName };
      await apiPost<{ user: { id: string } }>(path, body);
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
    <div className="panel" style={{ width: "min(520px, 100%)" }}>
      <div className="kicker">YouTube AI Platform</div>
      <h1>{mode === "login" ? "Sign in" : "Create your studio"}</h1>
      <p className="sub">Protected multi-tenant workspaces for autonomous YouTube operations.</p>
      {error && <div className="error" style={{ marginBottom: 16 }}>{error}</div>}
      <form onSubmit={(e) => void submit(e)} className="stack">
        <div className="field"><label htmlFor="auth-email">Email</label><input id="auth-email" aria-label="Email" className="input" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="auth-password">Password</label><input id="auth-password" aria-label="Password" className="input" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={12} required value={password} onChange={e => setPassword(e.target.value)} /></div>
        {mode === "register" && <>
          <div className="field"><label htmlFor="auth-name">Name</label><input id="auth-name" aria-label="Name" className="input" autoComplete="name" value={name} onChange={e => setName(e.target.value)} /></div>
          <div className="field"><label htmlFor="auth-organization">Organization</label><input id="auth-organization" aria-label="Organization" className="input" value={organizationName} onChange={e => setOrganizationName(e.target.value)} /></div>
        </>}
        <button className="btn primary" disabled={busy}>{busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}</button>
      </form>
      <div style={{ marginTop: 18 }}>
        <button className="btn" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Create a new account" : "I already have an account"}
        </button>
      </div>
    </div>
  </main>;
}
