"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId } from "../../lib/api";

type Channel = { id: string; name: string };
type Decision = {
  id: string; topic: string | null; priority_score: number; trend_boost: number; urgency: number;
  action: string; status: string; recommended_format: string; recommended_hook: string;
  recommended_duration_minutes: number; evidence: Record<string, unknown>; rationale: Record<string, unknown>;
};

type ChannelList = { channels: Channel[] };

export default function OpportunityIntelligencePage() {
  const [channelId, setChannelId] = useState<string | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [goal, setGoal] = useState("balanced");
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(id: string) {
    const response = await apiGet<{ decisions: Decision[] }>(`/api/v1/opportunity-intelligence/channels/${id}/decisions?limit=50`);
    setDecisions(response.decisions || []);
  }

  useEffect(() => {
    void (async () => {
      const response = await apiGet<ChannelList>("/api/v1/channels");
      setChannels(response.channels || []);
      const id = getStoredChannelId() || response.channels[0]?.id || null;
      if (id) { setChannelId(id); await load(id); }
    })().catch(e => setMessage(e instanceof Error ? e.message : "Failed to load opportunity intelligence"));
  }, []);

  async function analyze() {
    if (!channelId) return;
    setBusy(true); setMessage("");
    try {
      await apiPost(`/api/v1/opportunity-intelligence/channels/${channelId}/analyze`, { goal, limit: 50, min_score: 0 });
      await load(channelId);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Analysis failed");
    } finally { setBusy(false); }
  }

  return <Shell>
    <div className="topbar">
      <div>
        <div className="kicker">Content decision engine v2.0</div>
        <h1>Opportunity Intelligence</h1>
        <p className="sub">Turn research opportunities and recent trend events into auditable content priorities.</p>
      </div>
      <div className="actions">
        <select className="select" value={channelId || ""} onChange={async e => { const id = e.target.value || null; setChannelId(id); if (id) await load(id); }}>
          <option value="">Choose channel…</option>
          {channels.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="select" value={goal} onChange={e => setGoal(e.target.value)}>
          <option value="balanced">Balanced</option>
          <option value="growth">Growth</option>
          <option value="authority">Authority</option>
          <option value="monetization">Monetization</option>
        </select>
        <button className="btn primary" disabled={!channelId || busy} onClick={() => void analyze()}>{busy ? "Analyzing…" : "Run analysis"}</button>
      </div>
    </div>
    {message && <div className="error" style={{ marginBottom: 16 }}>{message}</div>}
    <div className="panel">
      <div className="cardTitle"><div><h2>Latest decisions</h2><p className="sub">Heuristic prioritization — signals are evidence for planning, not guaranteed outcomes.</p></div></div>
      {decisions.length === 0 ? <div className="empty">Run Opportunity Intelligence after research data is available.</div> : <table className="table"><thead><tr><th>Topic</th><th>Priority</th><th>Action</th><th>Trend boost</th><th>Urgency</th><th>Format</th><th>Hook</th><th>Duration</th></tr></thead><tbody>{decisions.map(d => <tr key={d.id}>
        <td><strong>{d.topic || "Untitled"}</strong></td>
        <td>{(d.priority_score * 100).toFixed(1)}</td>
        <td><span className={`badge ${d.status === "ACTIONABLE" ? "success" : "warn"}`}>{d.action}</span></td>
        <td>{d.trend_boost >= 0 ? "+" : ""}{(d.trend_boost * 100).toFixed(1)}</td>
        <td>{(d.urgency * 100).toFixed(1)}</td>
        <td>{d.recommended_format}</td>
        <td>{d.recommended_hook}</td>
        <td>{d.recommended_duration_minutes} min</td>
      </tr>)}</tbody></table>}
    </div>
  </Shell>;
}
