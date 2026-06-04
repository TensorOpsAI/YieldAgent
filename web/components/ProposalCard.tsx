/* eslint-disable @typescript-eslint/no-explicit-any */

function facetList(audience: any): string[] {
  const out: string[] = [];
  const add = (label: string, v: any) => {
    if (Array.isArray(v) && v.length) out.push(`${label}: ${v.join(", ")}`);
  };
  add("Geos", audience?.geos);
  add("Seniorities", audience?.seniorities);
  add("Functions", audience?.job_functions);
  add("Industries", audience?.industries);
  add("Titles", audience?.job_titles);
  add("Skills", audience?.skills);
  add("Company sizes", audience?.company_sizes);
  return out;
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
    <div className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4">
      <div className="text-xs font-semibold tracking-wide text-emerald-700">
        PROPOSED DRAFT
      </div>
      <div className="mt-1 text-base font-semibold text-gray-900">
        {campaign?.name ?? "Untitled campaign"}
      </div>
      <div className="text-sm text-gray-500">
        Objective: {campaign?.objective ?? "—"}
      </div>

      {lineItems.map((li: any, i: number) => (
        <div key={i} className="mt-3 rounded-lg border border-gray-200 bg-white p-3">
          <div className="text-sm font-medium text-gray-900">{li?.name}</div>
          <div className="text-xs text-gray-500">
            Budget: {li?.budget?.amount} {li?.budget?.currency} · Flight:{" "}
            {li?.flight?.start_date} → {li?.flight?.end_date}
          </div>
          <ul className="mt-2 space-y-0.5">
            {facetList(li?.targeting?.audience).map((f, j) => (
              <li key={j} className="text-xs text-gray-600">
                {f}
              </li>
            ))}
          </ul>
        </div>
      ))}

      <div className="mt-2 text-xs text-gray-500">
        {ads.length} ad{ads.length === 1 ? "" : "s"}:{" "}
        {ads.map((a: any) => a?.name).filter(Boolean).join(", ") || "—"}
      </div>

      {awaiting && (
        <div className="mt-4 flex gap-2">
          <button
            onClick={onApprove}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            Approve &amp; create draft
          </button>
          <button
            onClick={onReject}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
