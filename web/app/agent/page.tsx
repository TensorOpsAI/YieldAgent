"use client";

import { useRef, useState } from "react";
import { streamChat } from "@/lib/chat";

type Msg = { role: "user" | "assistant"; text: string };

export default function AgentConsole() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((m) => [
      ...m,
      { role: "user", text },
      { role: "assistant", text: "" },
    ]);
    setBusy(true);
    try {
      for await (const ev of streamChat(text)) {
        if (ev.event === "token") {
          const t = ev.data.text;
          setMessages((m) => {
            const copy = [...m];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { role: "assistant", text: last.text + t };
            return copy;
          });
          scrollRef.current?.scrollTo({ top: 1e9 });
        }
      }
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "[connection error — is the API running?]" },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-auto p-6">
        {messages.length === 0 && (
          <div className="text-sm text-gray-400">
            Describe the campaign you want to create…
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : ""}>
            <div
              className={`inline-block max-w-[70%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
                m.role === "user"
                  ? "bg-emerald-600 text-white"
                  : "border border-gray-200 bg-white text-gray-900"
              }`}
            >
              {m.text || (busy ? "…" : "")}
            </div>
          </div>
        ))}
      </div>
      <div className="flex gap-2 border-t border-gray-200 bg-white p-4">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Message the agent…"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />
        <button
          onClick={send}
          disabled={busy}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}
