"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "../components/Shell";
import { apiGet, getStoredChannelId, storeChannelId } from "../lib/api";

const steps = ["Research", "Script", "Storyboard", "Scene Director", "Production", "Editor", "QA", "Publish"];
type Dashboard = { channel: { id: string; name: string; niche?: string; language: string; youtube_channel_id?: string | null }; metrics: { views: number; watch_time_minutes: number; subscribers_net: number; videos: number }; projects: { id: string; topic: string; status: string; title?: string }[] };
type Channels = { channels: { id: string; name: string; niche?: string; language: string }[] };

function format(n: number) { return new Intl.NumberFormat("en-US", { notation: n >= 1000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n); }

export default function Dashboard() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [channels, setChannels] = useState<Channels["channels"]>([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      const list = await apiGet<Channels>("/api/v1/channels");
      setChannels(list.channels);
      let channelId = getStoredChannelId();
      if (!channelId || !list.channels.some(c => c.id === channelId)) {
        channelId = list.channels[0]?.id || null;
        if (channelId) storeChannelId(channelId);
      }
      if (channelId) setDashboard(await apiGet<Dashboard>(`/api/v1/channels/${channelId}/dashboard`));
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load dashboard"); }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { void load(); }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const active = dashboard?.projects.find(p => !["PUBLISHED", "READY_TO_PUBLISH", "FAILED"].includes(p.status));
  const statusStep: Record<string, number> = { QUEUED: 0, RESEARCHING: 0, SCRIPTING: 1, STORYBOARDING: 2, DIRECTING_SCENES: 3, GENERATING_ASSETS: 4, EDITING: 5, GENERATING_THUMBNAIL: 6, QA: 6, READY_TO_PUBLISH: 7, PUBLISHED: 7, FAILED: 0 };
  const activeIndex = active ? statusStep[active.status] ?? -1 : -1;

  return <Shell>
    <div className="topbar">
      <div><div className="kicker">Channel overview</div><h1>{dashboard?.channel.name || "AI Lab"}</h1><p className="sub">{dashboard?.channel.niche || "Autonomous YouTube content operating system"}</p></div>
      <div className="actions"><Link className="btn" href="/settings">Connect channel</Link><Link className="btn" href="/autopilot">Open Autopilot</Link><Link className="btn primary" href="/ideas">Open Content Factory</Link></div>
    </div>

    {error && <div className="error" style={{marginBottom:16}}>{error}</div>}
    {!dashboard && !error && <div className="panel empty">Create a channel in Settings to activate the AI workspace.</div>}

    {dashboard && <>
      <div className="grid grid4" style={{marginBottom:16}}>
        {[["Views", format(dashboard.metrics.views)], ["Watch time", `${format(dashboard.metrics.watch_time_minutes / 60)} h`], ["Subscribers net", `${dashboard.metrics.subscribers_net >= 0 ? "+" : ""}${format(dashboard.metrics.subscribers_net)}`], ["Projects", String(dashboard.metrics.videos)]].map(([label,value]) => <div className="panel metric" key={label}><span className="label">{label}</span><span className="value">{value}</span><span className="badge success">Live backend data</span></div>)}
      </div>

      <div className="panel" style={{marginBottom:16}}>
        <div className="cardTitle"><div><h2>Active content pipeline</h2><p className="sub">The workflow is executed asynchronously; this page polls for progress.</p></div><span className={`badge ${active?.status === "FAILED" ? "danger" : "warn"}`}>{active?.status || "No active project"}</span></div>
        <div className="pipeline">{steps.map((step, i) => <div key={step} className={`step ${activeIndex >= 0 && i < activeIndex ? "done" : ""} ${activeIndex === i ? "active" : ""}`}><div className="dot"/><div className="name">{step}</div></div>)}</div>
      </div>

      <div className="grid grid2">
        <div className="panel"><div className="cardTitle"><h2>Recent projects</h2><Link href="/projects" className="btn">View all</Link></div>
          {dashboard.projects.length === 0 ? <div className="empty">No projects yet.</div> : dashboard.projects.slice(0,5).map(p => <div className="idea" key={p.id}><div className="ideaText"><strong>{p.title || p.topic}</strong><small>{p.status}</small></div><Link href={`/projects/${p.id}`} className="btn">Open</Link></div>)}
        </div>
        <div className="panel"><div className="cardTitle"><h2>Channel Brain</h2><Link href="/brain" className="btn">Open</Link></div><p className="sub">Learned patterns are fed back into Idea and Script Agents.</p><div style={{marginTop:18}} className="stack"><div><span className="label">Automation loop</span><div style={{marginTop:6}}>Analytics → diagnosis → memory → next idea</div></div><div><span className="label">YouTube</span><div style={{marginTop:6}}>{dashboard.channel.youtube_channel_id ? "Connected" : "Not connected yet"}</div></div></div></div>
      </div>
    </>}
  </Shell>;
}
