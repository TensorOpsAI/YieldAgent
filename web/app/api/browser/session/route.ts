import { NextRequest, NextResponse } from "next/server";

import {
  closeBrowserSession,
  defaultBrowserUrl,
  getActiveBrowserSession,
  openBrowserSession,
  refreshBrowserSession
} from "../../../../lib/browser-sessions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({ session: getActiveBrowserSession() });
}

export async function POST(request: NextRequest) {
  let body: { url?: string; reasonBrowserNeeded?: string } = {};
  try {
    body = (await request.json()) as typeof body;
  } catch {
    body = {};
  }

  try {
    const session = await openBrowserSession({
      url: body.url || defaultBrowserUrl(),
      reasonBrowserNeeded: body.reasonBrowserNeeded
    });
    return NextResponse.json({ ok: true, session });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Unable to open browser session" },
      { status: 400 }
    );
  }
}

export async function PATCH(request: NextRequest) {
  const body = (await request.json()) as { sessionId?: string };
  if (!body.sessionId) {
    return NextResponse.json({ ok: false, error: "sessionId is required" }, { status: 400 });
  }

  try {
    const session = await refreshBrowserSession(body.sessionId);
    return NextResponse.json({ ok: true, session });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Unable to refresh browser session" },
      { status: 400 }
    );
  }
}

export async function DELETE(request: NextRequest) {
  const sessionId = request.nextUrl.searchParams.get("sessionId");
  if (!sessionId) {
    return NextResponse.json({ ok: false, error: "sessionId is required" }, { status: 400 });
  }

  try {
    const session = await closeBrowserSession(sessionId);
    return NextResponse.json({ ok: true, session });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Unable to close browser session" },
      { status: 400 }
    );
  }
}
