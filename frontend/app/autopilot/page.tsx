"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId, storeChannelId } from "../../lib/api";

type Channel = { id: string; name: string; timezone?: string };
type Plan = { id: string; name: string; start_date: string; end_date: string; timezone: string; goal: string; cadence_per_week: number; publish_time: string; auto_publish: boolean; status: string };
type Item = { id: string; position: number; title: string; topic: string; angle: string; scheduled_for: string; production_start_at: string; status: string; project_id?: string | null };

type PlanDetail = { plan: Plan; items: Item[] };

export default function AutopilotPage() {
  const [channelId, setChannelId] = useState<string | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [detail, setDetail] = useState<PlanDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({ name: "30-Day Content Plan", start_date: new Date().toISOString().slice(0,10), horizon_days: 30, cadence_per_week: 3, publish_time: "18:00", goal: "balanced", timezone: "UTC", production_lead_hours: 24, auto_publish: false, seed_topics: "" });

  async function load() {
    const list = await apiGet<{channels:Channel[]}>("/api/v1/channels");
    setChannels(list.channels);
    const id = getStoredChannelId() || list.channels[0]?.id || null;
    if (!id) return;
    storeChannelId(id); setChannelId(id);
    const channel = list.channels.find(c => c.id === id);
    if (channel?.timezone && form.timezone === "UTC") setForm(f => ({...f, timezone: channel.timezone || "UTC"}));
    const r = await apiGet<{plans:Plan[]}>(`/api/v1/autopilot/channels/${id}/plans`); setPlans(r.plans);
    if (r.plans[0]) setDetail(await apiGet<PlanDetail>(`/api/v1/autopilot/channels/${id}/plans/${r.plans[0].id}`));
  }

  useEffect(() => { void load().catch(e => setMessage(e instanceof Error ? e.message : "Failed to load autopilot")); }, []);

  async function generate() {
    if (!channelId) return setMessage("Create a channel in Settings first.");
    setBusy(true); setMessage("");
    try {
      const p = await apiPost<Plan>(`/api/v1/autopilot/channels/${channelId}/plans`, {...form, horizon_days:Number(form.horizon_days), cadence_per_week:Number(form.cadence_per_week), production_lead_hours:Number(form.production_lead_hours), seed_topics:form.seed_topics ? form.seed_topics.split(",").map(x=>x.trim()).filter(Boolean) : []});
      const list = await apiGet<{plans:Plan[]}>(`/api/v1/autopilot/channels/${channelId}/plans`); setPlans(list.plans); setDetail(await apiGet<PlanDetail>(`/api/v1/autopilot/channels/${channelId}/plans/${p.id}`)); setMessage(`Plan created with ${new Date(p.end_date).getTime() >= new Date(p.start_date).getTime() ? "scheduled" : "draft"} slots.`);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Plan generation failed"); }
    finally { setBusy(false); }
  }

  async function activate() {
    if (!channelId || !detail) return; setBusy(true); setMessage("");
    try { await apiPost(`/api/v1/autopilot/channels/${channelId}/plans/${detail.plan.id}/activate`); setDetail(await apiGet<PlanDetail>(`/api/v1/autopilot/channels/${channelId}/plans/${detail.plan.id}`)); setMessage("Autopilot activated. The worker will materialize due items automatically."); }
    catch(e){setMessage(e instanceof Error?e.message:"Activation failed")} finally{setBusy(false)}
  }

  async function pause() {
    if (!channelId || !detail) return; setBusy(true); setMessage("");
    try { await apiPost(`/api/v1/autopilot/channels/${channelId}/plans/${detail.plan.id}/pause`); setDetail(await apiGet<PlanDetail>(`/api/v1/autopilot/channels/${channelId}/plans/${detail.plan.id}`)); setMessage("Autopilot paused. Existing workflows are not cancelled."); }
    catch(e){setMessage(e instanceof Error?e.message:"Pause failed")} finally{setBusy(false)}
  }

  async function materializeAll() {
    if (!channelId || !detail) return; setBusy(true); setMessage("");
    try { await apiPost(`/api/v1/autopilot/channels/${channelId}/plans/${detail.plan.id}/materialize`, {}); setDetail(await apiGet<PlanDetail>(`/api/v1/autopilot/channels/${channelId}/plans/${detail.plan.id}`)); setMessage("Plan items materialized into video projects."); }
    catch(e){setMessage(e instanceof Error?e.message:"Materialization failed")} finally{setBusy(false)}
  }

  return <Shell>
    <div className="topbar"><div><div className="kicker">Creator Autopilot</div><h1>30-Day Content Factory</h1><p className="sub">Generate a publishing calendar, turn slots into projects, and let the worker start production before each deadline.</p></div><div className="actions"><a className="btn" href="/ideas">Ideas</a><a className="btn primary" href="/settings">Channel settings</a></div></div>
    {message && <div className="notice" style={{marginBottom:16}}>{message}</div>}
    <div className="panel" style={{marginBottom:16}}><div className="cardTitle"><div><h2>Plan generator</h2><p className="sub">Publish times are interpreted in the selected IANA timezone; stored schedule timestamps are UTC.</p></div></div>
      <div className="formGrid">
        <div className="formRow"><div className="field"><label>Plan name</label><input className="input" value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></div><div className="field"><label>Start date</label><input className="input" type="date" value={form.start_date} onChange={e=>setForm({...form,start_date:e.target.value})}/></div></div>
        <div className="formRow"><div className="field"><label>Horizon (days)</label><input className="input" type="number" min="1" max="365" value={form.horizon_days} onChange={e=>setForm({...form,horizon_days:Number(e.target.value)})}/></div><div className="field"><label>Videos / week</label><input className="input" type="number" min="1" max="7" value={form.cadence_per_week} onChange={e=>setForm({...form,cadence_per_week:Number(e.target.value)})}/></div></div>
        <div className="formRow"><div className="field"><label>Publish time</label><input className="input" type="time" value={form.publish_time} onChange={e=>setForm({...form,publish_time:e.target.value})}/></div><div className="field"><label>Timezone</label><input className="input" value={form.timezone} onChange={e=>setForm({...form,timezone:e.target.value})} placeholder="Europe/Brussels"/></div></div>
        <div className="formRow"><div className="field"><label>Strategy</label><select className="select" value={form.goal} onChange={e=>setForm({...form,goal:e.target.value})}><option value="growth">Growth</option><option value="authority">Authority</option><option value="monetization">Monetization</option><option value="balanced">Balanced</option></select></div><div className="field"><label>Production lead (hours)</label><input className="input" type="number" min="0" max="168" value={form.production_lead_hours} onChange={e=>setForm({...form,production_lead_hours:Number(e.target.value)})}/></div></div>
        <div className="formRow"><div className="field"><label>Seed topics (comma-separated)</label><input className="input" value={form.seed_topics} onChange={e=>setForm({...form,seed_topics:e.target.value})} placeholder="AI agents, automation, future of work"/></div><div className="field"><label>Autopublish</label><select className="select" value={form.auto_publish ? "true":"false"} onChange={e=>setForm({...form,auto_publish:e.target.value==="true"})}><option value="false">Manual approval</option><option value="true">Schedule to YouTube</option></select></div></div>
        <button className="btn primary" disabled={busy || !channelId} onClick={()=>void generate()}>{busy ? "Generating…" : "Generate content plan"}</button>
      </div>
    </div>

    <div className="grid grid2">
      <div className="panel"><div className="cardTitle"><h2>Plans</h2><span className="badge success">{plans.length} saved</span></div>{plans.length===0?<div className="empty">No plans yet.</div>:plans.map(p=><button key={p.id} className="idea" style={{width:"100%",background:"transparent",border:0,color:"inherit",textAlign:"left"}} onClick={()=>channelId&&void apiGet<PlanDetail>(`/api/v1/autopilot/channels/${channelId}/plans/${p.id}`).then(setDetail)}><div className="ideaText"><strong>{p.name}</strong><small>{p.start_date} → {p.end_date} · {p.status}</small></div><span className="badge">{p.cadence_per_week}/wk</span></button>)}</div>
      <div className="panel">{!detail?<div className="empty">Select a plan to inspect the schedule.</div>:<><div className="cardTitle"><div><h2>{detail.plan.name}</h2><p className="sub">{detail.plan.status} · {detail.plan.timezone} · {detail.plan.publish_time}</p></div><div className="actions"><button className="btn" disabled={busy} onClick={()=>void materializeAll()}>Materialize all</button>{detail.plan.status === "ACTIVE" ? <button className="btn" disabled={busy} onClick={()=>void pause()}>Pause</button> : <button className="btn primary" disabled={busy} onClick={()=>void activate()}>Activate Autopilot</button>}</div></div><table className="table"><thead><tr><th>#</th><th>Video</th><th>Production start</th><th>Publish</th><th>Status</th></tr></thead><tbody>{detail.items.map(i=><tr key={i.id}><td>{i.position}</td><td><strong>{i.title}</strong><br/><span className="mini">{i.angle}</span></td><td>{new Date(i.production_start_at+"Z").toLocaleString()}</td><td>{new Date(i.scheduled_for+"Z").toLocaleString()}</td><td><span className={`badge ${i.status==="FAILED"?"danger":i.status==="SCHEDULED"?"success":"warn"}`}>{i.status}</span></td></tr>)}</tbody></table></>}</div>
    </div>
  </Shell>;
}
