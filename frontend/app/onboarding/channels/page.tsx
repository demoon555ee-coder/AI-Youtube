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
  const [showCreateYouTube, setShowCreateYouTube] = useState(false);

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
    setError("");
    setBusy(true);
    try {
      const r = await apiPost<{ authorization_url: string }>("/api/v1/auth/google/start");
      window.location.href = r.authorization_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to start Google authorization");
      setBusy(false);
    }
  }

  function openYouTubeCreator() {
    window.open("https://www.youtube.com/channel_switcher", "_blank", "noopener,noreferrer");
    setShowCreateYouTube(false);
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
      <div className="kicker">Your YouTube accounts</div>
      <h1>Choose the channel we will operate.</h1>
      <p className="sub">Google is connected. We loaded every YouTube channel available to this account. Pick one to make it the active AI workspace.</p>
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
            <div className="channelCardMeta"><span>{channel.youtube_channel_id ? <span className="channelConnected">Connected</span> : "Platform workspace"}</span><span>{selectedLabel}</span></div>
          </div>
        </button>;
      })}
      <button className="channelCreateCard" onClick={() => setShowCreateYouTube(true)}>
        <span className="channelCreatePlus">+</span>
        <strong>Create a new YouTube channel</strong>
        <span className="mini">Create the channel in YouTube, then bring it into this workspace.</span>
      </button>
      <button className="channelCreateCard" onClick={() => setCreateOpen(true)}>
        <span className="channelCreatePlus">✦</span>
        <strong>Create a separate AI workspace</strong>
        <span className="mini">Keep another channel's strategy, projects and governance separate.</span>
      </button>
    </section>
    <section className="channelSetupActions">
      <div className="channelSetupSecondary">
        <button className="btn" disabled={busy} onClick={() => void connectAnotherGoogleAccount()}>Change Google account</button>
        <span className="mini">The Google account chooser opens again, then we reload that account's YouTube channels.</span>
      </div>
      <button className="btn primary" disabled={!selected || busy} onClick={continueToStudio}>Continue to Dashboard →</button>
    </section>

    {showCreateYouTube && <div className="modalBackdrop" onClick={() => setShowCreateYouTube(false)}>
      <div className="modalCard" onClick={e => e.stopPropagation()}>
        <div className="cardTitle"><div><div className="kicker">New YouTube channel</div><h2>Create it in YouTube</h2></div><button className="btn" onClick={() => setShowCreateYouTube(false)}>Close</button></div>
        <p className="sub">YouTube creates the actual channel. We only manage the AI workspace and connect it after Google gives us access.</p>
        <div className="stack" style={{ marginTop: 18 }}>
          <div className="notice">1. Open YouTube's channel switcher and create the new channel. 2. Return here. 3. Choose <strong>Change Google account</strong> so we re-read the channels from Google.</div>
          <div className="actions">
            <button className="btn primary" onClick={openYouTubeCreator}>Open YouTube</button>
            <button className="btn" onClick={() => { setShowCreateYouTube(false); void connectAnotherGoogleAccount(); }}>Create and connect</button>
          </div>
        </div>
      </div>
    </div>}

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
