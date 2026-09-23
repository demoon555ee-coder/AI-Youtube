"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId, storeChannelId } from "../../lib/api";

type Idea = {
  id: string; title: string; topic: string; hook: string; angle: string;
  composite_score: number; status: string; selected: boolean;
};
type IdeasResponse = { ideas: Idea[] };
type Channels = { channels: { id: string; name: string; niche?: string; language: string }[] };

const tones = ["persimmon", "blue", "jade", "wasabi", "plum"] as const;

export default function IdeasPage() {
  const [channelId, setChannelId] = useState<string | null>(null);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [seed, setSeed] = useState("");
  const [goal, setGoal] = useState("growth");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function loadIdeas(id: string) {
    setIdeas((await apiGet<IdeasResponse>(`/api/v1/content/channels/${id}/ideas`)).ideas);
  }
  async function init() {
    const list = await apiGet<Channels>("/api/v1/channels");
    const id = getStoredChannelId() || list.channels[0]?.id;
    if (id) { storeChannelId(id); setChannelId(id); await loadIdeas(id); }
  }
  useEffect(() => {
    void init().catch(e => setMessage(e instanceof Error ? e.message : "Failed to load ideas"));
  }, []);

  async function generate() {
    if (!channelId) return setMessage("Choose or create a channel first.");
    setBusy(true); setMessage("");
    try {
      await apiPost(`/api/v1/content/channels/${channelId}/generate-ideas`,
        { seed_topics: seed ? [seed] : [], count: 12, goal });
      await loadIdeas(channelId);
      setSeed(""); setMessage("12 new ideas generated using Channel Brain context.");
    } catch (e) { setMessage(e instanceof Error ? e.message : "Generation failed"); }
    finally { setBusy(false); }
  }

  async function selectAndCreate(id: string) {
    if (!channelId) return;
    setBusy(true); setMessage("");
    try {
      await apiPost(`/api/v1/content/channels/${channelId}/ideas/${id}/select`);
      const project = await apiPost<{project_id: string}>(
        `/api/v1/content/channels/${channelId}/ideas/${id}/create-project`);
      window.location.href = `/projects/${project.project_id}`;
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not create project");
      setBusy(false);
    }
  }

  const filteredIdeas = useMemo(() => {
    const value = query.trim().toLowerCase();
    return value ? ideas.filter(i => [i.title, i.topic, i.hook, i.angle]
      .some(text => text.toLowerCase().includes(value))) : ideas;
  }, [ideas, query]);

  return (
    <Shell>
      <div className="topbar">
        <div>
          <div className="kicker">Content factory</div>
          <h1>Ideas</h1>
          <p className="sub">A visual board for turning channel intelligence into production-ready concepts.</p>
        </div>
        <div className="actions">
          <Link href="/research" className="btn">Research</Link>
          <button className="btn primary" disabled={busy || !channelId}
            onClick={() => void generate()}>Generate ideas</button>
        </div>
      </div>
      <div className="discoveryBar">
        <input className="discoverySearch" value={query} onChange={e => setQuery(e.target.value)}
          placeholder="Search ideas, hooks, topics…" aria-label="Search ideas" />
        <select className="select" style={{width:180}} value={goal} onChange={e => setGoal(e.target.value)}>
          <option value="growth">Growth</option><option value="authority">Authority</option>
          <option value="monetization">Monetization</option><option value="balanced">Balanced</option>
        </select>
      </div>
      {message && <div className="notice" style={{marginBottom:16}}>{message}</div>}

      <div className="panel" style={{marginBottom:18}}>
        <div className="cardTitle">
          <div><h2>Generate a new batch</h2><p className="sub">Optional seed + strategy goal. The Channel Brain supplies the context.</p></div>
          <span className="badge">{filteredIdeas.length} ideas</span>
        </div>
        <div className="formRow">
          <div className="field"><label htmlFor="idea-seed">Topic seed</label>
            <input id="idea-seed" className="input" value={seed} onChange={e => setSeed(e.target.value)}
              placeholder="e.g. AI agents in 2027" /></div>
          <div className="field"><label>Strategy goal</label>
            <div className="mini" style={{paddingTop:11}}>Generate with <strong>{goal}</strong> as the optimization target.</div></div>
        </div>
        <div style={{marginTop:12}}><button className="btn primary" disabled={busy || !channelId}
          onClick={() => void generate()}>{busy ? "Working…" : "Generate 12 ideas"}</button></div>
      </div>

      {filteredIdeas.length === 0 ? (
        <div className="panel empty">No matching ideas yet. Generate the first batch.</div>
      ) : (
        <div className="pinBoard">
          {filteredIdeas.map((idea, index) => (
            <article className="pinCard" key={idea.id}>
              <div className={`pinMedia ${tones[index % tones.length]}`}>
                <div style={{width:"100%"}}>
                  <span className="badge" style={{background:"rgba(255,255,255,.72)"}}>
                    {idea.status || "New"}
                  </span>
                  <div style={{fontSize:index % 3 === 0 ? 25 : 21,fontWeight:850,letterSpacing:"-.03em",marginTop:12}}>
                    {idea.topic || "Content idea"}
                  </div>
                </div>
              </div>
              <div className="pinBody">
                <strong>{idea.title}</strong>
                <p>{idea.hook}</p>
                <div className="ideaPinMeta">
                  <span>{idea.angle || "Original angle"}</span>
                  <span>AI score <b>{Math.round(idea.composite_score * 100)}</b></span>
                </div>
                <div className="ideaPinActions">
                  <Link href={`/research?idea=${idea.id}`} className="btn">Research</Link>
                  <button className="btn primary" disabled={busy}
                    onClick={() => void selectAndCreate(idea.id)}>Create project →</button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </Shell>
  );
}
