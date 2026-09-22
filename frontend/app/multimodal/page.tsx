"use client";
import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId } from "../../lib/api";

type Graph = { id:string; project_id:string; stage:string; status:string; score:number; risk_level:string; conflicts:any[]; recommendations:string[]; signals:Record<string,any>; created_at:string };
export default function MultimodalPage(){
  const [rows,setRows]=useState<Graph[]>([]); const [error,setError]=useState(""); const [busy,setBusy]=useState("");
  async function load(){
    const channel=getStoredChannelId(); if(!channel)return;
    try{
      const projects=await apiGet<{projects:any[]}>(`/api/v1/channels/${channel}/projects`);
      const out:Graph[]=[];
      for(const p of projects.projects.slice(0,20)){
        try{ const r=await apiGet<{graph:Graph|null}>(`/api/v1/multimodal/projects/${p.id}/latest`); if(r.graph) out.push(r.graph); }catch{}
      }
      setRows(out);
    }catch(e){setError(e instanceof Error?e.message:"Failed to load multimodal graphs")}
  }
  useEffect(()=>{void load()},[]);
  async function run(projectId:string, action:"preflight"|"analyze"){
    setBusy(`${projectId}:${action}`); setError("");
    try{ await apiPost(`/api/v1/multimodal/projects/${projectId}/${action}`); await load(); }
    catch(e){setError(e instanceof Error?e.message:"Multimodal analysis failed")}
    finally{setBusy("")}
  }
  return <Shell><div className="topbar"><div><div className="kicker">Production graph</div><h1>Multimodal Intelligence</h1><p className="sub">One graph connecting script, scenes, assets, audio, subtitles, timeline and visual analysis.</p></div></div>
    {error&&<div className="error">{error}</div>}
    <div className="grid grid3">{rows.map(r=><div className="panel" key={r.id}><div className="cardTitle"><h2>{r.stage}</h2><span className={`badge ${r.status==="FAIL"?"danger":r.status==="WARN"?"warn":"success"}`}>{r.score}</span></div><div className="mini">{r.project_id} · {r.risk_level}</div><div className="mini" style={{marginTop:10}}>Conflicts: {r.conflicts?.length||0} · Vision: {r.signals?.vision_mode||"pending"}</div><div className="mini" style={{marginTop:6}}>Scenes: {r.signals?.scene_count||0} · Assets: {r.signals?.asset_count||0}</div><div className="row" style={{marginTop:14,gap:8}}><button className="btn" disabled={!!busy} onClick={()=>void run(r.project_id,"preflight")}>{busy===`${r.project_id}:preflight`?"Running…":"Preflight"}</button><button className="btn" disabled={!!busy} onClick={()=>void run(r.project_id,"analyze")}>{busy===`${r.project_id}:analyze`?"Analyzing…":"Analyze"}</button></div></div>)}</div>
    {rows.length===0&&<div className="panel empty">No multimodal graphs yet. Create a video project and run its workflow.</div>}
  </Shell>
}
