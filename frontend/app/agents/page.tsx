"use client";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

export default function AgentsPage(){
 const [channelId,setChannelId]=useState("");
 const [agents,setAgents]=useState<any[]>([]);
 const [tasks,setTasks]=useState<any[]>([]);
 const [selected,setSelected]=useState<any>(null);
 const [loading,setLoading]=useState(false);
 async function load(){
   if(!channelId)return;
   setLoading(true);
   try {
     const [a,t]=await Promise.all([
       apiGet<any>(`/api/v1/agents/channels/${channelId}/agents`),
       apiGet<any>(`/api/v1/agents/channels/${channelId}/tasks`)
     ]);
     setAgents(a.agents??[]); setTasks(t.tasks??[]);
   } finally {setLoading(false);}
 }
 useEffect(()=>{if(channelId)void load()},[channelId]);
 return <main className="space-y-6">
  <div><h1 className="text-2xl font-semibold">Autonomous Agent Runtime</h1><p className="text-sm text-slate-500">Durable task state, governance admission, leases and execution lineage. Worker lifecycle controls are intentionally not exposed as operator shortcuts.</p></div>
  <div className="rounded-xl border p-4 flex gap-2"><input className="w-full rounded border px-3 py-2" value={channelId} onChange={e=>setChannelId(e.target.value)} placeholder="Channel UUID"/><button className="rounded bg-black px-4 py-2 text-white" onClick={()=>void load()}>{loading?"Loading…":"Refresh"}</button></div>
  {agents.length>0&&<section className="grid gap-3 md:grid-cols-5">{agents.map(a=><div key={a.agent_key} className="rounded-xl border p-4"><div className="font-semibold">{a.display_name}</div><div className="mt-1 text-xs text-slate-500">{a.capabilities.join(" · ")}</div><div className="mt-3 text-xs text-slate-500">Concurrency {a.max_concurrency}</div></div>)}</section>}
  <section className="rounded-xl border p-4"><div className="flex justify-between"><h2 className="font-semibold">Task queue</h2><span className="text-sm text-slate-500">{tasks.length} tasks</span></div>
   <div className="mt-3 grid gap-3">{tasks.map(t=><div key={t.id} className="rounded-lg border p-3">
    <div className="flex items-center justify-between"><div><span className="font-medium">{t.task_type}</span><span className="ml-2 text-xs text-slate-500">{t.agent_key}</span></div><span className="rounded-full border px-2 py-1 text-xs">{t.status}</span></div>
    <div className="mt-2 text-xs text-slate-500">Action {t.action_type} · risk {t.risk_tier} · governance {t.governance_mode} · approved {String(t.governance_approved)}</div>
    <div className="mt-1 text-xs text-slate-500">Priority {t.priority} · budget ${Number(t.requested_budget_usd).toFixed(2)} · actual ${Number(t.actual_cost_usd).toFixed(2)}</div>
    <button className="mt-3 rounded border px-3 py-1 text-sm" onClick={()=>setSelected(t)}>Inspect</button>
   </div>)}{!tasks.length&&<div className="text-sm text-slate-500">No tasks yet.</div>}</div>
  </section>
  {selected&&<section className="rounded-xl border p-4"><div className="flex justify-between"><h2 className="font-semibold">Task {selected.id}</h2><button className="text-sm underline" onClick={()=>setSelected(null)}>Close</button></div><pre className="mt-3 overflow-auto rounded bg-slate-50 p-3 text-xs">{JSON.stringify(selected,null,2)}</pre></section>}
 </main>
}
