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
      await apiPost(path, body);
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  async function signInWithGoogle() {
    setError("");
    setBusy(true);
    try {
      const r = await apiPost<{ authorization_url: string }>("/api/v1/auth/google/start");
      window.location.href = r.authorization_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Google authentication failed");
      setBusy(false);
    }
  }

  return <main className="authPage">
    <div className="authCard">
      <div className="authBrand"><span className="authBrandMark">●</span><span>YouTube AI</span></div>
      <div className="kicker">Creator workspace</div>
      <h1>{mode === "login" ? "Welcome back" : "Create your studio"}</h1>
      <p className="sub">Connect Google once, then choose the YouTube channel you want the AI team to operate.</p>
      {error && <div className="error" style={{ marginTop: 16 }}>{error}</div>}

      <button className="googleBtn" disabled={busy} onClick={() => void signInWithGoogle()}>
        <span className="googleIcon">G</span>
        <span>{busy ? "Connecting…" : "Continue with Google"}</span>
      </button>

      <div className="authDivider"><span>or</span></div>

      <form onSubmit={(e) => void submit(e)} className="stack">
        {mode === "register" && <div className="field"><label htmlFor="auth-name">Name</label><input id="auth-name" className="input" autoComplete="name" value={name} onChange={e => setName(e.target.value)} /></div>}
        <div className="field"><label htmlFor="auth-email">Email</label><input id="auth-email" className="input" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="auth-password">Password</label><input id="auth-password" className="input" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={12} required value={password} onChange={e => setPassword(e.target.value)} /></div>
        {mode === "register" && <div className="field"><label htmlFor="auth-organization">Workspace name</label><input id="auth-organization" className="input" value={organizationName} onChange={e => setOrganizationName(e.target.value)} /></div>}
        <button className="btn primary" disabled={busy}>{mode === "login" ? "Sign in with email" : "Create account"}</button>
      </form>

      <button className="authSwitch" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Create a new account" : "I already have an account"}
      </button>
      <div className="authNote">Google OAuth uses the account chooser, so a user can select another Google account without signing out of the browser.</div>
    </div>
  </main>;
}
