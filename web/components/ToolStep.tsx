"use client";

import { useState } from "react";
import type { ToolArgs } from "@/lib/chat";

const asString = (v: unknown): string | undefined =>
  typeof v === "string" ? v : undefined;

/** Human label for a tool call, derived from its name + args. */
export function toolLabel(name: string, args: ToolArgs): string {
  const platform = asString(args?.platform);
  const on = platform ? ` on ${platform}` : "";
  switch (name) {
    case "list_ad_platforms":
      return "Checking available platforms";
    case "describe_platform":
      return `Reading ${platform ?? "platform"} rules`;
    case "list_targeting_options": {
      const kind = asString(args?.kind)?.replace(/_/g, " ") ?? "targeting options";
      return `Looking up ${kind}`;
    }
    case "search_targeting": {
      const facet = asString(args?.facet) ?? "targeting";
      const query = asString(args?.query);
      return `Searching ${facet}${query ? ` for “${query}”` : ""}`;
    }
    case "preview_targeting":
      return `Resolving targeting${on}`;
    case "estimate_reach":
      return "Estimating audience reach";
    case "propose_campaign":
      return "Preparing the proposal";
    case "create_draft":
      return `Creating the draft${on}`;
    default:
      return name;
  }
}

/** snake_case / camelCase -> "Sentence case" for result keys. */
function prettyKey(k: string): string {
  const spaced = k.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-md bg-surface px-1.5 py-0.5 text-[11px] text-ink ring-1 ring-line">
      {children}
    </span>
  );
}

function Bool({ value }: { value: boolean }) {
  return (
    <span
      className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ${
        value
          ? "bg-brand-soft text-brand-strong ring-brand/20"
          : "bg-paper text-faint ring-line"
      }`}
    >
      {value ? "yes" : "no"}
    </span>
  );
}

/** Recursively render a tool result: lists become chip clouds, objects become
 *  labelled rows, scalars render inline. Keeps deep results readable, no raw JSON. */
function ResultNode({ value }: { value: unknown }) {
  if (value === null || value === undefined)
    return <span className="text-faint">-</span>;
  if (typeof value === "boolean") return <Bool value={value} />;
  if (typeof value === "number")
    return <span className="nums text-ink">{value.toLocaleString("en-US")}</span>;
  if (typeof value === "string")
    return <span className="whitespace-pre-wrap break-words text-ink">{value}</span>;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-faint">none</span>;
    const allScalar = value.every((v) => v === null || typeof v !== "object");
    if (allScalar)
      return (
        <div className="flex flex-wrap gap-1">
          {value.map((v, i) => (
            <Chip key={i}>{String(v)}</Chip>
          ))}
        </div>
      );
    return (
      <div className="space-y-1.5">
        {value.map((v, i) => (
          <div
            key={i}
            className="rounded-md border border-line bg-surface/60 p-2"
          >
            <ResultNode value={v} />
          </div>
        ))}
      </div>
    );
  }

  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return <span className="text-faint">empty</span>;
  return (
    <div className="space-y-1.5">
      {entries.map(([k, v]) => {
        const nested = v !== null && typeof v === "object";
        return (
          <div
            key={k}
            className={nested ? "flex flex-col gap-1" : "flex items-start gap-2"}
          >
            <span className="shrink-0 text-[11px] uppercase tracking-wide text-faint">
              {prettyKey(k)}
            </span>
            <div
              className={`min-w-0 flex-1 text-[12px] ${
                nested ? "border-l border-line/70 pl-2.5" : ""
              }`}
            >
              <ResultNode value={v} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** One agent tool step: a status row that, once finished, expands to reveal the
 *  tool's full result in a refined panel. */
export function ToolStep({
  name,
  args,
  summary,
  result,
  count,
}: {
  name: string;
  args: ToolArgs;
  summary: string | null;
  result?: unknown;
  count: number;
}) {
  const [open, setOpen] = useState(false);
  const done = summary !== null;
  const hasResult =
    done && result !== undefined && result !== null && result !== "";

  return (
    <div className="pl-1">
      <button
        type="button"
        disabled={!hasResult}
        onClick={() => setOpen((o) => !o)}
        className={`group flex w-full items-center gap-2.5 rounded-md py-0.5 text-left text-[13px] ${
          hasResult ? "cursor-pointer hover:bg-paper/70" : "cursor-default"
        }`}
      >
        {done ? (
          <span className="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full bg-brand/15 text-[9px] text-brand">
            ✓
          </span>
        ) : (
          <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-brand/25 border-t-brand" />
        )}
        <span className="text-muted group-hover:text-ink">{toolLabel(name, args)}</span>
        {count > 1 && (
          <span className="rounded bg-paper px-1 text-[11px] text-faint ring-1 ring-line">
            ×{count}
          </span>
        )}
        {hasResult && (
          <span
            className={`ml-auto text-[10px] text-faint transition-transform duration-200 group-hover:text-muted ${
              open ? "rotate-90" : ""
            }`}
            aria-hidden="true"
          >
            ▶
          </span>
        )}
      </button>

      {open && hasResult && (
        <div className="ml-6 mt-1.5 overflow-hidden rounded-lg border border-line bg-paper/70 shadow-[0_6px_20px_-14px_rgba(13,16,14,0.3)]">
          <div className="flex items-center justify-between border-b border-line/70 px-3 py-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-faint">
              Result
            </span>
            <span className="nums text-[10px] text-faint">{name}</span>
          </div>
          <div className="max-h-80 overflow-auto p-3 text-[12px] leading-relaxed">
            <ResultNode value={result} />
          </div>
        </div>
      )}
    </div>
  );
}
