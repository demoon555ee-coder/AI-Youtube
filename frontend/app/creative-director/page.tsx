"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId } from "../../lib/api";

type Analysis = { id: string; project_id: string; score: number; status: string; created_at?: string };
type Plan = { id: string; project_id: string; status: string; max_changes: number; score: number; plan: any; execution: any };

export default function CreativeDirectorPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [selected, setSelected] = useState("");
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const channel = getStoredChannelId();
    if (!channel) return;
    void apiGet<{ projects: any[] }>(`/api/v1/channels/${channel}/projects`).then(r => setProjects(r.projects)).catch(e => setError(e instanceof Error ? e.message : "Failed to load projects"));
  }, []);

  async function selectProject(projectId: string) {
    setSelected(projectId); setError("");
    if (!projectId) return;
    try {
      const [a, p] = await Promise.all([
        apiGet<{ analyses: Analysis[] }>(`/api/v1/creative/projects/${projectId}/analyses`),
        apiGet<{ plans: Plan[] }>(`/api/v1/creative/projects/${projectId}/director-plans`),
      ]);
      setAnalyses(a.analyses); setPlans(p.plans);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load creative intelligence"); }
  }

  async function buildPlan() {
    if (!selected) return;
    setLoading(true); setError("");
    try {
      const result = await apiPost<Plan>(`/api/v1/creative/projects/${selected}/director-plan`, { analysis_id: analyses[0]?.id ?? null, max_changes: 3 });
      setPlans(prev => [result, ...prev]);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to create director plan"); }
    finally { setLoading(false); }
  }

  return <Shell><div className="topbar"><div><div className="kicker">Creative direction</div><h1>Autonomous Creative Director</h1><p className="sub">Turn scene evidence into bounded, explainable edit actions without rewriting the source video.</p></div></div>{error && <div className="error" style={{marginBottom:16}}>{error}</div>}<div className="panel" style={{marginBottom:16}}><label className="field"><span>Project</span><select value={selected} onChange={e=>void selectProject(e.target.value)}><option value="">Select a project</option>{projects.map(p=><option key={p.id} value={p.id}>{p.topic || p.id} — {p.status}</option>)}</select></label><button className="btn primary" disabled={!selected || loading || analyses.length===0} onClick={()=>void buildPlan()}>{loading ? "Building…" : "Build director plan"}</button></div>{selected && <div className="grid2"><div className="panel"><h2>Latest creative analysis</h2>{analyses[0] ? <div><div className="metric"><strong>{analyses[0].score}</strong><span>{analyses[0].status}</span></div><p className="mini">Analysis {analyses[0].id}</p></div> : <div className="empty">Run Creative Intelligence first.</div>}</div><div className="panel"><h2>Director plans</h2>{plans.length===0 && <div className="empty">No plans yet.</div>}{plans.map(p=><div key={p.id} className="card" style={{marginTop:10}}><div><strong>{p.status}</strong> · {p.plan?.changes?.length ?? 0} changes</div><div className="mini">automatic: {p.execution?.automatic ?? 0} · manual: {p.execution?.manual_review ?? 0}</div>{p.plan?.changes?.map((c:any)=><div key={`${p.id}-${c.scene}`} className="mini" style={{marginTop:6}}>Scene {c.scene}: {c.action} · priority {c.priority}</div>)}</div>)}</div></div>}</Shell>;
}
