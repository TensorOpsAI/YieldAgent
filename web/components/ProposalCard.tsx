"use client";

import { useState } from "react";
import type { Audience, Campaign, LineItem, Ad } from "@/lib/chat";

type Facet = { label: string; key: string; values: string[] };

function facets(audience: Audience | undefined): Facet[] {
  const map: [string, string, string[] | undefined][] = [
    ["Geos", "geos", audience?.geos],
    ["Seniorities", "seniorities", audience?.seniorities],
    ["Functions", "job_functions", audience?.job_functions],
    ["Industries", "industries", audience?.industries],
    ["Titles", "job_titles", audience?.job_titles],
    ["Skills", "skills", audience?.skills],
    ["Company sizes", "company_sizes", audience?.company_sizes],
  ];
  return map
    .filter((entry): entry is [string, string, string[]] => {
      const v = entry[2];
      return Array.isArray(v) && v.length > 0;
    })
    .map(([label, key, values]) => ({ label, key, values }));
}

export function ProposalCard({
  campaign,
  unresolved,
  awaiting,
  onApprove,
  onReject,
}: {
  campaign: Campaign;
  unresolved: Record<string, string[]>;
  awaiting: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const decide = (fn: () => void) => {
    if (submitting) return; // guard against double-submit (one approval only)
    setSubmitting(true);
    fn();
  };

  const lineItems = campaign?.line_items ?? [];
  const ads = campaign?.ads ?? [];
  const unresolvedCount = Object.values(unresolved ?? {}).reduce(
    (n, v) => n + v.length,
    0,
  );
  const isDropped = (key: string, value: string) =>
    (unresolved?.[key] ?? []).includes(value);

  return (
    <div className="rise overflow-hidden rounded-2xl border border-ink/10 bg-surface shadow-[0_8px_30px_-12px_rgba(13,16,14,0.25)]">
      <div className="flex items-center justify-between border-b border-line bg-ink px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-brand live-dot" />
          <span className="text-[12px] font-semibold uppercase tracking-[0.14em] text-paper/70">
            Proposed draft
          </span>
        </div>
        <span className="nums text-[12px] text-paper/40">
          {lineItems.length} line item{lineItems.length === 1 ? "" : "s"} ·{" "}
          {ads.length} ad{ads.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="px-5 py-4">
        <div className="font-display text-xl text-ink">
          {campaign?.name ?? "Untitled campaign"}
        </div>
        <div className="mt-0.5 text-[13px] text-muted">
          Objective ·{" "}
          <span className="nums text-ink">{campaign?.objective ?? "—"}</span>
        </div>

        {unresolvedCount > 0 && (
          <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
            <span className="font-semibold">{unresolvedCount}</span> targeting
            value{unresolvedCount === 1 ? "" : "s"} didn&rsquo;t match LinkedIn and
            won&rsquo;t be targeted (struck through below). Everything else is
            confirmed against the live API.
          </div>
        )}

        {lineItems.map((li: LineItem, i: number) => (
          <div key={i} className="mt-4 rounded-xl border border-line bg-paper p-4">
            <div className="flex items-center justify-between">
              <span className="text-[14px] font-medium text-ink">{li?.name}</span>
              <span className="nums text-[12px] text-muted">
                {li?.budget?.amount} {li?.budget?.currency} · {li?.flight?.start_date}
                {" → "}
                {li?.flight?.end_date}
              </span>
            </div>
            <div className="mt-3 grid gap-2">
              {facets(li?.targeting?.audience).map((f) => (
                <div key={f.label} className="flex gap-2 text-[13px]">
                  <span className="w-24 shrink-0 text-faint">{f.label}</span>
                  <span className="flex flex-wrap gap-1">
                    {f.values.map((v) => {
                      const dropped = isDropped(f.key, v);
                      return (
                        <span
                          key={v}
                          title={dropped ? "No LinkedIn match — won't be targeted" : ""}
                          className={`rounded-md px-1.5 py-0.5 text-[12px] ring-1 ${
                            dropped
                              ? "text-faint line-through ring-amber-200 bg-amber-50/50"
                              : "bg-surface text-ink ring-line"
                          }`}
                        >
                          {v}
                        </span>
                      );
                    })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}

        {ads.length > 0 && (
          <div className="mt-4">
            <div className="eyebrow mb-1.5">Ads</div>
            <div className="grid gap-1.5">
              {ads.map((ad: Ad, i: number) => {
                const c = ad?.creative ?? {};
                const source = c.existing_post_urn
                  ? `post ${c.existing_post_urn}`
                  : c.landing_url
                    ? `new post → ${c.landing_url}`
                    : "no source";
                return (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg border border-line bg-paper px-3 py-2 text-[13px]"
                  >
                    <span className="text-ink">{ad?.name}</span>
                    <span className="nums text-faint">{source}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {awaiting && (
          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={() => decide(onApprove)}
              disabled={submitting}
              className="rounded-lg bg-brand px-4 py-2.5 text-[14px] font-semibold text-white transition-colors hover:bg-brand-strong disabled:opacity-50"
            >
              {submitting ? "Creating…" : "Approve & create draft"}
            </button>
            <button
              onClick={() => decide(onReject)}
              disabled={submitting}
              className="rounded-lg border border-line px-4 py-2.5 text-[14px] font-medium text-muted transition-colors hover:border-ink/20 hover:text-ink disabled:opacity-50"
            >
              Reject
            </button>
            <span className="ml-auto text-[12px] text-faint">
              Nothing is created until you approve.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
