"use client";

import { useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost } from "../../lib/api";

type PrivacyRequest = { id: string; request_type: string; status: string; created_at: string; completed_at?: string | null };

export default function PrivacyPage() {
  const [password, setPassword] = useState("");
  const [reason, setReason] = useState("");
  const [requests, setRequests] = useState<PrivacyRequest[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function exportData() {
    setMessage("");
    try {
      const data = await apiGet<Record<string, unknown>>("/api/v1/privacy/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "youtube-ai-platform-personal-data.json";
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage("Your personal-data export was generated in the browser.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Export failed");
    }
  }

  async function requestDeletion() {
    setBusy(true); setMessage("");
    try {
      await apiPost("/api/v1/privacy/deletion-request", { password, reason: reason || undefined });
      setPassword("");
      setReason("");
      setMessage("Erasure request submitted. The background worker will process it.");
      const data = await apiGet<{ requests: PrivacyRequest[] }>("/api/v1/privacy/requests");
      setRequests(data.requests);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Deletion request failed");
    } finally { setBusy(false); }
  }

  return <Shell>
    <div className="topbar"><div><div className="kicker">Privacy & security</div><h1>Privacy Center</h1><p className="sub">Export personal data, review privacy requests, and request account erasure.</p></div></div>
    {message && <div className="notice" style={{marginBottom:16}}>{message}</div>}
    <div className="grid grid2">
      <div className="panel">
        <h2>Export my data</h2>
        <p className="sub">The export excludes password hashes, session tokens, raw API keys, and encrypted provider credentials.</p>
        <button className="btn primary" style={{marginTop:16}} onClick={()=>void exportData()}>Download personal-data export</button>
      </div>
      <div className="panel">
        <h2>Request account erasure</h2>
        <p className="sub">Re-authentication is required. Personal identity and credentials are anonymized; organization-owned content is not silently deleted.</p>
        <div className="field" style={{marginTop:14}}><label>Current password</label><input className="input" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} /></div>
        <div className="field" style={{marginTop:12}}><label>Reason (optional)</label><textarea className="input" rows={4} maxLength={2000} value={reason} onChange={e=>setReason(e.target.value)} /></div>
        <button className="btn" style={{marginTop:14}} disabled={busy || !password} onClick={()=>void requestDeletion()}>{busy?"Submitting…":"Submit erasure request"}</button>
      </div>
    </div>
    <div className="panel" style={{marginTop:16}}>
      <div className="cardTitle"><h2>Recent requests</h2><button className="btn" onClick={()=>void apiGet<{requests:PrivacyRequest[]}>("/api/v1/privacy/requests").then(x=>setRequests(x.requests)).catch(e=>setMessage(e instanceof Error?e.message:"Unable to load requests"))}>Refresh</button></div>
      {requests.length===0 ? <div className="empty">No privacy requests loaded.</div> : <div className="table">{requests.map(r=><div className="tr" key={r.id}><span>{r.request_type}</span><span>{r.status}</span><span>{new Date(r.created_at).toLocaleString()}</span></div>)}</div>}
    </div>
  </Shell>;
}
