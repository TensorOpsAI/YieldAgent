import { API_BASE } from "./api";

// Mirrors the backend SSE contract (api/routes/chat.py). Only the `token` and
// `done` events exist in M0; tool_call/proposal/created arrive with the M1 agent.
export type ChatEvent =
  | { event: "thread"; data: { thread_id: string } }
  | { event: "token"; data: { text: string } }
  | { event: "tool_call"; data: { name: string; args: unknown } }
  | { event: "tool_result"; data: { name: string; summary: string } }
  | { event: "proposal"; data: unknown }
  | { event: "created"; data: unknown }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, never> };

function parseSse(chunk: string): ChatEvent | null {
  let event = "message";
  let data = "";
  // SSE lines may end with \n or \r\n depending on the server (sse-starlette
  // emits \r\n), so tolerate both.
  for (const line of chunk.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) } as ChatEvent;
  } catch {
    return null;
  }
}

/** Stream a chat turn from the backend, yielding typed SSE events. */
export async function* streamChat(
  message: string,
  threadId?: string,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!res.body) throw new Error("No response body from /api/chat");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Events are separated by a blank line — \n\n or \r\n\r\n.
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const ev = parseSse(part);
      if (ev) yield ev;
    }
  }
}
