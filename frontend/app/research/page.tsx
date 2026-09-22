"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId } from "../../lib/api";

type Opportunity = {
  id: string; topic: string; score: number; demand_signal: number; competition_signal: number;
  freshness_signal: number; gap_signal: number; channel_fit: number; rationale: any;
};
type ChannelList = { channels: { id: string; name: string }[] };

export default function ResearchPage() {
  const [channelId, setChannelId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [days, setDays] = useState("30");
  const [provider, setProvider] = useState("youtube_data");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function load(id: string) {
    const data = await apiGet<{ opportunities: Opportunity[] }>(`/api/v1/research-intelligence/channels/${id}/opportunities`);
    setOpportunities(data.opportunities || []);
  }

  useEffect(() => {
    void (async () => {
      const channels = await apiGet<ChannelList>("/api/v1/channels");
      const id = getStoredChannelId() || channels.channels[0]?.id;
      if (id) { setChannelId(id); await load(id); }
    })().catch(e => setMessage(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  async function scan() {
    if (!channelId || !query.trim()) return;
    setBusy(true); setMessage("");
    try {
      const res = await apiPost<any>(`/api/v1/research-intelligence/channels/${channelId}/scan`, {
        query, max_results: 10, published_after_days: Number(days), provider,
      });
      setOpportunities(res.opportunities || []);
      setMessage(`Research completed: ${res.result_count} sources → ${res.opportunities?.length || 0} opportunity signal(s).`);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Research failed"); }
    finally { setBusy(false); }
  }

  async function generateIdeas(opportunityId: string) {
    if (!channelId) return;
    setBusy(true); setMessage("");
    try {
      const res = await apiPost<any>(`/api/v1/research-intelligence/channels/${channelId}/opportunities/generate-ideas`, {
        opportunity_ids: [opportunityId], count: 10, goal: "balanced",
      });
      setMessage(`${res.ideas?.length || 0} ideas generated from the research opportunity. Open Ideas to continue.`);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Idea generation failed"); }
    finally { setBusy(false); }
  }

  return <Shell>
    <div className="topbar"><div><div className="kicker">Research intelligence v1.9</div><h1>Research Graph</h1><p className="sub">Discover public signals, persistent research entities, and opportunity hypotheses for this channel.</p></div><div className="actions"><a className="btn" href="/trends">Trend Intelligence</a><a className="btn" href="/research-scheduler">Research Scheduler</a></div></div>
    {message && <div className="notice" style={{marginBottom:16}}>{message}</div>}
    <div className="panel" style={{marginBottom:16}}>
      <div className="formRow">
        <div className="field" style={{flex:2}}><label>Topic / query</label><input className="input" value={query} onChange={e=>setQuery(e.target.value)} placeholder="e.g. AI coding agents" /></div>
        <div className="field"><label>Freshness (days)</label><input className="input" type="number" min="1" max="365" value={days} onChange={e=>setDays(e.target.value)} /></div>
        <div className="field"><label>Provider</label><select className="select" value={provider} onChange={e=>setProvider(e.target.value)}><option value="youtube_data">YouTube Data API</option><option value="mock">Mock</option><option value="http_json">HTTP JSON</option></select></div>
      </div>
      <button className="btn primary" style={{marginTop:12}} disabled={busy || !query.trim() || !channelId} onClick={()=>void scan()}>{busy ? "Scanning…" : "Scan opportunity"}</button>
    </div>
    <div className="panel"><div className="cardTitle"><div><h2>Opportunity signals</h2><p className="sub">Heuristic signals from the latest research scan; not performance guarantees.</p></div></div>
      {opportunities.map(o => <div className="listItem" key={o.id} style={{display:"grid",gridTemplateColumns:"2fr repeat(5, 100px) 130px",gap:12,alignItems:"center"}}>
        <div><strong>{o.topic}</strong><div className="mini">{o.rationale?.top_result?.title || "Research signal"}</div></div>
        <div><span className="label">Score</span><strong>{Math.round(o.score*100)}</strong></div>
        <div><span className="label">Demand</span>{Math.round(o.demand_signal*100)}</div>
        <div><span className="label">Competition</span>{Math.round(o.competition_signal*100)}</div>
        <div><span className="label">Freshness</span>{Math.round(o.freshness_signal*100)}</div>
        <div><span className="label">Gap</span>{Math.round(o.gap_signal*100)}</div>
        <button className="btn" disabled={busy} onClick={()=>void generateIdeas(o.id)}>Generate ideas</button>
      </div>)}
      {opportunities.length===0 && <div className="empty">Run a research scan to populate the opportunity layer.</div>}
    </div>
  </Shell>
}
