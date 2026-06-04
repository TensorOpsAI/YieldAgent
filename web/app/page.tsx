"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  deleteCampaign,
  fetchCampaigns,
  fetchSummary,
  type CampaignRow,
  type Summary,
} from "@/lib/api";

function facetChips(targeting: Record<string, string[]>): string[] {
  return Object.values(targeting ?? {})
    .flat()
    .slice(0, 4);
}

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignRow[]>([]);
  const [removing, setRemoving] = useState<string | null>(null);

  useEffect(() => {
    fetchSummary().then(setSummary).catch(() => undefined);
    fetchCampaigns().then(setCampaigns).catch(() => undefined);
  }, []);

  async function remove(id: string) {
    if (removing) return;
    setRemoving(id);
    const wasDraft = campaigns.find((c) => c.id === id)?.status === "DRAFT";
    try {
      await deleteCampaign(id);
      setCampaigns((prev) => prev.filter((c) => c.id !== id));
      setSummary((prev) =>
        prev
          ? {
              campaigns: Math.max(0, prev.campaigns - 1),
              drafts: Math.max(0, prev.drafts - (wasDraft ? 1 : 0)),
            }
          : prev,
      );
    } catch {
      // leave the row in place if the delete failed
    } finally {
      setRemoving(null);
    }
  }

  const stats = [
    { label: "Tracked spend", value: "—", hint: "n/a for drafts" },
    { label: "Draft campaigns", value: String(summary?.drafts ?? 0) },
    { label: "Pending approvals", value: "0" },
    { label: "Campaigns created", value: String(summary?.campaigns ?? 0) },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-7 px-7 py-8">
      <div>
        <span className="eyebrow">Overview</span>
        <h1 className="mt-1 font-display text-3xl text-ink">Good to see you.</h1>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((s, i) => (
          <div
            key={s.label}
            className="rise rounded-xl border border-line bg-surface p-4"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className="text-[13px] text-muted">{s.label}</div>
            <div className="nums mt-2 text-3xl font-medium text-ink">{s.value}</div>
            {s.hint && <div className="mt-1 text-[12px] text-faint">{s.hint}</div>}
          </div>
        ))}
      </div>

      <div
        className="rise overflow-hidden rounded-2xl border border-line bg-surface"
        style={{ animationDelay: "240ms" }}
      >
        <div className="relative p-7">
          <div
            className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full opacity-[0.07]"
            style={{ background: "radial-gradient(circle, var(--color-brand), transparent 70%)" }}
          />
          <span className="eyebrow">Agent command center</span>
          <h2 className="mt-2 max-w-lg font-display text-2xl leading-snug text-ink">
            Describe a campaign in plain language — the agent plans, targets, and
            drafts it on LinkedIn.
          </h2>
          <Link
            href="/agent"
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2.5 text-[14px] font-medium text-paper transition-colors hover:bg-ink-soft"
          >
            New campaign <span className="text-brand">→</span>
          </Link>
        </div>
      </div>

      <div
        className="rise rounded-2xl border border-line bg-surface p-7"
        style={{ animationDelay: "320ms" }}
      >
        <div className="flex items-center justify-between">
          <span className="eyebrow">Campaigns</span>
          <span className="nums text-[13px] text-faint">
            {campaigns.length} total
          </span>
        </div>

        {campaigns.length === 0 ? (
          <div className="mt-6 grid place-items-center rounded-xl border border-dashed border-line py-12 text-center">
            <div className="text-[14px] text-muted">No campaigns created yet.</div>
            <Link href="/agent" className="mt-1 text-[14px] font-medium text-brand-strong">
              Start one with the agent →
            </Link>
          </div>
        ) : (
          <div className="mt-4 divide-y divide-line">
            {campaigns.map((c) => (
              <div key={c.id} className="flex items-center gap-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium text-ink">{c.name}</span>
                    <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-brand-strong">
                      {c.status}
                    </span>
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    <span className="nums text-[12px] text-faint">{c.objective}</span>
                    {facetChips(c.targeting).map((v) => (
                      <span
                        key={v}
                        className="rounded bg-paper px-1.5 py-0.5 text-[12px] text-muted ring-1 ring-line"
                      >
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
                {c.lcm_url && (
                  <a
                    href={c.lcm_url}
                    target="_blank"
                    rel="noreferrer"
                    className="shrink-0 text-[13px] font-medium text-brand-strong hover:underline"
                  >
                    Campaign Manager →
                  </a>
                )}
                <button
                  onClick={() => remove(c.id)}
                  disabled={removing === c.id}
                  title="Remove from this list (does not delete on LinkedIn)"
                  aria-label={`Remove ${c.name} from list`}
                  className="shrink-0 rounded-md px-1.5 py-1 text-[16px] leading-none text-faint transition-colors hover:bg-paper hover:text-ink disabled:opacity-40"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
