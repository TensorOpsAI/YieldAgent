"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
    case "list_recent_posts":
      return "Finding the right post";
    case "preview_targeting":
      return `Resolving targeting${on}`;
    case "estimate_reach":
      return "Estimating audience reach";
    case "quote_budget_floor":
      return `Checking the minimum budget${on}`;
    case "propose_campaign":
      return "Preparing the proposal";
    case "create_draft":
      return `Creating the draft${on}`;
    default:
      return name;
  }
}

const num = (n: number) => n.toLocaleString("en-US");
const isUrn = (v: unknown) => typeof v === "string" && v.startsWith("urn:");

type Money = { amount?: string; currency?: string };
const money = (m?: Money | null) =>
  m?.amount ? `${m.amount} ${m.currency ?? ""}`.trim() : null;

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-[11px] uppercase tracking-wide text-faint">{label}</span>
      <span className="nums text-[12px] font-medium text-ink">{value}</span>
    </div>
  );
}

function Tag({ children, tone = "muted" }: { children: React.ReactNode; tone?: "brand" | "muted" }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        tone === "brand"
          ? "bg-brand-soft text-brand-strong ring-1 ring-brand/20"
          : "bg-paper text-faint ring-1 ring-line"
      }`}
    >
      {children}
    </span>
  );
}

function Chips({ items, max = 16 }: { items: unknown[]; max?: number }) {
  const named = items.filter((v) => !isUrn(v)).map(String);
  const shown = named.slice(0, max);
  const rest = named.length - shown.length;
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((v, i) => (
        <span
          key={i}
          className="rounded-md bg-surface px-1.5 py-0.5 text-[11px] text-ink ring-1 ring-line"
        >
          {v}
        </span>
      ))}
      {rest > 0 && <span className="self-center text-[11px] text-faint">+{rest} more</span>}
    </div>
  );
}

/** Compact, human-friendly summary per tool. Returns null to fall back to the
 *  generic renderer (keeps unknown/edge results readable without bespoke code). */
function summarize(name: string, result: unknown, args: ToolArgs): React.ReactNode | null {
  const r = result as any;
  switch (name) {
    case "list_ad_platforms": {
      if (!Array.isArray(r)) return null;
      return (
        <div className="flex flex-wrap gap-1.5">
          {r.map((p) => (
            <span
              key={p.platform}
              className="inline-flex items-center gap-1.5 rounded-md bg-surface px-2 py-1 text-[12px] ring-1 ring-line"
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${p.can_create ? "bg-brand" : "bg-faint/40"}`}
              />
              <span className="text-ink">{p.platform}</span>
              <span className="text-faint">{p.can_create ? "ready" : "soon"}</span>
            </span>
          ))}
        </div>
      );
    }
    case "estimate_reach": {
      if (typeof r?.total !== "number") return null;
      return (
        <div className="flex items-baseline gap-2">
          <span className="nums text-xl font-semibold text-ink">≈ {num(r.total)}</span>
          <span className="text-[12px] text-muted">members</span>
          {typeof r.active === "number" && r.active > 0 && (
            <span className="text-[12px] text-faint">· {num(r.active)} active</span>
          )}
        </div>
      );
    }
    case "quote_budget_floor": {
      if (!r?.min_daily && !r?.min_total) return null;
      return (
        <div className="min-w-44 space-y-1.5">
          {money(r.min_daily) && (
            <Stat
              label="Min / day"
              value={
                <span className="inline-flex items-center gap-1.5">
                  {money(r.min_daily)}
                  {r.source && <Tag tone={r.source === "live" ? "brand" : "muted"}>{r.source}</Tag>}
                </span>
              }
            />
          )}
          {money(r.min_total) && <Stat label="Min total" value={money(r.min_total)} />}
          {money(r.quoted_daily) && (
            <div className="text-[11px] text-faint">LinkedIn quoted {money(r.quoted_daily)}</div>
          )}
        </div>
      );
    }
    case "list_recent_posts": {
      if (!Array.isArray(r) || r.length === 0) return null;
      return (
        <div className="space-y-1.5">
          {r.slice(0, 8).map((p) => (
            <div key={p.urn} className="flex items-start gap-2">
              <Tag>{p.media_type ?? "post"}</Tag>
              <span className="line-clamp-2 text-[12px] text-ink">{p.text}</span>
            </div>
          ))}
          {r.length > 8 && <div className="text-[11px] text-faint">+{r.length - 8} more</div>}
        </div>
      );
    }
    case "list_targeting_options":
    case "search_targeting": {
      if (!Array.isArray(r)) return null;
      if (r.length === 0) return <span className="text-faint">No matches</span>;
      return <Chips items={r} />;
    }
    case "preview_targeting": {
      // Be transparent: show the actual facets being targeted (readable names from
      // the request args), marking any value LinkedIn could not resolve.
      const aud = (args?.audience ?? {}) as Record<string, unknown>;
      const FACETS: [string, string][] = [
        ["geos", "Locations"],
        ["seniorities", "Seniorities"],
        ["job_functions", "Functions"],
        ["industries", "Industries"],
        ["titles", "Titles"],
        ["skills", "Skills"],
        ["company_sizes", "Company sizes"],
      ];
      const unresolved = new Set(
        (r?.unresolved ? (Object.values(r.unresolved).flat() as unknown[]) : []).map(String),
      );
      const rows = FACETS.filter(
        ([k]) => Array.isArray(aud[k]) && (aud[k] as unknown[]).length > 0,
      ).map(([k, label]) => ({ label, values: (aud[k] as unknown[]).map(String) }));
      if (rows.length === 0) return null;
      return (
        <div className="min-w-52 space-y-2">
          {rows.map((row) => (
            <div key={row.label}>
              <div className="mb-1 text-[11px] uppercase tracking-wide text-faint">{row.label}</div>
              <div className="flex flex-wrap gap-1">
                {row.values.map((v, i) => {
                  const bad = unresolved.has(v);
                  return (
                    <span
                      key={i}
                      className={`rounded-md px-1.5 py-0.5 text-[11px] ring-1 ${
                        bad ? "text-faint line-through ring-line" : "bg-surface text-ink ring-line"
                      }`}
                    >
                      {v}
                    </span>
                  );
                })}
              </div>
            </div>
          ))}
          {unresolved.size > 0 && (
            <div className="text-[11px] text-faint">
              Struck-through values matched nothing on LinkedIn.
            </div>
          )}
        </div>
      );
    }
    case "describe_platform": {
      if (!r || typeof r !== "object") return null;
      const b = r.budget ?? {};
      const cur = r.currency ?? "";
      return (
        <div className="min-w-52 space-y-1.5">
          {r.currency && <Stat label="Currency" value={r.currency} />}
          {b.min_total && <Stat label="Min budget" value={`${b.min_total} ${cur}`} />}
          {b.min_daily && <Stat label="Min / day" value={`${b.min_daily} ${cur}`} />}
          {r.audience?.min_size && (
            <Stat label="Audience floor" value={num(Number(r.audience.min_size))} />
          )}
          {Array.isArray(r.objectives) && (
            <div className="pt-0.5">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-faint">Objectives</div>
              <Chips items={r.objectives} />
            </div>
          )}
        </div>
      );
    }
    case "create_draft": {
      if (!r?.created) return null;
      return (
        <div className="text-[12px] text-ink">
          Created{" "}
          {r.campaign_id && <span className="nums text-muted">· group {r.campaign_id}</span>}
        </div>
      );
    }
    default:
      return null;
  }
}

