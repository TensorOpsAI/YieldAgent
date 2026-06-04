import Link from "next/link";

const STATS = [
  { label: "Tracked spend", value: "—", hint: "n/a for drafts" },
  { label: "Draft campaigns", value: "0" },
  { label: "Pending approvals", value: "0" },
  { label: "Connections", value: "1" },
];

export default function Dashboard() {
  return (
    <div className="mx-auto max-w-6xl space-y-7 px-7 py-8">
      <div>
        <span className="eyebrow">Overview</span>
        <h1 className="mt-1 font-display text-3xl text-ink">Good to see you.</h1>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {STATS.map((s, i) => (
          <div
            key={s.label}
            className="rise rounded-xl border border-line bg-surface p-4"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className="text-[12px] text-muted">{s.label}</div>
            <div className="nums mt-2 text-3xl font-medium text-ink">
              {s.value}
            </div>
            {s.hint && (
              <div className="mt-1 text-[11px] text-faint">{s.hint}</div>
            )}
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
          <p className="mt-2 max-w-md text-[13px] text-muted">
            It pulls real targeting options, never guesses, and waits for your
            approval before anything is created.
          </p>
          <Link
            href="/agent"
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2.5 text-[13px] font-medium text-paper transition-colors hover:bg-ink-soft"
          >
            New campaign
            <span className="text-brand">→</span>
          </Link>
        </div>
      </div>

      <div
        className="rise rounded-2xl border border-line bg-surface p-7"
        style={{ animationDelay: "320ms" }}
      >
        <div className="flex items-center justify-between">
          <span className="eyebrow">Campaigns</span>
          <span className="nums text-[12px] text-faint">0 total</span>
        </div>
        <div className="mt-6 grid place-items-center rounded-xl border border-dashed border-line py-12 text-center">
          <div className="text-[13px] text-muted">No campaigns created yet.</div>
          <Link href="/agent" className="mt-1 text-[13px] font-medium text-brand-strong">
            Start one with the agent →
          </Link>
        </div>
      </div>
    </div>
  );
}
