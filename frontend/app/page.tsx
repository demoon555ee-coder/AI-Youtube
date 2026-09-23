"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "../components/Shell";
import { apiGet, getStoredChannelId, storeChannelId } from "../lib/api";

const steps = ["Research", "Script", "Storyboard", "Scene Director", "Production", "Editor", "QA", "Publish"];
type Dashboard = { channel: { id: string; name: string; niche?: string; language: string; youtube_channel_id?: string | null }; metrics: { views: number; watch_time_minutes: number; subscribers_net: number; videos: number }; projects: { id: string; topic: string; status: string; title?: string }[] };
type Channels = { channels: { id: string; name: string; niche?: string; language: string }[] };
type ProviderStatus = { provider: string; kind: string; tier: string; priority: number; runtime_available: boolean; capabilities: Record<string, boolean> };
type RuntimeAvailability = { enabled: boolean; services: Record<string, ProviderStatus[]> };

function format(n: number) { return new Intl.NumberFormat("en-US", { notation: n >= 1000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n); }

export default function Dashboard() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [channels, setChannels] = useState<Channels["channels"]>([]);
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<RuntimeAvailability | null>(null);
  const [error, setError] = useState("");

  async function load(preferredChannelId?: string | null) {
    try {
      const list = await apiGet<Channels>("/api/v1/channels");
      setChannels(list.channels);
      let channelId = preferredChannelId ?? getStoredChannelId();
      if (!channelId || !list.channels.some(c => c.id === channelId)) {
        channelId = list.channels[0]?.id || null;
        if (channelId) storeChannelId(channelId);
      }
      setSelectedChannelId(channelId);
      if (channelId) setDashboard(await apiGet<Dashboard>(`/api/v1/channels/${channelId}/dashboard`));
      else setDashboard(null);
      try {
        setRuntime(await apiGet<RuntimeAvailability>("/api/v1/routing/runtime-availability"));
      } catch {
        setRuntime(null);
      }
      setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load dashboard"); }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { void load(); }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  function runtimeBadge(provider?: ProviderStatus) {
    return provider?.runtime_available ? "Ready" : "Unavailable";
  }

  function findProvider(service: string, name: string) {
    return runtime?.services?.[service]?.find(item => item.provider === name);
  }

  function chooseProvider(service: string, preferred: string[]) {
    const candidates = runtime?.services?.[service] || [];
    return preferred.map(name => candidates.find(item => item.provider === name)).find(item => item?.runtime_available)
      || preferred.map(name => candidates.find(item => item.provider === name)).find(Boolean);
  }

  const active = dashboard?.projects.find(p => !["PUBLISHED", "READY_TO_PUBLISH", "FAILED"].includes(p.status));
  const statusStep: Record<string, number> = { QUEUED: 0, RESEARCHING: 0, SCRIPTING: 1, STORYBOARDING: 2, DIRECTING_SCENES: 3, GENERATING_ASSETS: 4, EDITING: 5, GENERATING_THUMBNAIL: 6, QA: 6, READY_TO_PUBLISH: 7, PUBLISHED: 7, FAILED: 0 };
  const activeIndex = active ? statusStep[active.status] ?? -1 : -1;

  return <Shell>
    <div className="topbar">
      <div><div className="kicker">Channel overview</div><h1>{dashboard?.channel.name || "AI Lab"}</h1><p className="sub">{dashboard?.channel.niche || "Autonomous YouTube content operating system"}</p></div>
      <div className="actions">{channels.length > 1 && <select className="select" style={{width:210}} value={selectedChannelId || ""} onChange={e => { const id = e.target.value; storeChannelId(id); setSelectedChannelId(id); void load(id); }}>{channels.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>}<Link className="btn" href="/settings">Connect channel</Link><Link className="btn" href="/autopilot">Open Autopilot</Link><Link className="btn primary" href="/ideas">Open Content Factory</Link></div>
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

      <div className="panel" style={{marginBottom:16}}>
        <div className="cardTitle">
          <div><h2>Provider readiness</h2><p className="sub">Runtime checks show which providers can be used now. Secret values are never displayed.</p></div>
          <Link className="btn" href="/routing">Open routing</Link>
        </div>
        {!runtime?.enabled ? <div className="empty">Provider health is unavailable or disabled.</div> : <div className="grid grid3">
          {([
            { label: "Generative visuals", item: findProvider("visual", "openai_image") || findProvider("image", "openai_image") || findProvider("image", "stability_image") || findProvider("image", "mock_png") },
            { label: "Stock B-roll", item: findProvider("video", "pexels_video") },
            { label: "Voice", item: findProvider("tts", "elevenlabs") || findProvider("tts", "openai_tts") || findProvider("tts", "espeak") },
          ] as Array<{ label: string; item?: ProviderStatus }>).map(({ label, item }) => {
            const candidate = item;
            const capabilityText = candidate ? Object.keys(candidate.capabilities || {}).filter(k => candidate.capabilities[k]).join(", ") : "";
            return <div className="stat" key={label}>
              <span className="label">{label}</span>
              <div className="n">{candidate?.provider || "Not configured"}</div>
              <span className={"badge " + (candidate?.runtime_available ? "success" : "danger")}>{runtimeBadge(candidate)}</span>
              <div className="mini" style={{marginTop:8}}>{candidate ? candidate.tier + (capabilityText ? " · " + capabilityText : "") : "Add/configure a provider to enable this path."}</div>
            </div>;
          })}
        </div>}
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
