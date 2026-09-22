"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import Shell from "../../../components/Shell";
import { API_BASE, apiGet, apiPost, getStoredChannelId } from "../../../lib/api";

type Run = { id:string; agent_name:string; status:string; error_message?:string|null };
type Project = { id:string; topic:string; status:string; data:Record<string,any>; agent_runs:Run[]; publications:any[]; workflows?: {id:string;status:string;current_step?:string|null}[] };
const statusToStep: Record<string, number> = { QUEUED:0, RESEARCHING:0, SCRIPTING:1, STORYBOARDING:2, DIRECTING_SCENES:3, GENERATING_ASSETS:4, EDITING:5, GENERATING_THUMBNAIL:6, QA:6, READY_TO_PUBLISH:7, PUBLISHED:7 };

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [project,setProject]=useState<Project|null>(null); const [error,setError]=useState(""); const [busy,setBusy]=useState(false); const [privacy,setPrivacy]=useState("private");
  const title = useMemo(()=>project?.data?.script?.title || project?.data?.title || project?.topic || "",[project]);
  async function load(){ try{ setProject(await apiGet<Project>(`/api/v1/projects/${id}`)); setError(""); }catch(e){setError(e instanceof Error?e.message:"Failed to load project");} }
  useEffect(()=>{
    void load();
    const timer=setInterval(()=>{void load()},5000);
    const workflowId = project?.workflows?.[0]?.id;
    if (!workflowId || typeof window === "undefined" || !("EventSource" in window)) {
      return ()=>clearInterval(timer);
    }
    const source = new EventSource(`${API_BASE}/api/v1/workflows/${workflowId}/events`, {withCredentials:true});
    source.onmessage = () => { void load(); };
    source.addEventListener("workflow.closed", () => { void load(); source.close(); });
    source.onerror = () => { source.close(); };
    return ()=>{ clearInterval(timer); source.close(); };
  },[id, project?.workflows?.[0]?.id]);
  async function run(){setBusy(true);try{await apiPost(`/api/v1/projects/${id}/run`);await load();}catch(e){setError(e instanceof Error?e.message:"Workflow failed");}finally{setBusy(false);}}
  async function retry(){setBusy(true);try{await apiPost(`/api/v1/projects/${id}/retry`);await load();}catch(e){setError(e instanceof Error?e.message:"Retry failed");}finally{setBusy(false);}}
  async function publish(){const channelId=getStoredChannelId();if(!channelId)return setError("Select a channel first.");setBusy(true);try{await apiPost(`/api/v1/youtube/channels/${channelId}/publish`,{project_id:id,title,privacy_status:privacy});await load();}catch(e){setError(e instanceof Error?e.message:"YouTube publish failed");}finally{setBusy(false);}}
  async function cancel(){const workflowId=project?.workflows?.[0]?.id;if(!workflowId)return;setBusy(true);try{await apiPost(`/api/v1/workflows/${workflowId}/cancel`);await load();}catch(e){setError(e instanceof Error?e.message:"Cancellation failed");}finally{setBusy(false);}}
  if(error && !project) return <Shell><div className="error">{error}</div></Shell>;
  if(!project) return <Shell><div className="panel empty">Loading project…</div></Shell>;
  const step=statusToStep[project.status] ?? -1;
  const video=`${API_BASE}/api/v1/projects/${id}/video`; const thumb=`${API_BASE}/api/v1/projects/${id}/thumbnail`;
  return <Shell><div className="topbar"><div><div className="kicker">Video project</div><h1>{title}</h1><p className="sub">{project.topic}</p></div><div className="actions"><Link className="btn" href={`/evolution?projectId=${id}`}>Evolution</Link>{project.status === "FAILED" && <button className="btn" disabled={busy} onClick={()=>void retry()}>Retry workflow</button>}{project.status === "IDEA" && <button className="btn primary" disabled={busy} onClick={()=>void run()}>{busy?"Starting…":"Run AI workflow"}</button>}{["QUEUED","RESEARCHING","SCRIPTING","STORYBOARDING","DIRECTING_SCENES","GENERATING_ASSETS","EDITING","GENERATING_THUMBNAIL","QA"].includes(project.status) && <button className="btn" disabled={busy} onClick={()=>void cancel()}>Cancel workflow</button>}{project.status === "READY_TO_PUBLISH" && <><select className="select" style={{width:150}} value={privacy} onChange={e=>setPrivacy(e.target.value)}><option value="private">Private</option><option value="unlisted">Unlisted</option><option value="public">Public</option></select><button className="btn primary" disabled={busy} onClick={()=>void publish()}>{busy?"Publishing…":"Publish to YouTube"}</button></>}</div></div>{error && <div className="error" style={{marginBottom:16}}>{error}</div>}
    <div className="panel" style={{marginBottom:16}}><div className="cardTitle"><div><h2>Workflow</h2><p className="sub">Agent execution is persisted and can be inspected.</p></div><span className={`badge ${project.status === "FAILED"?"danger":project.status === "PUBLISHED"?"success":"warn"}`}>{project.status}</span></div><div className="pipeline">{["Research","Script","Storyboard","Scene Director","Production","Editor","QA","Publish"].map((name,i)=><div key={name} className={`step ${i<step?"done":""} ${i===step?"active":""}`}><div className="dot"/><div className="name">{name}</div></div>)}</div></div>
    <div className="grid grid2"><div className="panel"><h2>Video preview</h2>{project.data?.editor?.output_path?<div className="videoBox"><video controls src={video}/></div>:<div className="empty">The renderer has not produced a video yet.</div>}</div><div className="panel"><h2>Thumbnail</h2>{project.data?.thumbnail?.path || (project.status === "READY_TO_PUBLISH" && project.data?.editor?.output_path)?<div className="thumbBox"><img src={thumb} alt="Generated thumbnail"/></div>:<div className="empty">Thumbnail will appear after production.</div>}</div></div>
    <div className="panel" style={{marginTop:16}}><h2>Agent activity</h2>{project.agent_runs.length===0?<div className="empty">No agent runs yet.</div>:project.agent_runs.map(r=><div className="listItem" key={r.id}><div style={{display:"flex",justifyContent:"space-between",gap:10}}><strong>{r.agent_name}</strong><span className={`badge ${r.status === "FAILED"?"danger":r.status === "COMPLETED"?"success":"warn"}`}>{r.status}</span></div>{r.error_message&&<div className="mini" style={{marginTop:6}}>{r.error_message}</div>}</div>)}</div>
    {project.publications.length>0&&<div className="panel" style={{marginTop:16}}><h2>Publication</h2>{project.publications.map((p:any)=><div className="listItem" key={p.id}><strong>{p.title}</strong><div className="mini">{p.status} · {p.visibility}{p.youtube_video_id?` · ${p.youtube_video_id}`:""}</div></div>)}</div>}
  </Shell>;
}
