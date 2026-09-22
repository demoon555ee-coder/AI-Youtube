"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Shell from "../../components/Shell";
import { apiGet, apiPost, getStoredChannelId, storeChannelId } from "../../lib/api";

type Channel={id:string;name:string;niche?:string;language:string;timezone?:string;youtube_channel_id?:string|null};
function SettingsContent(){
  const search=useSearchParams();
  const [channels,setChannels]=useState<Channel[]>([]);const [selected,setSelected]=useState("");const [name,setName]=useState("My YouTube Channel");const [niche,setNiche]=useState("AI technology");const [language,setLanguage]=useState("en");const [status,setStatus]=useState<any>(null);const [timezone,setTimezone]=useState("UTC");const [message,setMessage]=useState("");
  async function load(){const r=await apiGet<{channels:Channel[]}>("/api/v1/channels");setChannels(r.channels);const id=search.get("channel_id")||getStoredChannelId()||r.channels[0]?.id||"";setSelected(id);if(id)storeChannelId(id);const selectedChannel=r.channels.find(c=>c.id===id);if(selectedChannel?.timezone)setTimezone(selectedChannel.timezone);if(id)await check(id)}
  useEffect(()=>{void load().catch(e=>setMessage(e instanceof Error?e.message:"Failed to load channels"));},[search]);
  useEffect(()=>{if(search.get("youtube")==="connected")setMessage("YouTube channel connected successfully.");if(search.get("youtube")==="error")setMessage(`YouTube connection failed: ${search.get("message")||"unknown error"}`);},[search]);
  async function check(id:string){try{setStatus(await apiGet(`/api/v1/youtube/channels/${id}/status`));}catch{setStatus({connected:false});}}
  async function create(){setMessage("");try{const r=await apiPost<Channel>("/api/v1/channels",{name,niche,language,timezone});storeChannelId(r.id);setSelected(r.id);await load();setMessage("Channel created.");}catch(e){setMessage(e instanceof Error?e.message:"Channel creation failed");}}
  async function connect(){try{const r=await apiPost<{authorization_url:string}>("/api/v1/youtube/oauth/start",{});window.location.href=r.authorization_url;}catch(e){setMessage(e instanceof Error?e.message:"OAuth start failed");}}
  return <Shell><div className="topbar"><div><div className="kicker">Workspace settings</div><h1>Settings</h1><p className="sub">Create/select a local channel workspace and connect YouTube via OAuth.</p></div></div>{message&&<div className="notice" style={{marginBottom:16}}>{message}</div>}<div className="grid grid2"><div className="panel"><h2>Channel workspace</h2><div className="formGrid"><div className="field"><label>Selected channel</label><select className="select" value={selected} onChange={e=>{setSelected(e.target.value);storeChannelId(e.target.value);void check(e.target.value)}}><option value="">Choose…</option>{channels.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div><div className="formRow"><div className="field"><label>Name</label><input className="input" value={name} onChange={e=>setName(e.target.value)}/></div><div className="field"><label>Language</label><input className="input" value={language} onChange={e=>setLanguage(e.target.value)}/></div></div><div className="field"><label>Niche</label><input className="input" value={niche} onChange={e=>setNiche(e.target.value)}/></div><div className="field"><label>Timezone</label><input className="input" value={timezone} onChange={e=>setTimezone(e.target.value)} placeholder="Europe/Brussels"/></div><button className="btn primary" onClick={()=>void create()}>Create channel workspace</button></div></div><div className="panel"><h2>YouTube connection</h2><p className="sub">OAuth credentials stay on the backend; the browser never receives refresh tokens.</p><div style={{marginTop:18}}>{status?.connected?<span className="badge success">Connected · {status.youtube_channel_id}</span>:<span className="badge warn">Not connected</span>}</div><div style={{marginTop:14}}><button className="btn primary" disabled={!selected} onClick={()=>void connect()}>Connect YouTube with Google</button></div><div className="mini" style={{marginTop:14}}>For local development, configure your Google OAuth client secret in <code>secrets/client_secret.json</code> and set the backend callback URL to the API public base URL.</div></div></div></Shell>
}

export default function SettingsPage(){
  return <Suspense fallback={null}><SettingsContent/></Suspense>;
}
