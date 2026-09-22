"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, getStoredChannelId } from "../../lib/api";

type Event = {
  id: string; query: string; topic_key: string; topic_label: string; event_type: string;
  current_signal: number; previous_signal: number; delta_signal: number; confidence: number;
  created_at?: string | null;
};
type ChannelList = { channels: { id: string; name: string }[] };

const eventClass: Record<string, string> = { NEW: "success", RISING: "success", FALLING: "warn", DISAPPEARING: "danger" };

export default function TrendsPage() {
  const [channelId, setChannelId] = useState<string | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [filter, setFilter] = useState("");
  const [message, setMessage] = useState("");

  async function load(id: string) {
    const query = filter ? `?event_type=${encodeURIComponent(filter)}` : "";
    const result = await apiGet<{ events: Event[] }>(`/api/v1/trends/channels/${id}/events${query}`);
    setEvents(result.events || []);
  }

  useEffect(() => {
    void (async () => {
      const channels = await apiGet<ChannelList>("/api/v1/channels");
      const id = getStoredChannelId() || channels.channels[0]?.id || null;
      if (id) { setChannelId(id); await load(id); }
    })().catch(e => setMessage(e instanceof Error ? e.message : "Failed to load trends"));
  }, []);

  useEffect(() => {
    if (!channelId) return;
    void load(channelId).catch(e => setMessage(e instanceof Error ? e.message : "Failed to refresh trends"));
  }, [filter]);

  return <Shell>
    <div className="topbar"><div><div className="kicker">Research intelligence v1.9</div><h1>Trend Intelligence</h1><p className="sub">Compare consecutive research snapshots and surface observable changes in topic signals.</p></div><div className="actions"><a className="btn" href="/research">Research Graph</a><a className="btn" href="/research-scheduler">Scheduler</a></div></div>
    {message && <div className="error" style={{marginBottom:16}}>{message}</div>}
    <div className="panel" style={{marginBottom:16}}>
      <div className="cardTitle"><div><h2>Trend events</h2><p className="sub">“Disappearing” means absent from the observed sample, not proof that the topic disappeared from YouTube.</p></div>
        <select className="select" style={{maxWidth:220}} value={filter} onChange={e=>setFilter(e.target.value)}><option value="">All events</option><option value="NEW">New</option><option value="RISING">Rising</option><option value="FALLING">Falling</option><option value="DISAPPEARING">Disappearing</option></select>
      </div>
      {events.length === 0 ? <div className="empty">Run Research or wait for the scheduler to create snapshots.</div> : <table className="table"><thead><tr><th>Topic</th><th>Event</th><th>Current</th><th>Previous</th><th>Delta</th><th>Confidence</th><th>Observed</th></tr></thead><tbody>{events.map(e=><tr key={e.id}><td><strong>{e.topic_label}</strong><div className="mini">{e.query} · {e.topic_key}</div></td><td><span className={`badge ${eventClass[e.event_type] || ""}`}>{e.event_type}</span></td><td>{(e.current_signal*100).toFixed(1)}</td><td>{(e.previous_signal*100).toFixed(1)}</td><td>{e.delta_signal >= 0 ? "+" : ""}{(e.delta_signal*100).toFixed(1)}</td><td>{Math.round(e.confidence*100)}%</td><td>{e.created_at ? new Date(e.created_at + (e.created_at.endsWith("Z") ? "" : "Z")).toLocaleString() : "—"}</td></tr>)}</tbody></table>}
    </div>
  </Shell>;
}
