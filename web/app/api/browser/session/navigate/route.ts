import { NextRequest, NextResponse } from "next/server";

import { navigateBrowserSession } from "../../../../../lib/browser-sessions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as { sessionId?: string; url?: string };
  if (!body.sessionId || !body.url) {
    return NextResponse.json(
      { ok: false, error: "sessionId and url are required" },
      { status: 400 }
    );
  }

  try {
    const session = await navigateBrowserSession(body.sessionId, body.url);
    return NextResponse.json({ ok: true, session });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Unable to navigate browser session" },
      { status: 400 }
    );
  }
}
