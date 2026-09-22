"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost } from "../../lib/api";

 type Version = { id:string; project_id:string; parent_project_id?:string|null; revision_number:number; trigger_type:string; reason:string; status:string; change_plan:Record<string,any>; metrics_snapshot:Record<string,any>; project_status?:string|null };
 type VersionsResponse = { content_root_id:string; versions:Version[] };

export default function EvolutionPage(){
  const [projectId,setProjectId]=useState("");
  const [rows,setRows]=useState<Version[]>([]);
  const [reason,setReason]=useState("Improve observed post-publish performance");
  const [metric,setMetric]=useState("retention");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  async function load(id:string){ if(!id) return; try{ const r=await apiGet<VersionsResponse>(`/api/v1/evolution/projects/${id}/versions`); setRows(r.versions); setError(""); }catch(e){setError(e instanceof Error?e.message:"Failed to load versions");} }
  useEffect(()=>{ const params=new URLSearchParams(window.location.search); const id=params.get("projectId")||""; setProjectId(id); if(id) void load(id); },[]);
  async function create(){ if(!projectId) return setError("Enter a project ID."); setBusy(true); try{ const r=await apiPost<{project_id:string}>(`/api/v1/evolution/projects/${projectId}/revisions`,{reason,trigger_type:"manual",metrics_snapshot:{metric},auto_run:true}); await load(r.project_id); setProjectId(r.project_id); setError(""); }catch(e){setError(e instanceof Error?e.message:"Revision failed");}finally{setBusy(false);} }
  return <Shell><div className="topbar"><div><div className="kicker">Content Evolution</div><h1>Versioned re-edit</h1><p className="sub">Create a new immutable revision without touching the published source.</p></div><Link className="btn" href="/projects">Back to Projects</Link></div>
    {error&&<div className="error" style={{marginBottom:16}}>{error}</div>}
    <div className="panel" style={{marginBottom:16}}><div className="grid grid2"><div><label className="label">Source project ID</label><input className="input" value={projectId} onChange={e=>setProjectId(e.target.value)} placeholder="UUID"/></div><div><label className="label">Primary issue</label><select className="select" value={metric} onChange={e=>setMetric(e.target.value)}><option value="retention">Retention</option><option value="ctr">CTR</option><option value="views">Views</option></select></div></div><label className="label" style={{display:"block",marginTop:14}}>Reason</label><textarea className="input" rows={3} value={reason} onChange={e=>setReason(e.target.value)} /><div className="actions" style={{marginTop:14}}><button className="btn" onClick={()=>void load(projectId)}>Load lineage</button><button className="btn primary" disabled={busy} onClick={()=>void create()}>{busy?"Creating…":"Create & run revision"}</button></div></div>
    <div className="panel"><div className="cardTitle"><div><h2>Revision lineage</h2><p className="sub">Each revision gets a unique project and preserved parent pointer.</p></div></div>{rows.length===0?<div className="empty">No version data loaded.</div>:rows.map(v=><div className="listItem" key={v.id}><div style={{display:"flex",justifyContent:"space-between",gap:12}}><strong>Revision {v.revision_number}</strong><span className={`badge ${v.status.includes("READY")?"success":v.status==="FAILED"?"danger":"warn"}`}>{v.status}</span></div><div className="mini" style={{marginTop:6}}>{v.trigger_type} · project {v.project_id}</div><div style={{marginTop:8}}>{v.reason}</div>{v.parent_project_id&&<div className="mini" style={{marginTop:5}}>Parent: {v.parent_project_id}</div>}</div>)}</div>
  </Shell>
}
