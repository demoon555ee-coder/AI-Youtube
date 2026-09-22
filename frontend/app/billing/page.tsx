"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost } from "../../lib/api";

type Plan = {id:string; code:string; name:string; description:string; monthly_price_cents:number; currency:string; entitlements:Record<string, any>; active:boolean};
type Summary = {plan:{code:string;name:string;monthly_price_cents:number;currency:string}; period:{start:string;end:string}; usage:Record<string,number>; entitlements:Record<string,any>};

function money(cents:number,currency:string){return new Intl.NumberFormat("en-US",{style:"currency",currency}).format(cents/100)}

export default function BillingPage(){
 const [plans,setPlans]=useState<Plan[]>([]); const [summary,setSummary]=useState<Summary|null>(null); const [message,setMessage]=useState(""); const [busy,setBusy]=useState("");
 async function load(){const [p,s]=await Promise.all([apiGet<{plans:Plan[]}>("/api/v1/billing/catalog"),apiGet<Summary>("/api/v1/billing/summary")]);setPlans(p.plans);setSummary(s)}
 useEffect(()=>{void load().catch(e=>setMessage(e instanceof Error?e.message:"Unable to load billing"))},[]);
 async function switchPlan(code:string){setBusy(code);setMessage("");try{if(code==="free"){await apiPost("/api/v1/billing/cancel",{at_period_end:true});setMessage("Downgrade scheduled for the end of the current billing period.");await load()}else{const r=await apiPost<{url:string}>("/api/v1/billing/checkout",{plan_code:code});window.location.href=r.url}}catch(e){setMessage(e instanceof Error?e.message:"Plan change failed")}finally{setBusy("")}}
 async function cancel(){setBusy("cancel");try{await apiPost("/api/v1/billing/cancel",{at_period_end:true});await load();setMessage("Cancellation scheduled for the end of the current billing period.")}catch(e){setMessage(e instanceof Error?e.message:"Cancellation failed")}finally{setBusy("")}}
 return <Shell><div className="topbar"><div><div className="kicker">Workspace billing</div><h1>Billing & Usage</h1><p className="sub">Plans, entitlements, usage and billing-provider state.</p></div><div className="actions"><button className="btn" onClick={()=>void cancel()} disabled={!summary||busy!==""}>Cancel at period end</button></div></div>
 {message&&<div className="notice" style={{marginBottom:16}}>{message}</div>}
 <div className="grid grid3" style={{marginBottom:16}}>
  {plans.map(plan=><div className={`panel ${summary?.plan.code===plan.code?"selectedPlan":""}`} key={plan.code}><div className="cardTitle"><h2>{plan.name}</h2>{summary?.plan.code===plan.code&&<span className="badge success">Current</span>}</div><div className="value" style={{margin:"10px 0"}}>{money(plan.monthly_price_cents,plan.currency)}<span className="mini"> / month</span></div><p className="sub">{plan.description}</p><div className="stack" style={{marginTop:14}}><div>Channels: <strong>{plan.entitlements.max_channels}</strong></div><div>Video projects: <strong>{plan.entitlements.monthly_video_projects}</strong></div><div>LLM requests: <strong>{plan.entitlements.monthly_llm_requests}</strong></div><div>Render minutes: <strong>{plan.entitlements.monthly_render_minutes}</strong></div></div>{summary?.plan.code!==plan.code&&<button className="btn primary" style={{marginTop:16,width:"100%"}} disabled={!!busy} onClick={()=>void switchPlan(plan.code)}>{busy===plan.code?"Applying…":plan.monthly_price_cents===0?"Downgrade at period end":"Choose plan"}</button>}</div>)}
 </div>
 {summary&&<div className="grid grid2"><div className="panel"><h2>Current usage</h2><div className="table"><div className="tr"><span>Metric</span><span>Used</span><span>Limit</span></div>{Object.entries(summary.entitlements).filter(([,v])=>typeof v==="number").map(([key,limit])=><div className="tr" key={key}><span>{key}</span><span>{summary.usage[key]??0}</span><span>{limit}</span></div>)}</div></div><div className="panel"><h2>Billing period</h2><div className="stack" style={{marginTop:14}}><div><span className="label">Start</span><div>{new Date(summary.period.start).toLocaleString()}</div></div><div><span className="label">End</span><div>{new Date(summary.period.end).toLocaleString()}</div></div><div><span className="label">Plan</span><div>{summary.plan.name}</div></div><div><span className="label">Monthly price</span><div>{money(summary.plan.monthly_price_cents,summary.plan.currency)}</div></div></div></div></div>}
 </Shell>
}
