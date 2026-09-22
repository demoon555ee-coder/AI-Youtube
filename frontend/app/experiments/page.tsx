"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, getStoredChannelId } from "../../lib/api";

type Experiment = { id:string; dimension:string; hypothesis:string; status:string; variants:Record<string,any>; result?:any };

export default function ExperimentsPage(){
  const [rows,setRows]=useState<Experiment[]>([]); const [error,setError]=useState("");
  async function load(){const id=getStoredChannelId(); if(!id)return; try{setRows((await apiGet<{experiments:Experiment[]}>(`/api/v1/experiments/channels/${id}`)).experiments);setError("");}catch(e){setError(e instanceof Error?e.message:"Failed to load experiments");}}
  useEffect(()=>{void load();},[]);
  return <Shell><div className="topbar"><div><div className="kicker">Optimization lab</div><h1>Experiments</h1><p className="sub">Track observational tests for titles, thumbnails, hooks, pacing and topic angles.</p></div></div>{error&&<div className="error" style={{marginBottom:16}}>{error}</div>}<div className="panel"><table className="table"><thead><tr><th>Dimension</th><th>Hypothesis</th><th>Status</th><th>Primary result</th></tr></thead><tbody>{rows.map(x=><tr key={x.id}><td><strong>{x.dimension}</strong><br/><span className="mini">{x.id}</span></td><td>{x.hypothesis||"—"}</td><td><span className={`badge ${x.status==="COMPLETED"?"success":"warn"}`}>{x.status}</span></td><td>{x.result?.decision?.state ? `${x.result.decision.state}${x.result.decision.leading_variant?` · ${x.result.decision.leading_variant}`:""}` : "Collect observations"}</td></tr>)}</tbody></table>{rows.length===0&&<div className="empty">No experiments yet. Create one from an optimization report through the API.</div>}</div></Shell>
}
