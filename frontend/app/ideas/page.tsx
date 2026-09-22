"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId, storeChannelId } from "../../lib/api";

type Idea = { id: string; title: string; topic: string; hook: string; angle: string; composite_score: number; status: string; selected: boolean };
type IdeasResponse = { ideas: Idea[] };
type Channels = { channels: { id: string; name: string; niche?: string; language: string }[] };

export default function IdeasPage() {
  const [channelId, setChannelId] = useState<string | null>(null);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [seed, setSeed] = useState("");
  const [goal, setGoal] = useState("growth");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function loadIdeas(id: string) { setIdeas((await apiGet<IdeasResponse>(`/api/v1/content/channels/${id}/ideas`)).ideas); }
  async function init() {
    const list = await apiGet<Channels>("/api/v1/channels");
    const id = getStoredChannelId() || list.channels[0]?.id;
    if (id) { storeChannelId(id); setChannelId(id); await loadIdeas(id); }
  }
  useEffect(() => { void init().catch(e => setMessage(e instanceof Error ? e.message : "Failed to load ideas")); }, []);

  async function generate() {
    if (!channelId) return setMessage("Create a channel in Settings first.");
    setBusy(true); setMessage("");
    try {
      await apiPost(`/api/v1/content/channels/${channelId}/generate-ideas`, { seed_topics: seed ? [seed] : [], count: 10, goal });
      await loadIdeas(channelId);
      setSeed(""); setMessage("10 new ideas generated using Channel Brain context.");
    } catch (e) { setMessage(e instanceof Error ? e.message : "Generation failed"); }
    finally { setBusy(false); }
  }

  async function selectAndCreate(id: string) {
    if (!channelId) return;
    setBusy(true); setMessage("");
    try {
      await apiPost(`/api/v1/content/channels/${channelId}/ideas/${id}/select`);
      const project = await apiPost<{project_id: string}>(`/api/v1/content/channels/${channelId}/ideas/${id}/create-project`);
      window.location.href = `/projects/${project.project_id}`;
    } catch (e) { setMessage(e instanceof Error ? e.message : "Could not create project"); setBusy(false); }
  }

  return <Shell>
    <div className="topbar"><div><div className="kicker">Content factory</div><h1>Ideas</h1><p className="sub">Ideas are generated and ranked against the current channel memory.</p></div></div>
    {message && <div className="notice" style={{marginBottom:16}}>{message}</div>}
    <div className="panel" style={{marginBottom:16}}><div className="cardTitle"><div><h2>Generate ideas</h2><p className="sub">Use an optional topic seed or let the strategy engine explore the niche.</p></div></div><div className="formRow"><div className="field"><label htmlFor="topic-seed">Topic seed</label><input id="topic-seed" className="input" value={seed} onChange={e => setSeed(e.target.value)} placeholder="e.g. AI agents in 2027" /></div><div className="field"><label htmlFor="strategy-goal">Strategy goal</label><select id="strategy-goal" className="select" value={goal} onChange={e => setGoal(e.target.value)}><option value="growth">Growth</option><option value="authority">Authority</option><option value="monetization">Monetization</option><option value="balanced">Balanced</option></select></div></div><div style={{marginTop:12}}><button className="btn primary" disabled={busy || !channelId} onClick={() => void generate()}>{busy ? "Working…" : "Generate 10 ideas"}</button></div></div>
    <div className="panel"><table className="table"><thead><tr><th>Idea</th><th>Hook</th><th>Angle</th><th>AI score</th><th></th></tr></thead><tbody>{ideas.map(i => <tr key={i.id}><td><strong>{i.title}</strong><br/><span className="mini">{i.topic}</span></td><td>{i.hook}</td><td>{i.angle}</td><td className="score">{Math.round(i.composite_score * 100)}</td><td><button className="btn" disabled={busy} onClick={() => void selectAndCreate(i.id)}>Create project</button></td></tr>)}</tbody></table>{ideas.length === 0 && <div className="empty">No ideas yet. Generate the first batch.</div>}</div>
  </Shell>;
}
