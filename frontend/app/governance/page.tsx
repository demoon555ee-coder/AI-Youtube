"use client";
import { useEffect, useState } from "react";
import { apiGet, apiPost, apiPatch } from "@/lib/api";

export default function GovernancePage(){
 const [channelId,setChannelId]=useState("");
 const [policy,setPolicy]=useState<any>(null);
 const [approvals,setApprovals]=useState<any[]>([]);
 const [journal,setJournal]=useState<any[]>([]);
 const [loading,setLoading]=useState(false);
 async function load(){
   if(!channelId)return; setLoading(true);
   try {
     const [p,a,j]=await Promise.all([
       apiGet<any>(`/api/v1/governance/channels/${channelId}/policy`),
       apiGet<any>(`/api/v1/governance/channels/${channelId}/approvals?status=PENDING`),
       apiGet<any>(`/api/v1/governance/channels/${channelId}/journal?limit=50`)
     ]);
     setPolicy(p); setApprovals(a.approvals??[]); setJournal(j.events??[]);
   } finally { setLoading(false); }
 }
 async function kill(enabled:boolean){ await apiPost(`/api/v1/governance/channels/${channelId}/kill-switch?enabled=${enabled}`); await load(); }
 async function approve(id:string){ await apiPost(`/api/v1/governance/approvals/${id}/approve`,{reason:"Approved in Agent Governance console."}); await load(); }
 async function reject(id:string){ await apiPost(`/api/v1/governance/approvals/${id}/reject`,{reason:"Rejected in Agent Governance console."}); await load(); }
 async function setDefaultMode(mode:string){ await apiPatch(`/api/v1/governance/channels/${channelId}/policy`,{default_mode:mode}); await load(); }
 useEffect(()=>{if(channelId)void load()},[channelId]);
 return <main className="space-y-6">
  <div><h1 className="text-2xl font-semibold">Agent Governance & Human Oversight</h1><p className="text-sm text-slate-500">Risk tiers, approval queues, channel automation policies, emergency stop and the decision journal.</p></div>
  <div className="rounded-xl border p-4 flex gap-2"><input className="w-full rounded border px-3 py-2" value={channelId} onChange={e=>setChannelId(e.target.value)} placeholder="Channel UUID"/><button className="rounded bg-black px-4 py-2 text-white" onClick={()=>void load()}>{loading?"Loading…":"Refresh"}</button></div>
  {policy&&<section className="grid gap-4 md:grid-cols-3">
   <div className="rounded-xl border p-4"><div className="text-xs text-slate-500">Policy</div><div className="mt-1 font-semibold">v{policy.policy_version} · {policy.enabled?"Enabled":"Disabled"}</div><div className="mt-2 text-sm">Default: {policy.default_mode}</div><select className="mt-3 rounded border px-2 py-1" value={policy.default_mode} onChange={e=>void setDefaultMode(e.target.value)}><option value="auto">auto</option><option value="approve">approve</option><option value="defer">defer</option><option value="block">block</option></select></div>
   <div className="rounded-xl border p-4"><div className="text-xs text-slate-500">Emergency kill switch</div><div className="mt-1 font-semibold">{policy.emergency_kill_switch?"ACTIVE":"OFF"}</div><button className="mt-3 rounded border px-3 py-2" onClick={()=>void kill(!policy.emergency_kill_switch)}>{policy.emergency_kill_switch?"Disable":"Enable"} kill switch</button></div>
   <div className="rounded-xl border p-4"><div className="text-xs text-slate-500">Approval queue</div><div className="mt-1 text-2xl font-semibold">{approvals.length}</div><div className="text-sm text-slate-500">Pending human decisions</div></div>
  </section>}
  {policy&&<section className="rounded-xl border p-4"><h2 className="font-semibold">Action policies</h2><div className="mt-3 grid gap-3">{(policy.actions??[]).map((a:any)=><div key={a.action_type} className="rounded-lg border p-3 flex items-center justify-between"><div><div className="font-medium">{a.action_type}</div><div className="text-xs text-slate-500">Risk {a.risk_tier} · max ${Number(a.max_cost_usd).toFixed(2)} · confidence ≥ {a.min_confidence}</div></div><span className="rounded-full border px-2 py-1 text-xs">{a.automation_mode}{a.require_human_approval?" · human approval":""}</span></div>)}</div></section>}
  <section className="rounded-xl border p-4"><h2 className="font-semibold">Approval queue</h2><div className="mt-3 grid gap-3">{approvals.map(a=><div key={a.id} className="rounded-lg border p-3"><div className="flex justify-between"><span className="font-medium">{a.agent_task_id ? `Agent task ${a.agent_task_id}` : `Run ${a.execution_run_id}`}</span><span className="text-xs">{a.metadata?.risk_tier??"unknown"}</span></div><div className="mt-1 text-sm text-slate-600">{(a.metadata?.reasons??[]).join(" ")}</div><div className="mt-3 flex gap-2"><button className="rounded bg-black px-3 py-2 text-white" onClick={()=>void approve(a.id)}>Approve</button><button className="rounded border px-3 py-2" onClick={()=>void reject(a.id)}>Reject</button></div></div>)}{!approvals.length&&<div className="text-sm text-slate-500">No pending approvals.</div>}</div></section>
  <section className="rounded-xl border p-4"><h2 className="font-semibold">Why AI was allowed to act</h2><div className="mt-3 grid gap-2">{journal.map(e=><div key={e.id} className="rounded-lg border p-3 text-sm"><div className="flex justify-between"><span>{e.action_type} · Risk {e.risk_tier}</span><span>{e.allowed?"ALLOWED":"BLOCKED"} · {e.event_type}</span></div><div className="mt-1 text-slate-600">{(e.reasons??[]).join(" ")}</div><div className="mt-1 text-xs text-slate-400">Policy v{e.policy_version} · {e.effective_mode}</div></div>)}{!journal.length&&<div className="text-sm text-slate-500">No governance events yet.</div>}</div></section>
 </main>
}
