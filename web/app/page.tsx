import Link from "next/link";

const STATS = [
  { label: "Tracked spend", value: "—", hint: "n/a for drafts" },
  { label: "Active campaigns", value: "0" },
  { label: "Pending approvals", value: "0" },
  { label: "Connections", value: "1" },
];

export default function Dashboard() {
  return (
    <div className="space-y-6 p-6">
      <div className="grid grid-cols-4 gap-4">
        {STATS.map((s) => (
          <div
            key={s.label}
            className="rounded-xl border border-gray-200 bg-white p-4"
          >
            <div className="text-sm text-gray-500">{s.label}</div>
            <div className="mt-1 text-2xl font-semibold">{s.value}</div>
            {s.hint && <div className="mt-1 text-xs text-gray-400">{s.hint}</div>}
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="text-xs font-medium tracking-wide text-gray-500">
          AGENT COMMAND CENTER
        </div>
        <div className="mt-2 text-gray-900">No campaign plan yet.</div>
        <p className="mt-1 text-sm text-gray-500">
          Describe a campaign in plain language and the agent plans, targets, and
          creates a draft on LinkedIn.
        </p>
        <Link
          href="/agent"
          className="mt-4 inline-block rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          New campaign
        </Link>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="text-xs font-medium tracking-wide text-gray-500">
          CAMPAIGNS
        </div>
        <div className="mt-2 text-sm text-gray-400">
          No campaigns created yet.
        </div>
      </div>
    </div>
  );
}
