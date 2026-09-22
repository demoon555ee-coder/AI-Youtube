"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

export default function OptimizationPage() {
  const [channelId, setChannelId] = useState("");
  const [decisions, setDecisions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!channelId) return;
    setLoading(true);
    try {
      const data = await apiGet<{ decisions?: any[] }>(`/api/v1/optimization/channels/${channelId}/decisions`);
      setDecisions(data.decisions ?? []);
    } finally { setLoading(false); }
  }

  useEffect(() => { if (channelId) void load(); }, [channelId]);

  return (
    <main className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Autonomous Optimization</h1>
        <p className="text-sm text-slate-500">Performance signals → evidence → bounded next action.</p>
      </div>
      <div className="rounded-xl border p-4 space-y-3">
        <label className="text-sm font-medium">Channel ID</label>
        <div className="flex gap-2">
          <input className="w-full rounded border px-3 py-2" value={channelId} onChange={(e) => setChannelId(e.target.value)} placeholder="UUID" />
          <button className="rounded bg-black px-4 py-2 text-white" onClick={() => void load()} disabled={loading}>Refresh</button>
        </div>
      </div>
      <div className="rounded-xl border p-3 text-sm"><a className="underline" href="/execution">Open Autonomous Execution</a></div>
      <div className="grid gap-4">
        {decisions.map((d) => (
          <article key={d.id} className="rounded-xl border p-4">
            <div className="flex items-center justify-between">
              <span className="font-medium">{d.target_scope}</span>
              <span className="text-xs text-slate-500">{d.status}</span>
            </div>
            <p className="mt-2 text-sm">{d.hypothesis}</p>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div>Priority: <strong>{Number(d.priority ?? 0).toFixed(2)}</strong></div>
              <div>Confidence: <strong>{Number(d.confidence ?? 0).toFixed(2)}</strong></div>
            </div>
          </article>
        ))}
        {!decisions.length && <div className="rounded-xl border p-6 text-sm text-slate-500">No optimization decisions yet.</div>}
      </div>
    </main>
  );
}
