"use client";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

export default function AgentLearningPage() {
  const [channelId, setChannelId] = useState("");
  const [agentKey, setAgentKey] = useState("");
  const [actionType, setActionType] = useState("");
  const [observations, setObservations] = useState<any[]>([]);
  const [proposals, setProposals] = useState<any[]>([]);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [message, setMessage] = useState("");

  async function load() {
    if (!channelId) return;
    const [o,p,s] = await Promise.all([
      apiGet<any>(`/api/v1/learning/channels/${channelId}/observations`),
      apiGet<any>(`/api/v1/learning/channels/${channelId}/proposals`),
      apiGet<any>(`/api/v1/learning/channels/${channelId}/strategies`),
    ]);
    setObservations(o.observations || []); setProposals(p.proposals || []); setStrategies(s.strategies || []);
  }

  async function propose() {
    if (!channelId || !agentKey || !actionType) return;
    const response = await apiPost(`/api/v1/learning/channels/${channelId}/proposals`, { agent_key: agentKey, action_type: actionType, observation_limit: 25 });
    setMessage(response ? "Proposal created and awaiting human approval" : "Proposal creation failed");
    await load();
  }

  useEffect(() => { void load(); }, [channelId]);

  return (
    <main style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <h1>Agent Learning & Self-Improvement</h1>
      <p>Learning consumes authoritative task outcomes. Strategy proposals require human approval and cannot modify governance controls.</p>
      <section style={{ display: "grid", gap: 12, margin: "20px 0" }}>
        <input placeholder="Channel ID" value={channelId} onChange={(e) => setChannelId(e.target.value)} />
        <input placeholder="Agent key" value={agentKey} onChange={(e) => setAgentKey(e.target.value)} />
        <input placeholder="Action type" value={actionType} onChange={(e) => setActionType(e.target.value)} />
        <div><button onClick={() => void load()}>Refresh</button> <button onClick={() => void propose()}>Create strategy proposal</button></div>
        {message && <div>{message}</div>}
      </section>
      <section><h2>Active strategies ({strategies.length})</h2><pre>{JSON.stringify(strategies, null, 2)}</pre></section>
      <section><h2>Pending/history proposals ({proposals.length})</h2><pre>{JSON.stringify(proposals, null, 2)}</pre></section>
      <section><h2>Recent authoritative observations ({observations.length})</h2>
        <table style={{ width: "100%" }}><thead><tr><th>Agent</th><th>Action</th><th>Outcome</th><th>Success</th><th>Reward</th><th>Cost</th></tr></thead>
        <tbody>{observations.map((row) => <tr key={row.id}><td>{row.agent_key}</td><td>{row.action_type}</td><td>{row.outcome}</td><td>{String(row.success)}</td><td>{row.reward ?? "—"}</td><td>{row.cost_usd}</td></tr>)}</tbody></table>
      </section>
    </main>
  );
}
