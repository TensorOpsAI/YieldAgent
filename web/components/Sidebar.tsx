"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Dashboard", icon: "▦" },
  { href: "/agent", label: "Agent Console", icon: "◈" },
  { href: "/connections", label: "Connections", icon: "⦿" },
];

const STUBS = ["Target Profiles", "Campaign Briefs", "Tools", "Audit Log"];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-sand px-3 py-4">
      <div className="px-3 pb-5">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-brand text-[14px] font-bold text-white">
            Y
          </span>
          <div className="leading-tight">
            <div className="text-[14px] font-semibold tracking-tight text-ink">
              YieldAgent
            </div>
            <div className="text-[12px] text-muted">Campaign Ops</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5">
        {NAV.map((item) => {
          const active = path === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[14px] transition-colors ${
                active
                  ? "bg-surface font-medium text-ink shadow-sm"
                  : "text-muted hover:bg-surface/70 hover:text-ink"
              }`}
            >
              <span className={active ? "text-brand" : "text-faint"}>
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}

        <div className="px-3 pb-1.5 pt-5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-faint">
            Soon
          </span>
        </div>
        {STUBS.map((label) => (
          <span
            key={label}
            className="flex cursor-not-allowed items-center gap-2.5 rounded-lg px-3 py-2 text-[14px] text-faint"
          >
            <span className="text-line">·</span>
            {label}
          </span>
        ))}
      </nav>

      <div className="rounded-xl border border-brand/25 bg-brand-soft p-3">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold text-brand-strong">
          <span className="h-1.5 w-1.5 rounded-full bg-brand live-dot" />
          Approval gates active
        </div>
        <div className="mt-1 text-[12px] leading-snug text-muted">
          Spend, publish &amp; broad targeting are held for review.
        </div>
      </div>
    </aside>
  );
}
