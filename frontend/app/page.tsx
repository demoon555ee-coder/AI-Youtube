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
type GovernanceSummary = { policy?: { emergency_kill_switch?: boolean; default_mode?: string }; approvals?: any[] };
type PlanSummary = { id: string; name: string; status: string; auto_publish: boolean };
type PlanDetail = { plan: PlanSummary; items: { id: string; title: string; scheduled_for: string; status: string }[] };

function format(n: number) { return new Intl.NumberFormat("en-US", { notation: n >= 1000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n); }

export default function Dashboard() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [channels, setChannels] = useState<Channels["channels"]>([]);
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<RuntimeAvailability | null>(null);
  const [governance, setGovernance] = useState<GovernanceSummary | null>(null);
  const [plan, setPlan] = useState<PlanDetail | null>(null);
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
      if (channelId) {
        try {
          const g = await apiGet<GovernanceSummary>("/api/v1/governance/channels/" + channelId + "/policy");
          setGovernance(g);
          const plans = await apiGet<{ plans: PlanSummary[] }>("/api/v1/autopilot/channels/" + channelId + "/plans");
          const first = plans.plans?.[0];
          setPlan(first ? await apiGet<PlanDetail>("/api/v1/autopilot/channels/" + channelId + "/plans/" + first.id) : null);
        } catch {
          setGovernance(null);
          setPlan(null);
        }
      } else {
        setGovernance(null);
        setPlan(null);
      }
      setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load dashboard"); }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { void load(); }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  function findProvider(service: string, name: string) {
    return runtime?.services?.[service]?.find(item => item.provider === name);
  }

  const active = dashboard?.projects.find(p => !["PUBLISHED", "READY_TO_PUBLISH", "FAILED"].includes(p.status));
  const pendingApprovals = governance?.approvals?.length ?? 0;
  const nextItem = plan?.items?.find(i => ["SCHEDULED", "PLANNED", "READY"].includes(i.status)) ?? plan?.items?.[0];
  const nextPublish = nextItem?.scheduled_for
    ? new Date(nextItem.scheduled_for + "Z").toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })
    : "Not scheduled";
  const statusStep: Record<string, number> = { QUEUED: 0, RESEARCHING: 0, SCRIPTING: 1, STORYBOARDING: 2, DIRECTING_SCENES: 3, GENERATING_ASSETS: 4, EDITING: 5, GENERATING_THUMBNAIL: 6, QA: 6, READY_TO_PUBLISH: 7, PUBLISHED: 7, FAILED: 0 };
  const activeIndex = active ? statusStep[active.status] ?? -1 : -1;

  return <Shell>
    <div className="topbar">
      <div><div className="kicker">Channel overview</div><h1>{dashboard?.channel.name || "AI Lab"}</h1><p className="sub">{dashboard?.channel.niche || "Autonomous YouTube content operating system"}</p></div>
      <div className="actions">{channels.length > 1 && <select className="select" style={{width:210}} value={selectedChannelId || ""} onChange={e => { const id = e.target.value; storeChannelId(id, false); setSelectedChannelId(id); void load(id); }}>{channels.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>}<Link className="btn" href="/settings">Connect channel</Link><Link className="btn" href="/autopilot">Open Autopilot</Link><Link className="btn primary" href="/ideas">Open Content Factory</Link></div>
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

      <div className="grid grid3" style={{marginBottom:10}}>
        <section className="panel commandCard"><div className="cardTitle"><div><h2>Next AI action</h2><p className="sub">Priority from the channel's current state.</p></div><span className="badge success">Live</span></div><div className="commandValue">{active ? "Continue production" : "Start research"}</div><p className="mini">{active ? (active.title || active.topic) : "No active project - Content Factory is ready."}</p><div style={{marginTop:8}}><Link className="btn primary" href={active ? "/projects/"+active.id : "/ideas"}>{active ? "Continue" : "Create idea"}</Link></div></section>
        <section className="panel commandCard"><div className="cardTitle"><h2>Control & autopilot</h2><Link className="btn" href="/governance">Governance</Link></div><div className="commandStats"><div><span className="label">Approvals</span><strong>{pendingApprovals}</strong></div><div><span className="label">Kill switch</span><strong>{governance?.policy?.emergency_kill_switch ? "STOP" : "OK"}</strong></div><div><span className="label">Autopilot</span><strong>{plan?.plan.status || "No plan"}</strong></div><div><span className="label">Publication</span><strong>{nextPublish}</strong></div></div></section>
        <section className="panel commandCard"><div className="cardTitle"><h2>Media readiness</h2><Link className="btn" href="/routing">Routing</Link></div><div className="commandStats">{[["Video","video","runway"],["Images","image","openai_image"],["Voice","tts","elevenlabs"]].map(([label,service,provider])=>{const item=findProvider(service,provider);return <div key={label}><span className="label">{label}</span><strong>{item?.runtime_available ? "Ready" : "Unavailable"}</strong></div>;})}</div></section>
      </div>

      <div className="pinBoard">
        <article className="pinCard">
          <div className="pinMedia persimmon"><strong style={{fontSize:24,letterSpacing:"-.03em"}}>Build the next video.</strong></div>
          <div className="pinBody"><strong>Content Factory</strong><p>Turn a research-backed idea into a governed production workflow.</p><div style={{marginTop:12}}><Link href="/ideas" className="btn primary">Start from idea</Link></div></div>
        </article>
        <article className="pinCard">
          <div className="pinMedia blue"><strong style={{fontSize:24,letterSpacing:"-.03em"}}>{active?.status || "No active run"}</strong></div>
          <div className="pinBody"><strong>Active pipeline</strong><p>{active ? "Your current project is moving through the production graph." : "Start a project to activate the pipeline."}</p><div style={{marginTop:12}}><Link href={active ? `/projects/${active.id}` : "/ideas"} className="btn">{active ? "Open project" : "Create project"}</Link></div></div>
        </article>
        <article className="pinCard">
          <div className="pinMedia jade"><strong style={{fontSize:24,letterSpacing:"-.03em"}}>{dashboard.metrics.subscribers_net >= 0 ? "+" : ""}{format(dashboard.metrics.subscribers_net)}</strong></div>
          <div className="pinBody"><strong>Channel growth</strong><p>Net subscribers from the analytics layer for this selected channel.</p><div style={{marginTop:12}}><Link href="/analytics" className="btn">Open analytics</Link></div></div>
        </article>
        <article className="pinCard">
          <div className="pinMedia wasabi"><strong style={{fontSize:22,letterSpacing:"-.03em"}}>{dashboard.projects.length} projects</strong></div>
          <div className="pinBody"><strong>Production library</strong><p>Browse previous ideas, drafts, renders and publish states for this workspace.</p><div style={{marginTop:12}}><Link href="/projects" className="btn">View projects</Link></div></div>
        </article>
        <article className="pinCard">
          <div className="pinMedia plum"><strong style={{fontSize:22,letterSpacing:"-.03em"}}>Channel Brain</strong></div>
          <div className="pinBody"><strong>Learning loop</strong><p>Analytics, diagnosis, memory, next idea, while governance remains in control.</p><div style={{marginTop:12}}><Link href="/brain" className="btn">Open brain</Link></div></div>
        </article>
        <article className="pinCard">
          <div className="pinMedia blue"><strong style={{fontSize:22,letterSpacing:"-.03em"}}>Media stack</strong></div>
          <div className="pinBody"><strong>Provider routing</strong><p>See which video, image and voice providers are available for the next production.</p><div style={{marginTop:12}}><Link href="/routing" className="btn">Open routing</Link></div></div>
        </article>
      </div>
    </>}
  </Shell>;
}
