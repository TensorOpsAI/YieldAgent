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
    <aside className="flex w-60 shrink-0 flex-col px-3 py-4 text-paper/90">
      <div className="px-3 pb-5">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-brand text-[13px] font-bold text-ink">
            Y
          </span>
          <div className="leading-tight">
            <div className="text-[13px] font-semibold tracking-tight text-white">
              YieldAgent
            </div>
            <div className="text-[11px] text-paper/40">Campaign Ops</div>
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
              className={`group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors ${
                active
                  ? "bg-white/10 text-white"
                  : "text-paper/55 hover:bg-white/5 hover:text-paper/90"
              }`}
            >
              <span
                className={`text-[13px] ${active ? "text-brand" : "text-paper/35"}`}
              >
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}

        <div className="px-3 pb-1.5 pt-5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-paper/30">
            Soon
          </span>
        </div>
        {STUBS.map((label) => (
          <span
            key={label}
            className="flex cursor-not-allowed items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-paper/25"
          >
            <span className="text-paper/15">·</span>
            {label}
          </span>
        ))}
      </nav>

      <div className="rounded-xl border border-brand/20 bg-brand/10 p-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-brand">
          <span className="h-1.5 w-1.5 rounded-full bg-brand live-dot" />
          Approval gates active
        </div>
        <div className="mt-1 text-[11px] leading-snug text-paper/40">
          Spend, publish &amp; broad targeting are held for review.
        </div>
      </div>
    </aside>
  );
}
