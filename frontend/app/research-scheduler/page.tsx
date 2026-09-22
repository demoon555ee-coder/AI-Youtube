"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId } from "../../lib/api";

type Channel = { id: string; name: string; niche?: string };
type Schedule = {
  id: string; name: string; query: string; provider?: string | null; cadence_hours: number;
  next_run_at: string; enabled: boolean; max_results: number; published_after_days?: number | null;
  auto_generate_ideas: boolean; idea_count: number; goal: string; max_runs_per_day: number;
  last_status: string; last_run_at?: string | null; failure_count: number; last_error?: string | null;
};
type Run = { id: string; trigger_type: string; status: string; started_at: string; finished_at?: string | null; result_count: number; opportunity_count: number; generated_idea_count: number; error_message?: string | null };

export default function ResearchSchedulerPage() {
  const [channelId, setChannelId] = useState<string | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<Schedule | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({ name: "Daily Opportunity Scan", query: "AI agents", cadence_hours: 24, provider: "mock", max_results: 10, published_after_days: 30, auto_generate_ideas: true, idea_count: 5, goal: "balanced", max_runs_per_day: 3 });

  async function loadSchedules(id: string) {
    const result = await apiGet<{ schedules: Schedule[] }>(`/api/v1/research-scheduler/channels/${id}/schedules`);
    setSchedules(result.schedules || []);
  }

  async function load() {
    const result = await apiGet<{ channels: Channel[] }>("/api/v1/channels");
    setChannels(result.channels || []);
    const id = getStoredChannelId() || result.channels[0]?.id || null;
    if (!id) return;
    setChannelId(id);
    await loadSchedules(id);
  }

  useEffect(() => { void load().catch(e => setMessage(e instanceof Error ? e.message : "Failed to load scheduler")); }, []);

  async function create() {
    if (!channelId) return setMessage("Create a channel first.");
    setBusy(true); setMessage("");
    try {
      await apiPost(`/api/v1/research-scheduler/channels/${channelId}/schedules`, {
        ...form,
        cadence_hours: Number(form.cadence_hours), max_results: Number(form.max_results),
        published_after_days: Number(form.published_after_days), idea_count: Number(form.idea_count),
        max_runs_per_day: Number(form.max_runs_per_day), provider: form.provider || null,
      });
      await loadSchedules(channelId);
      setMessage("Autonomous research schedule created.");
    } catch (e) { setMessage(e instanceof Error ? e.message : "Failed to create schedule"); }
    finally { setBusy(false); }
  }

  async function action(schedule: Schedule, endpoint: "run" | "enable" | "disable") {
    setBusy(true); setMessage("");
    try {
      await apiPost(`/api/v1/research-scheduler/schedules/${schedule.id}/${endpoint}`);
      await loadSchedules(channelId!);
      if (endpoint === "run") setMessage("Manual research run queued; the worker will execute it.");
      else setMessage(`Schedule ${endpoint === "enable" ? "enabled" : "disabled"}.`);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Scheduler action failed"); }
    finally { setBusy(false); }
  }

  async function showRuns(schedule: Schedule) {
    setSelected(schedule);
    if (!channelId) return;
    const result = await apiGet<{ runs: Run[] }>(`/api/v1/research-scheduler/schedules/${schedule.id}/runs`);
    setRuns(result.runs || []);
  }

  return <Shell>
    <div className="topbar"><div><div className="kicker">Research scheduler v1.8</div><h1>Autonomous Research</h1><p className="sub">Run recurring opportunity scans without manual intervention. Each run is checkpointed, bounded by a daily limit, and logged for audit.</p></div><div className="actions"><a className="btn" href="/research">Research Graph</a><a className="btn" href="/trends">Trend Intelligence</a><a className="btn primary" href="/autopilot">Creator Autopilot</a></div></div>
    {message && <div className="notice" style={{marginBottom:16}}>{message}</div>}
    {channels.length === 0 ? <div className="panel empty">Create a channel in Settings before configuring research schedules.</div> : <>
      <div className="panel" style={{marginBottom:16}}>
        <div className="cardTitle"><div><h2>Create research schedule</h2><p className="sub">The first scan runs immediately unless you set a future timestamp in the API.</p></div><span className="badge success">Worker-driven</span></div>
        <div className="formGrid">
          <div className="formRow"><div className="field"><label>Name</label><input className="input" value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></div><div className="field"><label>Query</label><input className="input" value={form.query} onChange={e=>setForm({...form,query:e.target.value})}/></div></div>
          <div className="formRow"><div className="field"><label>Cadence (hours)</label><input className="input" type="number" min="1" max="168" value={form.cadence_hours} onChange={e=>setForm({...form,cadence_hours:Number(e.target.value)})}/></div><div className="field"><label>Provider</label><select className="select" value={form.provider} onChange={e=>setForm({...form,provider:e.target.value})}><option value="mock">Mock</option><option value="youtube_data">YouTube Data API</option><option value="http_json">HTTP JSON</option></select></div></div>
          <div className="formRow"><div className="field"><label>Freshness window (days)</label><input className="input" type="number" min="1" max="3650" value={form.published_after_days} onChange={e=>setForm({...form,published_after_days:Number(e.target.value)})}/></div><div className="field"><label>Max runs / day</label><input className="input" type="number" min="1" max="24" value={form.max_runs_per_day} onChange={e=>setForm({...form,max_runs_per_day:Number(e.target.value)})}/></div></div>
          <div className="formRow"><div className="field"><label>Auto-generate ideas</label><select className="select" value={String(form.auto_generate_ideas)} onChange={e=>setForm({...form,auto_generate_ideas:e.target.value === "true"})}><option value="true">Yes</option><option value="false">No</option></select></div><div className="field"><label>Ideas per run</label><input className="input" type="number" min="1" max="50" value={form.idea_count} onChange={e=>setForm({...form,idea_count:Number(e.target.value)})}/></div></div>
          <button className="btn primary" disabled={busy || !channelId} onClick={()=>void create()}>{busy ? "Saving…" : "Create schedule"}</button>
        </div>
      </div>

      <div className="grid grid2">
        <div className="panel"><div className="cardTitle"><h2>Schedules</h2><span className="badge success">{schedules.filter(s=>s.enabled).length} active</span></div>
          {schedules.length === 0 ? <div className="empty">No recurring research schedules yet.</div> : schedules.map(s => <div className="listItem" key={s.id}>
            <div className="cardTitle" style={{marginBottom:8}}><div><strong>{s.name}</strong><div className="mini">{s.query} · every {s.cadence_hours}h · {s.provider || "default"}</div></div><span className={`badge ${s.enabled ? "success" : ""}`}>{s.enabled ? "ACTIVE" : "PAUSED"}</span></div>
            <div className="mini" style={{marginBottom:10}}>Next: {new Date(s.next_run_at + (s.next_run_at.endsWith("Z") ? "" : "Z")).toLocaleString()} · last: {s.last_status} · failures: {s.failure_count}</div>
            {s.last_error && <div className="error" style={{marginBottom:10}}>{s.last_error}</div>}
            <div className="actions"><button className="btn primary" disabled={busy} onClick={()=>void action(s,"run")}>Run now</button><button className="btn" disabled={busy} onClick={()=>void action(s,s.enabled?"disable":"enable")}>{s.enabled?"Pause":"Enable"}</button><button className="btn" disabled={busy} onClick={()=>void showRuns(s)}>Run history</button></div>
          </div>)}
        </div>
        <div className="panel"><div className="cardTitle"><div><h2>{selected ? selected.name : "Run history"}</h2><p className="sub">Every scan is recorded with results, opportunities, generated ideas and error state.</p></div></div>
          {!selected ? <div className="empty">Select a schedule to inspect its run history.</div> : runs.length === 0 ? <div className="empty">No runs recorded yet.</div> : <table className="table"><thead><tr><th>Started</th><th>Trigger</th><th>Status</th><th>Results</th><th>Opps</th><th>Ideas</th></tr></thead><tbody>{runs.map(r=><tr key={r.id}><td>{new Date(r.started_at+"Z").toLocaleString()}</td><td>{r.trigger_type}</td><td><span className={`badge ${r.status==="FAILED"?"danger":"success"}`}>{r.status}</span></td><td>{r.result_count}</td><td>{r.opportunity_count}</td><td>{r.generated_idea_count}</td></tr>)}</tbody></table>}
        </div>
      </div>
    </>}
  </Shell>;
}
