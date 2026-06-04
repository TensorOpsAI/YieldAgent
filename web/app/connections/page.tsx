"use client";

import { useEffect, useState } from "react";
import { fetchProviders, type Provider } from "@/lib/api";

const AD_PLATFORMS = [
  { platform: "LinkedIn Ads", status: "Connected", detail: "Gad Benram" },
  { platform: "Meta Ads", status: "Disabled", detail: "Provider setup required" },
  { platform: "Google Ads", status: "Disabled", detail: "Provider setup required" },
];

export default function Connections() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [testing, setTesting] = useState(false);

  const load = (test = false) => {
    setTesting(test);
    fetchProviders(test)
      .then(setProviders)
      .catch(() => undefined)
      .finally(() => setTesting(false));
  };

  useEffect(() => load(false), []);

  return (
    <div className="space-y-8 p-6">
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-medium tracking-wide text-gray-500">
            LLM PROVIDERS
          </h2>
          <button
            onClick={() => load(true)}
            disabled={testing}
            className="rounded-md border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {testing ? "Testing…" : "Re-test keys"}
          </button>
        </div>
        <div className="grid grid-cols-3 gap-4">
          {providers.map((p) => (
            <div
              key={p.id}
              className="rounded-xl border border-gray-200 bg-white p-4"
            >
              <div className="flex items-center justify-between">
                <div className="font-medium text-gray-900">{p.label}</div>
                <span
                  className={`text-sm ${
                    p.connected ? "text-emerald-600" : "text-gray-400"
                  }`}
                >
                  {p.connected ? "● Connected" : "○ Not connected"}
                </span>
              </div>
              {p.connected ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {p.models.map((m) => (
                    <span
                      key={m}
                      className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="mt-2 text-xs text-gray-400">{p.reason}</div>
              )}
            </div>
          ))}
          {providers.length === 0 && (
            <div className="text-sm text-gray-400">Checking providers…</div>
          )}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-xs font-medium tracking-wide text-gray-500">
          AD PLATFORMS
        </h2>
        <div className="grid grid-cols-3 gap-4">
          {AD_PLATFORMS.map((c) => (
            <div
              key={c.platform}
              className="rounded-xl border border-gray-200 bg-white p-4"
            >
              <div className="font-medium text-gray-900">{c.platform}</div>
              <div
                className={`mt-1 text-sm ${
                  c.status === "Connected" ? "text-emerald-600" : "text-gray-400"
                }`}
              >
                {c.status}
              </div>
              <div className="mt-1 text-xs text-gray-400">{c.detail}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
