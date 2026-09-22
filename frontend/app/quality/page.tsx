"use client";
import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, getStoredChannelId } from "../../lib/api";

type Report = { id:string; project_id:string; status:string; score:number; duration_seconds:number; width:number; height:number; issues:string[]; recommendations:string[]; created_at:string };
export default function QualityPage(){
 const [rows,setRows]=useState<Report[]>([]); const [error,setError]=useState("");
 useEffect(()=>{ const id=getStoredChannelId(); if(!id)return; void apiGet<{projects:any[]}>(`/api/v1/channels/${id}/projects`).then(async r=>{ const out:Report[]=[]; for(const p of r.projects.slice(0,20)){ try { const q=await apiGet<{reports:Report[]}>(`/api/v1/quality/projects/${p.id}/reports`); if(q.reports[0]) out.push(q.reports[0]); } catch {} } setRows(out); }).catch(e=>setError(e instanceof Error?e.message:"Failed to load quality reports")); },[]);
 return <Shell><div className="topbar"><div><div className="kicker">Production quality</div><h1>Quality Gate</h1><p className="sub">Deterministic media validation before publication.</p></div></div>{error&&<div className="error">{error}</div>}<div className="grid grid3">{rows.map(r=><div className="panel" key={r.id}><div className="cardTitle"><h2>{r.status}</h2><span className={`badge ${r.status==="FAIL"?"danger":r.status==="WARN"?"warn":"success"}`}>{r.score}</span></div><div className="mini">{r.width}×{r.height} · {r.duration_seconds.toFixed(1)}s</div>{r.issues?.length>0&&<div className="mini" style={{marginTop:10}}>{r.issues.join(" · ")}</div>}</div>)}</div>{rows.length===0&&<div className="panel empty">No quality reports yet. Run a workflow or a manual quality check.</div>}</Shell>;
}
