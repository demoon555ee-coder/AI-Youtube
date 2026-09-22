"use client";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
export default function ExecutionPage(){
 const [channelId,setChannelId]=useState(""); const [runs,setRuns]=useState<any[]>([]);
 async function load(){ if(!channelId)return; const data=await apiGet<{runs?:any[]}>(`/api/v1/execution/channels/${channelId}/runs`); setRuns(data.runs??[]);}
 useEffect(()=>{if(channelId)void load()},[channelId]);
 return <main className="space-y-6"><div><h1 className="text-2xl font-semibold">Autonomous Execution</h1><p className="text-sm text-slate-500">Optimization decisions become actions only after permission, Quality Gate and budget checks.</p></div><div className="rounded-xl border p-4 flex gap-2"><input className="w-full rounded border px-3 py-2" value={channelId} onChange={e=>setChannelId(e.target.value)} placeholder="Channel UUID"/><button className="rounded bg-black px-4 py-2 text-white" onClick={()=>void load()}>Refresh</button></div><div className="grid gap-4">{runs.map(r=><article key={r.id} className="rounded-xl border p-4"><div className="flex justify-between"><strong>{r.target_scope}</strong><span className="text-xs text-slate-500">{r.status}</span></div><div className="mt-2 text-sm">Mode: {r.mode} · Estimated: ${Number(r.estimated_cost_usd||0).toFixed(4)}</div><div className="mt-2 text-xs text-slate-500">{r.reason}</div></article>)}{!runs.length&&<div className="rounded-xl border p-6 text-sm text-slate-500">No execution runs yet.</div>}</div></main>}
