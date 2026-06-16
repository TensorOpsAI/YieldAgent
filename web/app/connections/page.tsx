"use client";

import { useEffect, useState } from "react";
import {
  fetchAdPlatforms,
  fetchProviders,
  type AdPlatform,
  type Provider,
} from "@/lib/api";

function platformDetail(p: AdPlatform): string {
  if (p.can_create) return "Connected · campaigns enabled";
  if (p.connected) return "Connected · creation coming soon";
  return "Coming soon";
}

function Dot({ on }: { on: boolean }) {
  return (
    <span
      className={`h-2 w-2 rounded-full ${
        on ? "bg-brand live-dot shadow-[0_0_0_3px_var(--color-brand-soft)]" : "bg-faint/40"
      }`}
    />
  );
}

function SoonTag() {
  return (
    <span className="rounded-md bg-paper px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-faint/70 ring-1 ring-line/60">
      Soon
    </span>
  );
}

export default function Connections() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [adPlatforms, setAdPlatforms] = useState<AdPlatform[]>([]);
  const [testing, setTesting] = useState(false);

  // Used by the "Re-test keys" button; it legitimately toggles the spinner.
  const retest = () => {
    setTesting(true);
    fetchProviders(true)
      .then(setProviders)
      .catch(() => undefined)
      .finally(() => setTesting(false));
  };

  // Initial load: fetch without touching `testing` (avoids a synchronous
  // setState in the effect body - the cached providers load fast).
  useEffect(() => {
    fetchProviders(false).then(setProviders).catch(() => undefined);
    fetchAdPlatforms().then(setAdPlatforms).catch(() => undefined);
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-7 py-8">
      <div className="flex items-end justify-between">
        <div>
          <span className="eyebrow">Connections</span>
          <h1 className="mt-1 font-display text-3xl text-ink">Platform readiness</h1>
        </div>
        <button
          onClick={retest}
          disabled={testing}
          className="rounded-lg border border-line bg-surface px-3.5 py-2 text-[13px] font-medium text-ink transition-colors hover:border-ink/20 disabled:opacity-50"
        >
          {testing ? "Testing…" : "Re-test keys"}
        </button>
      </div>

      <section>
        <div className="eyebrow mb-3">LLM providers</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {providers.map((p) => (
            <div
              key={p.id}
              className="rounded-xl border border-line bg-surface p-4"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-ink">{p.label}</span>
                <Dot on={p.connected} />
              </div>
              <div className="mt-0.5 text-[13px] text-muted">
                {p.connected ? "Authenticated" : "Not connected"}
              </div>
              {p.connected ? (
                <div className="mt-3 flex flex-wrap gap-1">
                  {p.models.map((m) => (
                    <span
                      key={m}
                      className="nums rounded-md bg-paper px-1.5 py-0.5 text-[12px] text-muted ring-1 ring-line"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="mt-3 text-[12px] text-faint">{p.reason}</div>
              )}
            </div>
          ))}
          {providers.length === 0 && (
            <div className="text-[14px] text-faint">Checking providers…</div>
          )}
        </div>
        <p className="mt-2 text-[12px] text-faint">
          Keys are verified against each provider&rsquo;s models endpoint; no
          inference is spent.
        </p>
      </section>

      <section>
        <div className="eyebrow mb-3">Ad platforms</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {adPlatforms.map((c) => (
            <div
              key={c.platform}
              className={`rounded-xl border border-line bg-surface p-4 ${
                c.can_create ? "" : "opacity-70"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-ink">{c.platform}</span>
                {c.can_create ? <Dot on /> : <SoonTag />}
              </div>
              <div className="mt-0.5 text-[13px] text-muted">
                {platformDetail(c)}
              </div>
            </div>
          ))}
          {adPlatforms.length === 0 && (
            <div className="text-[14px] text-faint">Checking platforms…</div>
          )}
        </div>
      </section>
    </div>
  );
}
