/* eslint-disable @typescript-eslint/no-explicit-any */

function facets(audience: any): { label: string; values: string[] }[] {
  const map: [string, any][] = [
    ["Geos", audience?.geos],
    ["Seniorities", audience?.seniorities],
    ["Functions", audience?.job_functions],
    ["Industries", audience?.industries],
    ["Titles", audience?.job_titles],
    ["Skills", audience?.skills],
    ["Company sizes", audience?.company_sizes],
  ];
  return map
    .filter(([, v]) => Array.isArray(v) && v.length)
    .map(([label, v]) => ({ label, values: v as string[] }));
}

export function ProposalCard({
  campaign,
  awaiting,
  onApprove,
  onReject,
}: {
  campaign: any;
  awaiting: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const lineItems = campaign?.line_items ?? [];
  const ads = campaign?.ads ?? [];
  return (
    <div className="rise overflow-hidden rounded-2xl border border-ink/10 bg-surface shadow-[0_8px_30px_-12px_rgba(13,16,14,0.25)]">
      <div className="flex items-center justify-between border-b border-line bg-ink px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-brand live-dot" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-paper/70">
            Proposed draft
          </span>
        </div>
        <span className="nums text-[11px] text-paper/40">
          {lineItems.length} line item{lineItems.length === 1 ? "" : "s"} ·{" "}
          {ads.length} ad{ads.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="px-5 py-4">
        <div className="font-display text-xl text-ink">
          {campaign?.name ?? "Untitled campaign"}
        </div>
        <div className="mt-0.5 text-[12px] text-muted">
          Objective ·{" "}
          <span className="nums text-ink">{campaign?.objective ?? "—"}</span>
        </div>

        {lineItems.map((li: any, i: number) => (
          <div key={i} className="mt-4 rounded-xl border border-line bg-paper p-4">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-medium text-ink">{li?.name}</span>
              <span className="nums text-[11px] text-muted">
                {li?.budget?.amount} {li?.budget?.currency} · {li?.flight?.start_date}
                {" → "}
                {li?.flight?.end_date}
              </span>
            </div>
            <div className="mt-3 grid gap-2">
              {facets(li?.targeting?.audience).map((f) => (
                <div key={f.label} className="flex gap-2 text-[12px]">
                  <span className="w-24 shrink-0 text-faint">{f.label}</span>
                  <span className="flex flex-wrap gap-1">
                    {f.values.map((v) => (
                      <span
                        key={v}
                        className="rounded-md bg-surface px-1.5 py-0.5 text-[11px] text-ink ring-1 ring-line"
                      >
                        {v}
                      </span>
                    ))}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}

        {awaiting && (
          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={onApprove}
              className="rounded-lg bg-brand px-4 py-2.5 text-[13px] font-semibold text-white transition-colors hover:bg-brand-strong"
            >
              Approve &amp; create draft
            </button>
            <button
              onClick={onReject}
              className="rounded-lg border border-line px-4 py-2.5 text-[13px] font-medium text-muted transition-colors hover:border-ink/20 hover:text-ink"
            >
              Reject
            </button>
            <span className="ml-auto text-[11px] text-faint">
              Nothing is created until you approve.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
