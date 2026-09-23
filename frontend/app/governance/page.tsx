"use client";

import { useEffect, useState } from "react";
import Shell from "../../../components/Shell";
import { apiGet, apiPost, apiPatch, getStoredChannelId, storeChannelId } from "@/lib/api";

type Channel = { id: string; name: string };

export default function GovernancePage(){
 const [channelId,setChannelId]=useState("");
 const [channels,setChannels]=useState<Channel[]>([]);
 const [policy,setPolicy]=useState<any>(null);
 const [approvals,setApprovals]=useState<any[]>([]);
 const [journal,setJournal]=useState<any[]>([]);
 const [loading,setLoading]=useState(false);
 const [message,setMessage]=useState("");

 async function load(id = channelId){
   if(!id)return;
   setLoading(true); setMessage("");
   try {
     const [p,a,j]=await Promise.all([
       apiGet<any>(`/api/v1/governance/channels/${id}/policy`),
       apiGet<any>(`/api/v1/governance/channels/${id}/approvals?status=PENDING`),
       apiGet<any>(`/api/v1/governance/channels/${id}/journal?limit=50`)
     ]);
     setPolicy(p); setApprovals(a.approvals??[]); setJournal(j.events??[]);
   } catch(e) {
     setMessage(e instanceof Error ? e.message : "Failed to load governance");
   } finally { setLoading(false); }
 }

 useEffect(()=>{
   void apiGet<{channels:Channel[]}>("/api/v1/channels").then(r=>{
     setChannels(r.channels);
     const id=getStoredChannelId() || r.channels[0]?.id || "";
     if(id){ storeChannelId(id); setChannelId(id); void load(id); }
   }).catch(e=>setMessage(e instanceof Error ? e.message : "Failed to load channels"));
 },[]);

 async function kill(enabled:boolean){
   setLoading(true); setMessage("");
   try { await apiPost(`/api/v1/governance/channels/${channelId}/kill-switch?enabled=${enabled}`); await load(); }
   catch(e){setMessage(e instanceof Error?e.message:"Kill-switch update failed")} finally{setLoading(false)}
 }
 async function approve(id:string){
   setLoading(true); setMessage("");
   try { await apiPost(`/api/v1/governance/approvals/${id}/approve`,{reason:"Approved in Agent Governance console."}); await load(); }
   catch(e){setMessage(e instanceof Error?e.message:"Approval failed")} finally{setLoading(false)}
 }
 async function reject(id:string){
   setLoading(true); setMessage("");
   try { await apiPost(`/api/v1/governance/approvals/${id}/reject`,{reason:"Rejected in Agent Governance console."}); await load(); }
   catch(e){setMessage(e instanceof Error?e.message:"Rejection failed")} finally{setLoading(false)}
 }
 async function setDefaultMode(mode:string){
   setLoading(true); setMessage("");
   try { await apiPatch(`/api/v1/governance/channels/${channelId}/policy`,{default_mode:mode}); await load(); }
   catch(e){setMessage(e instanceof Error?e.message:"Policy update failed")} finally{setLoading(false)}
 }

 return <Shell>
  <div className="topbar">
   <div><div className="kicker">Control plane</div><h1>Agent Governance & Human Oversight</h1><p className="sub">Risk tiers, approval queues, automation policies, emergency stop and the decision journal.</p></div>
  </div>
  {message && <div className="error" style={{marginBottom:16}}>{message}</div>}
  <div className="panel" style={{marginBottom:16}}>
   <div className="formRow">
    <div className="field"><label htmlFor="governance-channel">Channel</label><select id="governance-channel" className="select" value={channelId} onChange={e=>{storeChannelId(e.target.value);setChannelId(e.target.value);void load(e.target.value)}}><option value="">Choose…</option>{channels.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
    <div style={{display:"flex",alignItems:"end"}}><button className="btn" disabled={loading||!channelId} onClick={()=>void load()}>{loading?"Loading…":"Refresh"}</button></div>
   </div>
  </div>
  {policy&&<section className="grid grid3" style={{marginBottom:16}}>
   <div className="panel"><div className="label">Policy</div><div className="value">v{policy.policy_version} · {policy.enabled?"Enabled":"Disabled"}</div><div className="sub">Default: {policy.default_mode}</div><select className="select" style={{marginTop:10}} value={policy.default_mode} onChange={e=>void setDefaultMode(e.target.value)} disabled={loading}><option value="auto">auto</option><option value="approve">approve</option><option value="defer">defer</option><option value="block">block</option></select></div>
   <div className="panel"><div className="label">Emergency kill switch</div><div className="value">{policy.emergency_kill_switch?"ACTIVE":"OFF"}</div><button className="btn" style={{marginTop:10}} disabled={loading} onClick={()=>void kill(!policy.emergency_kill_switch)}>{policy.emergency_kill_switch?"Disable":"Enable"} kill switch</button></div>
   <div className="panel"><div className="label">Approval queue</div><div className="value">{approvals.length}</div><div className="sub">Pending human decisions</div></div>
  </section>}
  {policy&&<section className="panel" style={{marginBottom:16}}><div className="cardTitle"><h2>Action policies</h2></div><div className="stack">{(policy.actions??[]).map((a:any)=><div key={a.action_type} className="idea"><div className="ideaText"><strong>{a.action_type}</strong><small>Risk {a.risk_tier} · max ${Number(a.max_cost_usd).toFixed(2)} · confidence ≥ {a.min_confidence}</small></div><span className="badge">{a.automation_mode}{a.require_human_approval?" · human approval":""}</span></div>)}</div></section>}
  <section className="panel" style={{marginBottom:16}}><div className="cardTitle"><h2>Approval queue</h2></div><div className="stack">{approvals.map(a=><div key={a.id} className="idea"><div className="ideaText"><strong>{a.agent_task_id? `Agent task ${a.agent_task_id}` : `Run ${a.execution_run_id}`}</strong><small>{(a.metadata?.reasons??[]).join(" ")}</small></div><div className="actions"><button className="btn primary" disabled={loading} onClick={()=>void approve(a.id)}>Approve</button><button className="btn" disabled={loading} onClick={()=>void reject(a.id)}>Reject</button></div></div>)}{!approvals.length&&<div className="empty">No pending approvals.</div>}</div></section>
  <section className="panel"><div className="cardTitle"><h2>Why AI was allowed to act</h2></div><div className="stack">{journal.map(e=><div key={e.id} className="idea"><div className="ideaText"><strong>{e.action_type} · Risk {e.risk_tier}</strong><small>{(e.reasons??[]).join(" ")} · Policy v{e.policy_version} · {e.effective_mode}</small></div><span className={`badge ${e.allowed?"success":"danger"}`}>{e.allowed?"ALLOWED":"BLOCKED"} · {e.event_type}</span></div>)}{!journal.length&&<div className="empty">No governance events yet.</div>}</div></section>
 </Shell>
}
