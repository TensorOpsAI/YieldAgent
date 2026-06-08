"use client";

import { useEffect, useRef, useState } from "react";
import {
  streamChat,
  streamResume,
  type ChatEvent,
  type Campaign,
  type CreatedResult,
  type Forecast,
  type Previews,
  type Reach,
  type ToolArgs,
} from "@/lib/chat";
import { fetchProviders, type Provider } from "@/lib/api";
import { ProposalCard } from "@/components/ProposalCard";
import { ModelPicker } from "@/components/ModelPicker";
import { ThinkingIndicator } from "@/components/ThinkingIndicator";
import { Markdown } from "@/components/Markdown";
import { ToolStep } from "@/components/ToolStep";

type Item =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | {
      kind: "tool";
      name: string;
      args: ToolArgs;
      summary: string | null;
      result?: unknown;
      count: number;
    }
  | {
      kind: "proposal";
      campaign: Campaign;
      unresolved: Record<string, string[]>;
      previews: Previews;
      reach: Reach;
      forecast: Forecast;
    }
  | { kind: "created"; result: CreatedResult };

export default function AgentConsole() {
  const [items, setItems] = useState<Item[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [awaiting, setAwaiting] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [model, setModel] = useState("gemini-3.5-flash");
  const threadId = useRef<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetchProviders()
      .then((ps) => {
        setProviders(ps);
        // Always default to Gemini flash; otherwise the last-used model, else first.
        const available = ps.filter((p) => p.connected).flatMap((p) => p.models);
        const saved =
          typeof window !== "undefined" ? window.localStorage.getItem("ya_model") : null;
        const preferred =
          available.find((m) => m === "gemini-3.5-flash") ??
          (saved && available.includes(saved) ? saved : undefined) ??
          available[0];
        if (preferred) setModel(preferred);
      })
      .catch(() => undefined);
  }, []);

  // Keep the composer focused so the operator can always just type (no re-click).
  useEffect(() => {
    if (!busy && model) inputRef.current?.focus();
  }, [busy, model]);

  // Auto-scroll to the newest message / tool step whenever the thread grows.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight });
  }, [items]);

  // Grow the composer with its content (Shift+Enter newlines), up to a cap.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const chooseModel = (m: string) => {
    setModel(m);
    if (typeof window !== "undefined") window.localStorage.setItem("ya_model", m);
  };

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
              { ...last, count: last.count + 1, summary: null, result: undefined },
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
          // Match the most recent unfilled row for THIS tool by name - two
          // different tools can be in flight at once (the collapse only merges
          // consecutive identical names), so position alone could mis-assign.
          const idx = [...prev]
            .reverse()
            .findIndex(
              (it) =>
                it.kind === "tool" &&
                it.summary === null &&
                it.name === ev.data.name,
            );
          if (idx === -1) return prev;
          const real = prev.length - 1 - idx;
          const copy = [...prev];
          const t = copy[real] as Extract<Item, { kind: "tool" }>;
          copy[real] = { ...t, summary: ev.data.summary, result: ev.data.result };
          return copy;
        });
        break;
      case "proposal":
        push({
          kind: "proposal",
          campaign: ev.data.campaign,
          unresolved: ev.data.unresolved ?? {},
          previews: ev.data.previews ?? {},
          reach: ev.data.reach ?? {},
          forecast: ev.data.forecast ?? {},
        });
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
    // The graph is paused awaiting approval iff THIS turn ended on a proposal.
    // Deriving it here (instead of a sticky flag) means an error or a normal
    // reply correctly clears it - so the next message can't mis-route to resume
    // a thread that isn't actually paused.
    let endedOnProposal = false;
    try {
      for await (const ev of gen) {
        if (ev.event === "proposal") endedOnProposal = true;
        handle(ev);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "connection error";
      push({ kind: "assistant", text: `⚠ ${msg}. Is the API running?` });
    } finally {
      setBusy(false);
      setAwaiting(endedOnProposal);
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy || !model) return;
    setInput("");
    push({ kind: "user", text });
    // If a proposal is awaiting a decision, the graph is paused inside
    // propose_campaign - a fresh run() would corrupt its history. Route the
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
                  Just tell me in plain language. I&rsquo;ll confirm the platform,
                  learn its rules, and ask for whatever it needs before drafting.
                </p>
              </div>
              <div className="mx-auto mt-6 max-w-md rounded-xl border border-line bg-surface p-4">
                <div className="eyebrow mb-2">How it works</div>
                <ul className="space-y-1.5 text-[14px] text-muted">
                  {[
                    "Tell me what you want to advertise",
                    "I confirm the platform and read its requirements",
                    "I draft it; you review every field and approve",
                  ].map((step, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="nums text-brand">{i + 1}</span>
                      <span>{step}</span>
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
                  <div className="rise max-w-[85%] rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-2.5 text-[15px] leading-relaxed text-ink">
                    <Markdown>{it.text || "…"}</Markdown>
                  </div>
                </div>
              );
            if (it.kind === "tool")
              return (
                <ToolStep
                  key={i}
                  name={it.name}
                  args={it.args}
                  summary={it.summary}
                  result={it.result}
                  count={it.count}
                />
              );
            if (it.kind === "proposal")
              return (
                <ProposalCard
                  key={i}
                  campaign={it.campaign}
                  unresolved={it.unresolved}
                  previews={it.previews}
                  reach={it.reach}
                  forecast={it.forecast}
                  awaiting={awaiting && i === items.length - 1}
                  onApprove={() => decide(true)}
                  onReject={() => decide(false)}
                />
              );
            return (
              <div
                key={i}
                className="rise rounded-xl border border-brand/30 bg-brand-soft px-4 py-3.5"
              >
                <div className="flex items-center gap-2 text-[14px] font-semibold text-brand-strong">
                  <span className="grid h-5 w-5 place-items-center rounded-full bg-brand text-[11px] text-white">
                    ✓
                  </span>
                  Draft created on LinkedIn
                </div>
                <p className="mt-1.5 pl-7 text-[13px] leading-relaxed text-muted">
                  Saved as a <span className="font-medium text-ink">DRAFT</span>. It
                  can&rsquo;t spend until you activate it manually in Campaign Manager.
                  {it.result?.campaign_id && (
                    <span className="nums"> Group {it.result.campaign_id}.</span>
                  )}
                </p>
                {it.result?.lcm_url && (
                  <a
                    href={it.result.lcm_url}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-7 mt-2.5 inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-strong"
                  >
                    Open in Campaign Manager →
                  </a>
                )}
              </div>
            );
          })}

          {busy &&
            (() => {
              const last = items[items.length - 1];
              const toolInFlight = last?.kind === "tool" && last.summary === null;
              // A tool already shows its own spinner; otherwise show the rotating
              // "Thinking…" so slow models never look frozen between tool calls.
              return toolInFlight ? null : <ThinkingIndicator />;
            })()}
        </div>
      </div>

      {/* Composer */}
      <div className="border-t border-line px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center gap-2">
          <ModelPicker providers={providers} value={model} onChange={chooseModel} />
          <div className="flex flex-1 items-end gap-2 rounded-xl border border-line bg-surface px-2 py-1.5 focus-within:border-brand">
            <textarea
              ref={inputRef}
              value={input}
              rows={1}
              aria-label="Describe your campaign"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                // Enter sends; Shift+Enter inserts a newline. Ignore Enter
                // mid-IME-composition (CJK/diacritics) so it doesn't send early.
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={
                !model
                  ? "Pick a model to start…"
                  : awaiting
                    ? "Approve, reject, or type a change…"
                    : "Describe your campaign…"
              }
              disabled={busy || !model}
              className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-faint disabled:opacity-60"
            />
            <button
              onClick={send}
              disabled={busy || !model}
              aria-label="Send message"
              aria-busy={busy}
              className="shrink-0 rounded-lg bg-brand px-4 py-2 text-[14px] font-medium text-white transition-colors hover:bg-brand-strong disabled:opacity-40"
            >
              {busy ? "…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
