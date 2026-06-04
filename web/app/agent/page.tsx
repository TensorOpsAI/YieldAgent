"use client";

/* eslint-disable @typescript-eslint/no-explicit-any */
import { useRef, useState } from "react";
import { streamChat, streamResume, type ChatEvent } from "@/lib/chat";
import { ProposalCard } from "@/components/ProposalCard";

type Item =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; name: string; summary: string | null }
  | { kind: "proposal"; campaign: any }
  | { kind: "created"; result: any };

const MODEL_PRESETS = [
  "gemini-3.1-pro-preview",
  "gemini-2.5-flash",
  "gpt-4o",
  "gpt-4o-mini",
  "claude-3-5-sonnet-latest",
];

export default function AgentConsole() {
  const [items, setItems] = useState<Item[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [awaiting, setAwaiting] = useState(false);
  const [model, setModel] = useState(MODEL_PRESETS[0]);
  const threadId = useRef<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

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
        push({ kind: "tool", name: ev.data.name, summary: null });
        break;
      case "tool_result":
        setItems((prev) => {
          const idx = [...prev]
            .reverse()
            .findIndex((it) => it.kind === "tool" && it.summary === null);
          if (idx === -1) return prev;
          const real = prev.length - 1 - idx;
          const copy = [...prev];
          copy[real] = { kind: "tool", name: ev.data.name, summary: ev.data.summary };
          return copy;
        });
        break;
      case "proposal":
        push({ kind: "proposal", campaign: ev.data.campaign });
        setAwaiting(true);
        break;
      case "created":
        push({ kind: "created", result: ev.data.result });
        break;
      case "error":
        push({ kind: "assistant", text: `⚠️ ${ev.data.message}` });
        break;
    }
    scroll();
  }

  async function consume(gen: AsyncGenerator<ChatEvent>) {
    setBusy(true);
    try {
      for await (const ev of gen) handle(ev);
    } catch {
      push({ kind: "assistant", text: "⚠️ connection error — is the API running?" });
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    push({ kind: "user", text });
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
      <div className="flex items-center gap-2 border-b border-gray-200 bg-white px-6 py-2">
        <label className="text-xs text-gray-500">Model</label>
        <input
          list="model-presets"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="w-64 rounded-md border border-gray-300 px-2 py-1 text-xs outline-none focus:border-emerald-500"
        />
        <datalist id="model-presets">
          {MODEL_PRESETS.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        <span className="text-[11px] text-gray-400">
          switches per message · key required per provider
        </span>
      </div>
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-auto p-6">
        {items.length === 0 && (
          <div className="text-sm text-gray-400">
            Describe the campaign you want to create — e.g. &ldquo;brand awareness
            for founders &amp; CTOs in New York and London, large companies&rdquo;.
          </div>
        )}
        {items.map((it, i) => {
          if (it.kind === "user")
            return (
              <div key={i} className="text-right">
                <div className="inline-block max-w-[75%] whitespace-pre-wrap rounded-2xl bg-emerald-600 px-4 py-2 text-sm text-white">
                  {it.text}
                </div>
              </div>
            );
          if (it.kind === "assistant")
            return (
              <div key={i}>
                <div className="inline-block max-w-[75%] whitespace-pre-wrap rounded-2xl border border-gray-200 bg-white px-4 py-2 text-sm text-gray-900">
                  {it.text || "…"}
                </div>
              </div>
            );
          if (it.kind === "tool")
            return (
              <div key={i} className="text-xs text-gray-500">
                <span className="font-mono">⚙ {it.name}</span>
                {it.summary === null ? (
                  <span className="text-gray-400"> …</span>
                ) : (
                  <span className="text-gray-400"> → {it.summary}</span>
                )}
              </div>
            );
          if (it.kind === "proposal")
            return (
              <ProposalCard
                key={i}
                campaign={it.campaign}
                awaiting={awaiting && i === items.length - 1}
                onApprove={() => decide(true)}
                onReject={() => decide(false)}
              />
            );
          return (
            <div
              key={i}
              className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
            >
              ✓ Draft created.{" "}
              {it.result?.stub ? "(M1 stub — not yet on LinkedIn.)" : ""}
            </div>
          );
        })}
      </div>

      <div className="flex gap-2 border-t border-gray-200 bg-white p-4">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={awaiting ? "Approve or reject the draft above…" : "Message the agent…"}
          disabled={busy}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 disabled:bg-gray-50"
        />
        <button
          onClick={send}
          disabled={busy}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {busy ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