/** snake_case / camelCase -> "Sentence case" for result keys. */
function prettyKey(k: string): string {
  const spaced = k.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
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

/** Generic fallback: lists become chip clouds, objects become labelled rows. */
function ResultNode({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-faint">-</span>;
  if (typeof value === "boolean") return <Bool value={value} />;
  if (typeof value === "number")
    return <span className="nums text-ink">{num(value)}</span>;
  if (typeof value === "string")
    return <span className="whitespace-pre-wrap break-words text-ink">{value}</span>;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-faint">none</span>;
    const allScalar = value.every((v) => v === null || typeof v !== "object");
    if (allScalar) return <Chips items={value} max={24} />;
    return (
      <div className="space-y-1.5">
        {value.map((v, i) => (
          <div key={i} className="rounded-md border border-line bg-surface/60 p-2">
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
          <div key={k} className={nested ? "flex flex-col gap-1" : "flex items-start gap-2"}>
            <span className="shrink-0 text-[11px] uppercase tracking-wide text-faint">
              {prettyKey(k)}
            </span>
            <div className={`min-w-0 flex-1 text-[12px] ${nested ? "border-l border-line/70 pl-2.5" : ""}`}>
              <ResultNode value={v} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** One agent tool step. Hovering the finished row reveals a compact, human-friendly
 *  summary of its result in a floating card (portaled, so it never shifts the
 *  conversation or gets clipped). */
export function ToolStep({
  name,
  args,
  summary,
  result,
  status,
  count,
}: {
  name: string;
  args: ToolArgs;
  summary: string | null;
  result?: unknown;
  status?: string;
  count: number;
}) {
  const rowRef = useRef<HTMLButtonElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  const timer = useRef<number | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const done = summary !== null;
  // A tool that raised comes back with status "error" - flag the step in red instead
  // of giving a failed call a green tick.
  const errored = done && status === "error";
  const hasResult = done && result !== undefined && result !== null && result !== "";

  const clearTimer = () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  };
  // Anchor the card just past the END of the row's label text - a fixed spot, not the
  // cursor (the row is full-width, so its right edge would fling the card to the screen
  // edge). Sitting right after the words ties it to that step and stays an easy
  // hover-hop away.
  const WIDTH = 340;
  const open = () => {
    clearTimer();
    const row = rowRef.current;
    if (!row || !hasResult) return;
    const r = row.getBoundingClientRect();
    const anchorRight = (labelRef.current ?? row).getBoundingClientRect().right;
    let left = anchorRight + 14;
    if (left + WIDTH > window.innerWidth - 10)
      left = Math.max(10, window.innerWidth - WIDTH - 10);
    const top = Math.min(Math.max(10, r.top - 4), window.innerHeight - 120);
    setPos({ top, left });
  };
  // Delay the close so the mouse can travel from the row into the card without it
  // vanishing - then it stays open while hovered, so you can read or copy.
  const scheduleClose = () => {
    clearTimer();
    timer.current = window.setTimeout(() => setPos(null), 180);
  };
  useEffect(() => () => clearTimer(), []);

  const friendly = hasResult ? summarize(name, result, args) : null;

  return (
    <div className="pl-1">
      <button
        ref={rowRef}
        type="button"
        onMouseEnter={open}
        onMouseLeave={scheduleClose}
        onFocus={open}
        onBlur={scheduleClose}
        className={`group -ml-1 flex w-fit items-center gap-2.5 rounded-md px-1 py-0.5 text-left text-[13px] ${
          hasResult ? "cursor-help hover:bg-paper/70" : "cursor-default"
        }`}
      >
        {!done ? (
          <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-brand/25 border-t-brand" />
        ) : errored ? (
          <span className="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full bg-red-500/15 text-[9px] font-bold text-red-600">
            ✕
          </span>
        ) : (
          <span className="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full bg-brand/15 text-[9px] text-brand">
            ✓
          </span>
        )}
        <span
          ref={labelRef}
          className={
            errored
              ? "text-red-700/90 group-hover:text-red-700"
              : "text-muted group-hover:text-ink"
          }
        >
          {toolLabel(name, args)}
        </span>
        {count > 1 && (
          <span className="rounded bg-paper px-1 text-[11px] text-faint ring-1 ring-line">
            ×{count}
          </span>
        )}
      </button>

      {pos &&
        hasResult &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            onMouseEnter={clearTimer}
            onMouseLeave={scheduleClose}
            style={{ position: "fixed", top: pos.top, left: pos.left, width: WIDTH, zIndex: 60 }}
            className="rounded-lg border border-line bg-paper shadow-[0_10px_34px_-12px_rgba(13,16,14,0.45)]"
          >
            <div className="flex items-center justify-between border-b border-line/70 px-3 py-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-faint">
                {toolLabel(name, args)}
              </span>
              <span className="nums text-[10px] text-faint">{name}</span>
            </div>
            <div className="max-h-80 overflow-auto p-3 text-[12px] leading-relaxed">
              {friendly ?? <ResultNode value={result} />}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
