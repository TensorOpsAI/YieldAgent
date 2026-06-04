"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/agent", label: "Agent Console" },
  { href: "/connections", label: "Connections" },
];

const STUBS = ["Target Profiles", "Campaign Briefs", "Tools", "Audit Log"];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-gray-200 bg-gray-50">
      <div className="border-b border-gray-200 px-5 py-4">
        <div className="text-xs font-semibold tracking-wide text-emerald-700">
          YIELDAGENT
        </div>
        <div className="text-sm font-medium text-gray-900">Campaign Ops</div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-3">
        {NAV.map((item) => {
          const active = path === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded-lg px-3 py-2 text-sm ${
                active
                  ? "bg-white font-medium text-gray-900 shadow-sm"
                  : "text-gray-600 hover:bg-white/70"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
        <div className="my-2 border-t border-gray-200" />
        {STUBS.map((label) => (
          <span
            key={label}
            className="block cursor-not-allowed rounded-lg px-3 py-2 text-sm text-gray-400"
          >
            {label}
          </span>
        ))}
      </nav>
      <div className="m-3 rounded-lg border border-emerald-100 bg-emerald-50 p-3">
        <div className="text-xs font-medium text-emerald-800">
          Approval gates active
        </div>
        <div className="mt-0.5 text-[11px] text-emerald-700/80">
          Spend, publish &amp; broad targeting are held.
        </div>
      </div>
    </aside>
  );
}
