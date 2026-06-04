"use client";

/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef, useState } from "react";
import { streamChat, streamResume, type ChatEvent } from "@/lib/chat";
import { fetchProviders, type Provider } from "@/lib/api";
import { ProposalCard } from "@/components/ProposalCard";
import { ModelPicker } from "@/components/ModelPicker";

type Item =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; name: string; args: any; summary: string | null; count: number }
  | { kind: "proposal"; campaign: any; unresolved: Record<string, string[]> }
  | { kind: "created"; result: any };

function toolLabel(name: string, args: any): string {
  switch (name) {
    case "list_ad_platforms":
      return "Checking available platforms";
    case "list_seniorities":
      return "Looking up seniority levels";
    case "list_job_functions":
      return "Looking up job functions";
    case "list_company_size_buckets":
      return "Loading company sizes";
    case "search_targeting":
      return `Searching ${args?.facet ?? "targeting"}${
        args?.query ? ` for “${args.query}”` : ""
      }`;
    case "preview_targeting":
      return "Resolving targeting on LinkedIn";
    case "propose_campaign":
      return "Preparing the proposal";
    case "create_linkedin_draft":
      return "Creating the draft on LinkedIn";
    default:
      return name;
  }
}

export default function AgentConsole() {
  const [items, setItems] = useState<Item[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [awaiting, setAwaiting] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [model, setModel] = useState("");
  const threadId = useRef<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  const availableModels = providers
    .filter((p) => p.connected)
    .flatMap((p) => p.models);

  useEffect(() => {
    fetchProviders()
      .then((ps) => {
        setProviders(ps);
        // Default to a sensible model: prefer a fast Gemini, else the first available.
        const available = ps.filter((p) => p.connected).flatMap((p) => p.models);
        const preferred = available.find((m) => m === "gemini-3.5-flash") ?? available[0];
        if (preferred) setModel((m) => m || preferred);
      })
      .catch(() => undefined);
  }, []);

  const push = (item: Item) => setItems((prev) => [...prev, item]);
  const scroll = () =>
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: 1e9 }));

  function handle(ev: ChatEvent) {
    switch (ev.event) {
      case "thread":
        threadId.current = ev.data.thread_id;
        break;
      case "token":
        setItems((prev) => {
          const last = prev[prev.length - 1];
          if (last?.kind === "assistant") {
            return [
              ...prev.slice(0, -1),
              { kind: "assistant", text: last.text + ev.data.text },
            ];
          }
          return [...prev, { kind: "assistant", text: ev.data.text }];
        });
        break;
      case "tool_call":
        setItems((prev) => {
          const last = prev[prev.length - 1];
          // Collapse a repeated tool (some models loop) into one row with a count.
          if (last?.kind === "tool" && last.name === ev.data.name) {
            return [
              ...prev.slice(0, -1),
              { ...last, count: last.count + 1, summary: null },
            ];
          }
          return [
            ...prev,
            { kind: "tool", name: ev.data.name, args: ev.data.args, summary: null, count: 1 },
          ];
        });
        break;
      case "tool_result":
        setItems((prev) => {
          const idx = [...prev]
            .reverse()
            .findIndex((it) => it.kind === "tool" && it.summary === null);
          if (idx === -1) return prev;
          const real = prev.length - 1 - idx;
          const copy = [...prev];
          const t = copy[real] as Extract<Item, { kind: "tool" }>;
          copy[real] = { ...t, summary: ev.data.summary };
          return copy;
        });
        break;
      case "proposal":
        push({
          kind: "proposal",
          campaign: ev.data.campaign,
          unresolved: ev.data.unresolved ?? {},
        });
        setAwaiting(true);
        break;
      case "created":
        push({ kind: "created", result: ev.data.result });
        break;
      case "error":
        push({ kind: "assistant", text: `⚠ ${ev.data.message}` });
        break;
    }
    scroll();
  }

  async function consume(gen: AsyncGenerator<ChatEvent>) {
    setBusy(true);
    try {
      for await (const ev of gen) handle(ev);
    } catch {
      push({ kind: "assistant", text: "⚠ connection error — is the API running?" });
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy || !model) return;
    setInput("");
    push({ kind: "user", text });
    // If a proposal is awaiting a decision, the graph is paused inside
    // propose_campaign — a fresh run() would corrupt its history. Route the
    // typed message as feedback so the agent revises and re-proposes.
    if (awaiting && threadId.current) {
      setAwaiting(false);
      await consume(streamResume(threadId.current, false, text, model));
      return;
    }
    await consume(streamChat(text, threadId.current, model));
  }

  async function decide(approved: boolean) {
    if (!threadId.current) return;
    setAwaiting(false);
    await consume(
      streamResume(threadId.current, approved, approved ? "" : "rejected", model),
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Status bar */}
      <div className="flex items-center gap-3 border-b border-line px-7 py-2.5">
        <span className="inline-flex items-center gap-1.5 rounded-md bg-paper px-2 py-1 text-[12px] font-medium text-ink ring-1 ring-line">
          <span className="h-1.5 w-1.5 rounded-full bg-brand" />
          LinkedIn
        </span>
        <div className="ml-auto flex items-center gap-3 text-[12px]">
          {providers.map((p) => (
            <span key={p.id} title={p.reason ?? "connected"} className="flex items-center gap-1.5">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  p.connected ? "bg-brand" : "bg-faint/40"
                }`}
              />
              <span className={p.connected ? "text-muted" : "text-faint/60"}>
                {p.label}
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* Conversation */}
      <div ref={scrollRef} className="flex-1 overflow-auto">
        <div className="mx-auto max-w-3xl space-y-4 px-6 py-7">
          {items.length === 0 && (
            <div className="mt-10">
              <div className="text-center">
                <div className="font-display text-2xl text-ink">
                  What are we launching?
                </div>
                <p className="mx-auto mt-2 max-w-md text-[14px] text-muted">
                  Just tell me in plain language — no brief needed. I&rsquo;ll ask
                  for anything I&rsquo;m missing before drafting.
                </p>
              </div>
              <div className="mx-auto mt-6 max-w-md rounded-xl border border-line bg-surface p-4">
                <div className="eyebrow mb-2">To create a draft I need</div>
                <ul className="space-y-1.5 text-[14px] text-muted">
                  {[
                    ["Objective", "awareness, leads, engagement…"],
                    ["Budget", "amount + currency, e.g. €5,000"],
                    ["Flight", "start & end dates"],
                    ["Audience", "geos + who to target"],
                    ["Creative", "an existing post, or copy + landing URL"],
                  ].map(([k, v]) => (
                    <li key={k} className="flex gap-2">
                      <span className="text-brand">›</span>
                      <span>
                        <span className="font-medium text-ink">{k}</span>
                        <span className="text-faint"> — {v}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {items.map((it, i) => {
            if (it.kind === "user")
              return (
                <div key={i} className="flex justify-end">
                  <div className="rise max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[15px] text-paper">
                    {it.text}
                  </div>
                </div>
              );
            if (it.kind === "assistant")
              return (
                <div key={i} className="flex justify-start">
                  <div className="rise max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-2.5 text-[15px] leading-relaxed text-ink">
                    {it.text || "…"}
                  </div>
                </div>
              );
            if (it.kind === "tool")
              return (
                <div
                  key={i}
                  className="flex items-center gap-2.5 pl-1 text-[13px]"
                  title={it.summary ?? undefined}
                >
                  {it.summary === null ? (
                    <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-brand/25 border-t-brand" />
                  ) : (
                    <span className="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full bg-brand/15 text-[9px] text-brand">
                      ✓
                    </span>
                  )}
                  <span className="text-muted">{toolLabel(it.name, it.args)}</span>
                  {it.count > 1 && (
                    <span className="rounded bg-paper px-1 text-[11px] text-faint ring-1 ring-line">
                      ×{it.count}
                    </span>
                  )}
                </div>
              );
            if (it.kind === "proposal")
              return (
                <ProposalCard
                  key={i}
                  campaign={it.campaign}
                  unresolved={it.unresolved}
                  awaiting={awaiting && i === items.length - 1}
                  onApprove={() => decide(true)}
                  onReject={() => decide(false)}
                />
              );
            return (
              <div
                key={i}
                className="rise flex items-center gap-2 rounded-xl border border-brand/30 bg-brand-soft px-4 py-3 text-[14px] text-brand-strong"
              >
                <span className="text-base">✓</span>
                <span>
                  Draft created on LinkedIn.{" "}
                  {it.result?.lcm_url ? (
                    <a
                      href={it.result.lcm_url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-semibold underline"
                    >
                      Open in Campaign Manager →
                    </a>
                  ) : it.result?.error ? (
                    <span className="text-amber-700">{it.result.error}</span>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Composer */}
      <div className="border-t border-line px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center gap-2">
          <ModelPicker models={availableModels} value={model} onChange={setModel} />
          <div className="flex flex-1 items-center gap-2 rounded-xl border border-line bg-surface px-2 py-1.5 focus-within:border-brand">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder={
                !model
                  ? "Pick a model to start…"
                  : awaiting
                    ? "Approve, reject, or type a change…"
                    : "Describe your campaign…"
              }
              disabled={busy || !model}
              className="flex-1 bg-transparent px-2 py-1.5 text-[15px] text-ink outline-none placeholder:text-faint disabled:opacity-60"
            />
            <button
              onClick={send}
              disabled={busy || !model}
              className="rounded-lg bg-brand px-4 py-2 text-[14px] font-medium text-white transition-colors hover:bg-brand-strong disabled:opacity-40"
            >
              {busy ? "…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
