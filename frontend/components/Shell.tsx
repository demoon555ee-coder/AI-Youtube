"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { apiPost } from "../lib/api";

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

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  async function logout(){ try { await apiPost("/api/v1/auth/logout"); } finally { router.push("/login"); } }
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">YouTube <span>AI</span></div>
        <div className="workspace">AUTONOMOUS CONTENT OS</div>
        <nav className="nav">
          {links.map(([label, href]) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return <Link key={href} href={href} className={active ? "active" : ""}>{label}</Link>;
          })}
        </nav>
        <div className="sidebarFoot">
          <span className="dotLive" /> Secure workspace
          <button className="btn" style={{marginTop:10,width:"100%"}} onClick={()=>void logout()}>Sign out</button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
