"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiGet, apiPost, getStoredChannelId, storeChannelId } from "../lib/api";
import { LanguageSwitcher, LocalizedContent, useLocale } from "./Locale";

const links = [
  ["Dashboard", "/"],
  ["Ideas", "/ideas"],
  ["Autopilot", "/autopilot"],
  ["Projects", "/projects"],
  ["Channel Brain", "/brain"],
  ["Intelligence", "/intelligence"],
  ["Portfolio", "/portfolio"],
  ["Portfolio Manager", "/manager"],
  ["Provider Routing", "/routing"],
  ["Analytics", "/analytics"],
  ["Experiments", "/experiments"],
  ["Research", "/research"],
  ["Research Scheduler", "/research-scheduler"],
  ["Trend Intelligence", "/trends"],
  ["Opportunity Intelligence", "/opportunity-intelligence"],
  ["Quality Gate", "/quality"],
  ["Post-Publish", "/post-publish"],
  ["Content Evolution", "/evolution"],
  ["Creative Intelligence", "/creative"],
  ["Creative Director", "/creative-director"],
  ["Autonomous Optimization", "/optimization"],
  ["Billing & Usage", "/billing"],
  ["Privacy Center", "/privacy"],
  ["Settings", "/settings"],
] as const;

type ShellChannel = { id: string; name: string; youtube_channel_id?: string | null };

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useLocale();
  const [channels, setChannels] = useState<ShellChannel[]>([]);
  const [activeChannel, setActiveChannel] = useState<ShellChannel | null>(null);

  useEffect(() => {
    void apiGet<{ channels: ShellChannel[] }>("/api/v1/channels").then(result => {
      setChannels(result.channels);
      const stored = getStoredChannelId();
      const chosen = result.channels.find(channel => channel.id === stored) || result.channels[0] || null;
      setActiveChannel(chosen);
      if (chosen) storeChannelId(chosen.id);
    }).catch(() => undefined);
  }, [pathname]);

  async function logout(){ try { await apiPost("/api/v1/auth/logout"); } finally { window.localStorage.removeItem("youtube_ai_channel_id"); router.push("/login"); } }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">YouTube <span>AI</span></div>
        <div className="workspace">{t("AUTONOMOUS CONTENT OS")}</div>
        <LanguageSwitcher className="shellLanguage" />
        <Link href="/onboarding/channels" className="accountPicker" title={t("Change YouTube account or channel")}>
          <span className="accountAvatar">{activeChannel?.name?.slice(0, 1).toUpperCase() || "Y"}</span>
          <span style={{minWidth:0,flex:1}}>
            <strong style={{display:"block",fontSize:12,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{activeChannel?.name || t("Choose channel")}</strong>
            <span className="mini">{channels.length > 1 ? `${channels.length} ${t("channels connected")}` : t("YouTube workspace")}</span>
          </span>
          <span aria-hidden="true">⌄</span>
        </Link>
        <div style={{height:14}} />
        <nav className="nav">
          {links.map(([label, href]) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return <Link key={href} href={href} className={active ? "active" : ""}>{t(label)}</Link>;
          })}
        </nav>
        <div className="sidebarFoot">
          <span className="dotLive" /> {t("Secure workspace")}
          <button className="btn" style={{marginTop:10,width:"100%"}} onClick={()=>void logout()}>{t("Sign out")}</button>
        </div>
      </aside>
      <main className="main"><LocalizedContent>{children}</LocalizedContent></main>
    </div>
  );
}
