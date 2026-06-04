"use client";

import { useEffect, useRef, useState } from "react";
import { ProviderIcon } from "./ProviderIcon";

export function ModelPicker({
  models,
  value,
  onChange,
}: {
  models: string[];
  value: string;
  onChange: (model: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

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
        disabled={models.length === 0}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Model: ${value || "none selected"}`}
        className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-2 text-[14px] text-ink transition-colors hover:border-ink/25 disabled:opacity-50"
      >
        {value && <ProviderIcon model={value} className="h-4 w-4 text-ink" />}
        <span className="nums max-w-[150px] truncate">
          {value || "Pick a model"}
        </span>
        <span className="text-faint" aria-hidden="true">
          ▾
        </span>
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Available models"
          className="absolute bottom-full left-0 z-10 mb-1.5 w-60 overflow-hidden rounded-xl border border-line bg-surface shadow-[0_10px_30px_-12px_rgba(43,39,34,0.4)]"
        >
          {models.length === 0 ? (
            <div className="px-3 py-2.5 text-[13px] text-faint">
              No provider connected
            </div>
          ) : (
            models.map((m) => (
              <button
                key={m}
                type="button"
                role="option"
                aria-selected={m === value}
                onClick={() => {
                  onChange(m);
                  setOpen(false);
                }}
                className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-[14px] transition-colors hover:bg-paper ${
                  m === value ? "font-medium text-ink" : "text-muted"
                }`}
              >
                <ProviderIcon model={m} className="h-4 w-4 shrink-0 text-ink" />
                <span className="nums truncate">{m}</span>
                {m === value && (
                  <span className="ml-auto text-brand" aria-hidden="true">
                    ✓
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
