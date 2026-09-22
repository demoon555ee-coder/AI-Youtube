"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { apiGet } from "../../lib/api";

type RoutingDecision = { id:string; step_name:string; service:string; requested_tier:string; chosen_provider:string; chosen_tier:string; fallback_used:boolean; estimated_cost_usd:number; created_at:string };
type ProviderProfile = { id:string; provider:string; service:string; kind:string; quality_tier:string; priority:number; unit_cost_usd:number; enabled:boolean };
type Portfolio = {
  portfolio: { id: string; name: string; monthly_budget_usd: number; daily_budget_usd: number; currency: string };
  spend: { monthly: { state: string; spent_usd: number; limit_usd: number; utilization_pct: number; remaining_usd: number | null }; daily: { state: string; spent_usd: number; limit_usd: number; utilization_pct: number } };
  channels: { id: string; name: string; youtube_channel_id?: string | null; budget_weight: number; monthly_budget_usd: number; monthly_spend_usd: number }[];
  providers: { provider: string; service: string; monthly: { state: string; spent_usd: number; limit_usd: number; utilization_pct: number }; daily: { state: string; spent_usd: number; limit_usd: number; utilization_pct: number }; hard_limit: boolean }[];
  top_projects_by_cost: { project_id: string; monthly_cost_usd: number }[];
};

const money = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);

export default function PortfolioPage() {
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState("");
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [decisions, setDecisions] = useState<RoutingDecision[]>([]);
  useEffect(() => {
    void Promise.all([
      apiGet<Portfolio>("/api/v1/portfolio/overview"),
      apiGet<{profiles:ProviderProfile[]}>("/api/v1/routing/providers"),
      apiGet<{decisions:RoutingDecision[]}>("/api/v1/routing/decisions?limit=12")
    ]).then(([portfolio, profileRows, decisionRows]) => { setData(portfolio); setProfiles(profileRows.profiles); setDecisions(decisionRows.decisions); }).catch(e => setError(e instanceof Error ? e.message : "Unable to load portfolio"));
  }, []);
  return <Shell>
    <div className="topbar"><div><div className="kicker">Portfolio Brain</div><h1>{data?.portfolio.name || "Portfolio"}</h1><p className="sub">One control plane for multiple channels, providers and production costs.</p></div></div>
    {error && <div className="error">{error}</div>}
    {!data && !error && <div className="panel empty">Loading Portfolio Brain…</div>}
    {data && <>
      <div className="grid grid4" style={{marginBottom:16}}>
        <div className="panel metric"><span className="label">Monthly spend</span><span className="value">{money(data.spend.monthly.spent_usd)}</span><span className="badge">{data.spend.monthly.state}</span></div>
        <div className="panel metric"><span className="label">Monthly budget</span><span className="value">{money(data.portfolio.monthly_budget_usd)}</span><span className="badge">{data.spend.monthly.limit_usd ? `${data.spend.monthly.utilization_pct}% used` : "Unlimited"}</span></div>
        <div className="panel metric"><span className="label">Daily spend</span><span className="value">{money(data.spend.daily.spent_usd)}</span><span className="badge">{data.spend.daily.state}</span></div>
        <div className="panel metric"><span className="label">Channels</span><span className="value">{data.channels.length}</span><span className="badge success">Portfolio managed</span></div>
      </div>
      <div className="grid grid2">
        <div className="panel"><div className="cardTitle"><h2>Channels</h2></div>{data.channels.length === 0 ? <div className="empty">No channels linked yet.</div> : data.channels.map(c => <div className="idea" key={c.id}><div className="ideaText"><strong>{c.name}</strong><small>{money(c.monthly_spend_usd)} this month · weight {c.budget_weight}</small></div><span className="badge">{c.youtube_channel_id ? "YouTube connected" : "Not connected"}</span></div>)}</div>
        <div className="panel"><div className="cardTitle"><h2>Provider budgets</h2></div>{data.providers.length === 0 ? <div className="empty">No provider budgets configured.</div> : data.providers.map(p => <div className="idea" key={`${p.provider}:${p.service}`}><div className="ideaText"><strong>{p.provider} / {p.service}</strong><small>{money(p.monthly.spent_usd)} / {money(p.monthly.limit_usd)} monthly</small></div><span className={`badge ${p.monthly.state === "BLOCKED" ? "danger" : p.monthly.state === "WARNING" ? "warn" : "success"}`}>{p.monthly.state}</span></div>)}</div>
      </div>
      <div className="grid grid2" style={{marginTop:16}}>
        <div className="panel"><div className="cardTitle"><h2>Provider router</h2><span className="badge success">{profiles.length} configured</span></div>{profiles.length === 0 ? <div className="empty">No custom provider profiles. The built-in provider catalog will be used.</div> : profiles.map(p => <div className="idea" key={p.id}><div className="ideaText"><strong>{p.provider}</strong><small>{p.service} · {p.quality_tier} · priority {p.priority} · {money(p.unit_cost_usd)}/unit</small></div><span className={`badge ${p.enabled ? "success" : ""}`}>{p.enabled ? "Enabled" : "Disabled"}</span></div>)}</div>
        <div className="panel"><div className="cardTitle"><h2>Recent routing decisions</h2></div>{decisions.length === 0 ? <div className="empty">No routing decisions yet. Start a workflow to populate the audit trail.</div> : decisions.map(d => <div className="idea" key={d.id}><div className="ideaText"><strong>{d.step_name} → {d.chosen_provider}</strong><small>{d.service} · requested {d.requested_tier} · estimated {money(d.estimated_cost_usd)}</small></div><span className={`badge ${d.fallback_used ? "warn" : "success"}`}>{d.fallback_used ? "Fallback" : d.chosen_tier}</span></div>)}</div>
      </div>
    </>}
  </Shell>;
}
