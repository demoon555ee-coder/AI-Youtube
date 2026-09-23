"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiGet, apiPost, getStoredChannelId, storeChannelId } from "../../../lib/api";

type Channel = {
  id: string;
  name: string;
  niche?: string;
  language: string;
  youtube_channel_id?: string | null;
  thumbnail_url?: string | null;
};

function ChannelOnboardingContent() {
  const router = useRouter();
  const search = useSearchParams();
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("My YouTube Workspace");
  const [newNiche, setNewNiche] = useState("AI technology");

  async function load() {
    try {
      setLoading(true);
      const result = await apiGet<{ channels: Channel[] }>("/api/v1/channels");
      setChannels(result.channels);
      const stored = getStoredChannelId();
      const preferred = stored && result.channels.some(c => c.id === stored) ? stored : result.channels[0]?.id || "";
      setSelected(preferred);
      if (preferred) storeChannelId(preferred);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load channels");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  function choose(id: string) {
    setSelected(id);
    storeChannelId(id);
  }

  function continueToStudio() {
    if (!selected) return;
    setBusy(true);
    storeChannelId(selected);
    router.push("/");
  }

  async function connectAnotherGoogleAccount() {
    setBusy(true);
    try {
      const r = await apiPost<{ authorization_url: string }>("/api/v1/auth/google/start");
      window.location.href = r.authorization_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to start Google authorization");
      setBusy(false);
    }
  }
  async function createWorkspace() {
    setError("");
    setBusy(true);
    try {
      const channel = await apiPost<Channel>("/api/v1/channels", {
        name: newName.trim(),
        niche: newNiche.trim(),
        language: "en",
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      });
      storeChannelId(channel.id);
      await load();
      setSelected(channel.id);
      setCreateOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create workspace");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <main className="authPage"><div className="authCard"><div className="kicker">Workspace setup</div><h1>Loading your channels…</h1><p className="sub">Preparing the YouTube accounts available to this Google identity.</p></div></main>;
  }

  return <main className="channelSetup">
    <section className="channelSetupHero">
      <div className="authBrand"><span className="authBrandMark" /><span>YouTube AI</span></div>
      <div className="kicker">Choose your workspace</div>
      <h1>Which channel are we working on?</h1>
      <p className="sub">Your Google authorization is complete. Choose the YouTube channel the AI team should use as its current workspace.</p>
      {search.get("google") === "connected" && <div className="notice" style={{ marginTop: 18 }}>Google connected. We found {channels.length} available channel{channels.length === 1 ? "" : "s"}.</div>}
      {error && <div className="error" style={{ marginTop: 18 }}>{error}</div>}
    </section>

    <section className="channelGrid">
      {channels.map(channel => {
        const selectedLabel = selected === channel.id ? "Selected" : "Choose";
        const youtubeId = channel.youtube_channel_id ? " · " + channel.youtube_channel_id : "";
        return <button key={channel.id} className={selected === channel.id ? "channelCard selected" : "channelCard"} onClick={() => choose(channel.id)}>
          <div className="channelThumb">{channel.thumbnail_url ? <img src={channel.thumbnail_url} alt="" /> : <span>{channel.name.slice(0, 1).toUpperCase()}</span>}</div>
          <div className="channelCardBody">
            <div className="channelCardTitle">{channel.name}</div>
            <div className="mini">{channel.niche || "YouTube channel"}{youtubeId}</div>
            <div className="channelCardMeta"><span>{channel.youtube_channel_id ? "Connected to YouTube" : "Platform workspace"}</span><span>{selectedLabel}</span></div>
          </div>
        </button>;
      })}
      <button className="channelCreateCard" onClick={() => setCreateOpen(true)}>
        <span className="channelCreatePlus">+</span>
        <strong>Create a new workspace</strong>
        <span className="mini">A separate AI operating workspace for a channel</span>
      </button>
      <a className="channelCreateCard" href="https://www.youtube.com/channel_switcher" target="_blank" rel="noreferrer">
        <span className="channelCreatePlus">↗</span>
        <strong>Create a new YouTube channel</strong>
        <span className="mini">Open YouTube and create the channel, then connect it here</span>
      </a>
    </section>
    <section className="channelSetupActions">
      <div className="channelSetupSecondary">
        <button className="btn" disabled={busy} onClick={() => void connectAnotherGoogleAccount()}>Connect another Google account</button>
        <span className="mini">Google's account chooser lets you switch accounts without signing out.</span>
      </div>
      <button className="btn primary" disabled={!selected || busy} onClick={continueToStudio}>Continue to Dashboard →</button>
    </section>

    {createOpen && <div className="modalBackdrop" onClick={() => setCreateOpen(false)}>
      <div className="modalCard" onClick={e => e.stopPropagation()}>
        <div className="cardTitle"><div><div className="kicker">New workspace</div><h2>Create a channel workspace</h2></div><button className="btn" onClick={() => setCreateOpen(false)}>Close</button></div>
        <p className="sub">This creates a workspace inside the platform. Creating a brand-new YouTube channel itself remains a Google/YouTube action.</p>
        <div className="stack" style={{ marginTop: 18 }}>
          <div className="field"><label htmlFor="workspace-name">Workspace name</label><input id="workspace-name" className="input" value={newName} onChange={e => setNewName(e.target.value)} /></div>
          <div className="field"><label htmlFor="workspace-niche">Niche</label><input id="workspace-niche" className="input" value={newNiche} onChange={e => setNewNiche(e.target.value)} /></div>
          <button className="btn primary" disabled={!newName.trim() || busy} onClick={() => void createWorkspace()}>Create workspace</button>
        </div>
      </div>
    </div>}
  </main>;
}

export default function ChannelOnboardingPage() {
  return <Suspense fallback={<main className="authPage"><div className="authCard"><div className="kicker">Workspace setup</div><h1>Preparing your channels…</h1></div></main>}><ChannelOnboardingContent /></Suspense>;
}
