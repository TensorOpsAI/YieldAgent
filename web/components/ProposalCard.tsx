"use client";

import { useState } from "react";
import type {
  Audience,
  Campaign,
  LineItem,
  Ad,
  Money,
  Previews,
  Reach,
} from "@/lib/chat";

type Facet = { label: string; key: string; values: string[] };

/** Compact member count: 290000000 → "290M", 150000 → "150K". */
function formatReach(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

const BIDDING_LABELS: Record<string, string> = {
  maximum_delivery: "Maximum delivery (auto)",
  cost_cap: "Cost cap",
  manual: "Manual",
};

/** Full delivery picture for a line item, with defaults shown so the operator
 *  sees every field - whether set explicitly or left on the platform's default. */
function deliveryRows(li: LineItem): { label: string; value: string }[] {
  const money = (m?: Money | null) => (m ? `${m.amount} ${m.currency}` : null);
  const rows: { label: string; value: string }[] = [];
  const daily = money(li.daily_budget);
  if (daily) rows.push({ label: "Daily budget", value: daily });
  rows.push({
    label: "Bidding",
    value: BIDDING_LABELS[li.bidding_strategy ?? "maximum_delivery"],
  });
  const bid = money(li.bid_amount);
  if (bid) rows.push({ label: "Bid / cap", value: bid });
  rows.push({ label: "Optimization", value: li.optimization_goal ?? "Auto" });
  rows.push({
    label: "Audience expansion",
    value: li.audience_expansion ? "On" : "Off",
  });
  rows.push({ label: "Audience network", value: li.audience_network ? "On" : "Off" });
  return rows;
}

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
  previews,
  reach,
  awaiting,
  onApprove,
  onReject,
}: {
  campaign: Campaign;
  unresolved: Record<string, string[]>;
  previews?: Previews;
  reach?: Reach;
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
  // Any ad whose creative is freshly authored (not an existing post) means
  // approving will PUBLISH a new post on the org page - warn the operator.
  const willCreatePost = Object.values(previews ?? {}).some(
    (p) => p.source === "ad_copy",
  );
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
          <span className="nums text-ink">{campaign?.objective ?? "n/a"}</span>
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
            {li?.name !== undefined && reach && li.name in reach && (
              <div className="mt-2">
                {reach[li.name] > 0 ? (
                  <span className="inline-flex items-center gap-1.5 rounded-md bg-brand-soft px-2 py-1 text-[12px] font-medium text-brand-strong">
                    <span aria-hidden="true">◎</span>
                    Est. audience ≈{" "}
                    <span className="nums">{formatReach(reach[li.name])}</span> members
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-[12px] font-medium text-amber-800">
                    Audience under the platform minimum, too small to run
                  </span>
                )}
              </div>
            )}
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
                          title={dropped ? "No match, won't be targeted" : ""}
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

            <div className="mt-3 border-t border-line pt-3">
              <div className="eyebrow mb-1.5">Delivery</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                {deliveryRows(li).map((r) => (
                  <div key={r.label} className="flex justify-between gap-2 text-[12px]">
                    <span className="text-faint">{r.label}</span>
                    <span className="nums text-right text-ink">{r.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}

        {ads.length > 0 && (
          <div className="mt-4">
            <div className="eyebrow mb-1.5">Ads</div>
            <div className="grid gap-2">
              {ads.map((ad: Ad, i: number) => {
                const c = ad?.creative ?? {};
                const preview = previews?.[ad?.name ?? ""];
                const fallback = c.existing_post_urn
                  ? `post ${c.existing_post_urn}`
                  : c.landing_url
                    ? `new post → ${c.landing_url}`
                    : "no source";
                return (
                  <div
                    key={i}
                    className="rounded-xl border border-line bg-paper p-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] font-medium text-ink">
                        {ad?.name}
                      </span>
                      <span className="text-[11px] text-faint">
                        {preview?.source === "existing_post"
                          ? "Sponsoring existing post"
                          : preview?.source === "ad_copy"
                            ? "New post"
                            : ""}
                      </span>
                    </div>
                    {preview ? (
                      <div className="mt-2 flex gap-3">
                        {preview.image_url && (
                          // Ephemeral external LinkedIn media URL (expires) - next/image
                          // optimization isn't appropriate, so a plain img is correct here.
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={preview.image_url}
                            alt={preview.headline ?? "Ad creative"}
                            className="h-16 w-16 shrink-0 rounded-md object-cover ring-1 ring-line"
                          />
                        )}
                        <div className="min-w-0">
                          {preview.headline && (
                            <div className="line-clamp-2 text-[13px] font-medium text-ink">
                              {preview.headline}
                            </div>
                          )}
                          {preview.text && (
                            <div className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-muted">
                              {preview.text}
                            </div>
                          )}
                          {preview.url && (
                            <a
                              href={preview.url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-1 block truncate text-[12px] text-brand-strong hover:underline"
                            >
                              {preview.url}
                            </a>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="nums mt-1 text-[12px] text-faint">{fallback}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {awaiting && (
          <div className="mt-4">
            {willCreatePost && (
              <div className="mb-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
                Heads up: approving will <strong>publish a new post</strong> on your
                LinkedIn page, then create the draft. No existing post is being sponsored.
              </div>
            )}
            <div className="flex items-center gap-2">
              <button
                onClick={() => decide(onApprove)}
                disabled={submitting}
                className="rounded-lg bg-brand px-4 py-2.5 text-[14px] font-semibold text-white transition-colors hover:bg-brand-strong disabled:opacity-50"
              >
                {submitting
                  ? "Creating…"
                  : willCreatePost
                    ? "Approve, create post & draft"
                    : "Approve & create draft"}
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
          </div>
        )}
      </div>
    </div>
  );
}
