"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId, storeChannelId } from "../../lib/api";

type Blueprint = {
  id: string;
  idea_id?: string | null;
  format: string;
  hook_pattern: string;
  target_duration_minutes: number;
  visual_change_seconds: number;
  packaging: Record<string, unknown>;
  experiment_spec: Record<string, unknown>;
  confidence: number;
};
type Idea = { id: string; title: string; topic: string };
type Channels = { channels: { id: string; name: string }[] };

type Overview = {
  memory_version: number;
  format_usage: Record<string, number>;
  hook_usage: Record<string, number>;
  blueprint_count: number;
};

export default function IntelligencePage() {
  const [channelId, setChannelId] = useState<string | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function load(id: string) {
    const [o, b, i] = await Promise.all([
      apiGet<Overview>(`/api/v1/intelligence/channels/${id}/overview`),
      apiGet<{ blueprints: Blueprint[] }>(`/api/v1/intelligence/channels/${id}/blueprints?limit=30`),
      apiGet<{ ideas: Idea[] }>(`/api/v1/content/channels/${id}/ideas?limit=30`),
    ]);
    setOverview(o); setBlueprints(b.blueprints); setIdeas(i.ideas);
  }

  useEffect(() => {
    void (async () => {
      const channels = await apiGet<Channels>("/api/v1/channels");
      const id = getStoredChannelId() || channels.channels[0]?.id;
      if (id) { storeChannelId(id); setChannelId(id); await load(id); }
    })().catch(e => setMessage(e instanceof Error ? e.message : "Failed to load intelligence"));
  }, []);

  async function build(ideaId: string) {
    if (!channelId) return;
    setBusy(true); setMessage("");
    try {
      await apiPost(`/api/v1/intelligence/channels/${channelId}/ideas/${ideaId}/blueprint`, { goal: "balanced" });
      await load(channelId);
      setMessage("Content blueprint generated from Channel Brain signals.");
    } catch (e) { setMessage(e instanceof Error ? e.message : "Blueprint generation failed"); }
    finally { setBusy(false); }
  }

  return <Shell>
    <div className="topbar"><div><div className="kicker">Content intelligence</div><h1>Blueprints</h1><p className="sub">The system chooses format, hook, duration, visual pacing and an experiment for each concept.</p></div></div>
    {message && <div className="notice" style={{marginBottom:16}}>{message}</div>}
    {overview && <div className="grid4" style={{marginBottom:16}}>
      <div className="metric"><span>Memory</span><strong>v{overview.memory_version}</strong></div>
      <div className="metric"><span>Blueprints</span><strong>{overview.blueprint_count}</strong></div>
      <div className="metric"><span>Top format</span><strong>{Object.entries(overview.format_usage).sort((a,b)=>b[1]-a[1])[0]?.[0] || "—"}</strong></div>
      <div className="metric"><span>Top hook</span><strong>{Object.entries(overview.hook_usage).sort((a,b)=>b[1]-a[1])[0]?.[0] || "—"}</strong></div>
    </div>}
    <div className="panel" style={{marginBottom:16}}><div className="cardTitle"><div><h2>Ideas waiting for a blueprint</h2><p className="sub">Turn a concept into a production strategy before rendering starts.</p></div></div><table className="table"><thead><tr><th>Idea</th><th>Topic</th><th></th></tr></thead><tbody>{ideas.filter(i => !blueprints.some(b => b.idea_id === i.id)).slice(0,10).map(i => <tr key={i.id}><td><strong>{i.title}</strong></td><td>{i.topic}</td><td><button className="btn" disabled={busy} onClick={() => void build(i.id)}>Build blueprint</button></td></tr>)}</tbody></table></div>
    <div className="panel"><div className="cardTitle"><div><h2>Recent blueprints</h2><p className="sub">Stored decisions remain reusable by Autopilot and production agents.</p></div></div><table className="table"><thead><tr><th>Format</th><th>Hook</th><th>Duration</th><th>Visual</th><th>Confidence</th><th>Experiment</th></tr></thead><tbody>{blueprints.map(b => <tr key={b.id}><td><strong>{b.format}</strong></td><td>{b.hook_pattern}</td><td>{b.target_duration_minutes} min</td><td>{b.visual_change_seconds}s</td><td>{Math.round(b.confidence * 100)}%</td><td>{String((b.experiment_spec as any)?.dimension || "—")}</td></tr>)}</tbody></table>{blueprints.length === 0 && <div className="empty">No blueprints yet.</div>}</div>
  </Shell>;
}
