"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, getStoredChannelId } from "../../lib/api";

type Project = { id: string; topic: string; status: string; data: Record<string, any> };
export default function ProjectsPage() {
  const [rows, setRows] = useState<Project[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { const id = getStoredChannelId(); if (!id) return; void apiGet<{projects:Project[]}>(`/api/v1/channels/${id}/projects`).then(r=>setRows(r.projects)).catch(e=>setError(e instanceof Error?e.message:"Failed to load projects")); }, []);
  return <Shell><div className="topbar"><div><div className="kicker">Production workspace</div><h1>Projects</h1><p className="sub">Every video is an auditable AI workflow with agent history and media artifacts.</p></div><Link href="/ideas" className="btn primary">Create from idea</Link></div>{error && <div className="error" style={{marginBottom:16}}>{error}</div>}<div className="panel"><table className="table"><thead><tr><th>Project</th><th>Status</th><th>Title</th><th></th></tr></thead><tbody>{rows.map(p=><tr key={p.id}><td><strong>{p.topic}</strong><br/><span className="mini">{p.id}</span></td><td><span className={`badge ${p.status === "FAILED" ? "danger" : p.status === "READY_TO_PUBLISH" || p.status === "PUBLISHED" ? "success" : "warn"}`}>{p.status}</span></td><td>{p.data?.script?.title || p.data?.title || "—"}</td><td><Link className="btn" href={`/projects/${p.id}`}>Open</Link></td></tr>)}</tbody></table>{rows.length === 0 && <div className="empty">No projects for the selected channel.</div>}</div></Shell>;
}
