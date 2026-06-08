"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Provider } from "@/lib/api";
import { modelMeta, TAG_STYLES } from "@/lib/models";
import { ProviderIcon } from "./ProviderIcon";

function TagBadge({ tag }: { tag: string }) {
  if (!tag) return null;
  const style = TAG_STYLES[tag as keyof typeof TAG_STYLES] ?? "bg-paper text-muted ring-line";
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 ${style}`}
    >
      {tag}
    </span>
  );
}

export function ModelPicker({
  providers,
  value,
  onChange,
}: {
  providers: Provider[];
  value: string;
  onChange: (model: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);

  const connected = useMemo(() => providers.filter((p) => p.connected), [providers]);
  const total = connected.reduce((n, p) => n + p.models.length, 0);

  // Filter each provider's models by the query (name, blurb, or provider label).
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    return connected
      .map((p) => ({
        provider: p,
        models: p.models.filter(
          (m) =>
            !q ||
            m.toLowerCase().includes(q) ||
            modelMeta(m).blurb.toLowerCase().includes(q) ||
            p.label.toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.models.length > 0);
  }, [connected, query]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const selected = modelMeta(value);
  const searching = query.trim().length > 0;

  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <div
      ref={ref}
      className="relative shrink-0"
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={total === 0}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Model: ${value || "none selected"}`}
        className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-2 text-[14px] text-ink transition-colors hover:border-ink/25 disabled:opacity-50"
      >
        {value && <ProviderIcon model={value} className="h-4 w-4 text-ink" />}
        <span className="nums max-w-[150px] truncate">{value || "Pick a model"}</span>
        {selected.tag && <TagBadge tag={selected.tag} />}
        <span className="text-faint" aria-hidden="true">
          ▾
        </span>
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Available models"
          className="absolute bottom-full left-0 z-10 mb-1.5 w-80 overflow-hidden rounded-xl border border-line bg-surface shadow-[0_10px_30px_-12px_rgba(43,39,34,0.4)]"
        >
          {total === 0 ? (
            <div className="px-3 py-2.5 text-[13px] text-faint">No provider connected</div>
          ) : (
            <>
              <div className="border-b border-line p-2">
                <input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search models…"
                  aria-label="Search models"
                  className="w-full rounded-lg bg-paper px-2.5 py-1.5 text-[13px] text-ink outline-none placeholder:text-faint"
                />
              </div>
              <div className="max-h-[60vh] overflow-y-auto py-1">
                {groups.length === 0 ? (
                  <div className="px-3 py-3 text-[13px] text-faint">No match</div>
                ) : (
                  groups.map(({ provider, models }) => {
                    const isCollapsed = collapsed.has(provider.id) && !searching;
                    return (
                      <div key={provider.id} className="mb-0.5">
                        <button
                          type="button"
                          onClick={() => toggle(provider.id)}
                          aria-expanded={!isCollapsed}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left"
                        >
                          {provider.models[0] && (
                            <ProviderIcon
                              model={provider.models[0]}
                              className="h-3.5 w-3.5 text-faint"
                            />
                          )}
                          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">
                            {provider.label}
                          </span>
                          <span className="nums text-[11px] text-faint/70">
                            {models.length}
                          </span>
                          <span className="ml-auto text-[10px] text-faint" aria-hidden="true">
                            {isCollapsed ? "▸" : "▾"}
                          </span>
                        </button>

                        {!isCollapsed &&
                          models.map((m) => {
                            const meta = modelMeta(m);
                            return (
                              <button
                                key={m}
                                type="button"
                                role="option"
                                aria-selected={m === value}
                                onClick={() => {
                                  onChange(m);
                                  setOpen(false);
                                }}
                                className={`flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors hover:bg-paper ${
                                  m === value ? "bg-paper" : ""
                                }`}
                              >
                                <ProviderIcon
                                  model={m}
                                  className="mt-0.5 h-4 w-4 shrink-0 text-ink"
                                />
                                <span className="min-w-0 flex-1">
                                  <span className="flex items-center gap-1.5">
                                    <span
                                      className={`nums truncate text-[13.5px] ${
                                        m === value ? "font-semibold text-ink" : "text-ink"
                                      }`}
                                    >
                                      {m}
                                    </span>
                                    <TagBadge tag={meta.tag} />
                                  </span>
                                  {meta.blurb && (
                                    <span className="mt-0.5 block truncate text-[12px] text-muted">
                                      {meta.blurb}
                                    </span>
                                  )}
                                </span>
                                {m === value && (
                                  <span className="mt-0.5 text-brand" aria-hidden="true">
                                    ✓
                                  </span>
                                )}
                              </button>
                            );
                          })}
                      </div>
                    );
                  })
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
