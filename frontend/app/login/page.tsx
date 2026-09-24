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
      router.push("/onboarding/channels?source=email");
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

  return <main className="welcomeAuthPage">
    <section className="welcomeVisual" aria-label="YouTube AI workspace">
      <div className="visualNoise" />
      <div className="visualOrb orbOne" />
      <div className="visualOrb orbTwo" />
      <div className="visualOrbit orbitOne" />
      <div className="visualOrbit orbitTwo" />
      <div className="visualGrid" />
      <div className="welcomeVisualCopy">
        <div className="authBrand visualBrand"><span className="authBrandMark">●</span><span>YouTube AI</span></div>
        <div className="kicker visualKicker">Autonomous creator operating system</div>
        <h1>From idea to published video.</h1>
        <p>Research. Create. Produce. Publish. Learn. One governed workspace for every YouTube channel.</p>
        <div className="visualFlow">
          {["Research","Script","Production","Publish","Learn"].map((step, index) => <span key={step} className="flowStep"><i>{String(index + 1).padStart(2, "0")}</i>{step}</span>)}
        </div>
      </div>
    </section>

    <section className="welcomeAuthPane">
      <div className="authCard">
        <div className="authBrand mobileBrand"><span className="authBrandMark">●</span><span>YouTube AI</span></div>
        <div className="kicker">Welcome</div>
        <h1>{mode === "login" ? "Start your studio" : "Create your studio"}</h1>
        <p className="sub">Sign in with Google and we will load the YouTube channels available to your account. Then you choose which channel to work with.</p>
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
        <div className="authNote">Google opens the account chooser. After authorization, your available YouTube channels are loaded automatically.</div>
      </div>
    </section>
  </main>;
}
