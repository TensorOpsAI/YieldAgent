import { API_BASE } from "./api";

// Mirrors the backend SSE contract (api/routes/chat.py).
export type ChatEvent =
  | { event: "thread"; data: { thread_id: string } }
  | { event: "token"; data: { text: string } }
  | { event: "tool_call"; data: { name: string; args: unknown } }
  | { event: "tool_result"; data: { name: string; summary: string } }
  | { event: "proposal"; data: { campaign: unknown } }
  | { event: "created"; data: { result: unknown } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, never> };

function parseSse(chunk: string): ChatEvent | null {
  let event = "message";
  let data = "";
  // SSE lines may end with \n or \r\n (sse-starlette emits \r\n) — tolerate both.
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

async function* streamSSE(
  path: string,
  body: Record<string, unknown>,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.body) throw new Error(`No response body from ${path}`);

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

/** Start a chat turn. `model` overrides the backend default for this request. */
export function streamChat(message: string, threadId?: string, model?: string) {
  return streamSSE("/api/chat", { message, thread_id: threadId, model });
}

/** Resume a paused turn after the operator approves/rejects a proposal. */
export function streamResume(
  threadId: string,
  approved: boolean,
  reason?: string,
  model?: string,
) {
  return streamSSE("/api/chat/resume", {
    thread_id: threadId,
    approved,
    reason,
    model,
  });
}
