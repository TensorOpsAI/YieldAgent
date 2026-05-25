import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

import { NextRequest, NextResponse } from "next/server";

import { getProviderConfig } from "../../../../../lib/connections";

export const runtime = "nodejs";

// Leads are persisted to a local JSONL file under the existing data dir so
// self-hosted operators have an audit trail without bringing up a database.
const DATA_DIR =
  process.env.YIELDAGENT_WEB_DATA_DIR ??
  path.join(process.cwd(), ".yieldagent");
const LEAD_LOG = path.join(DATA_DIR, "linkedin-leads.jsonl");

const linkedInClientSecret = async (): Promise<string | null> => {
  const stored = await getProviderConfig("linkedin");
  return stored?.clientSecret ?? process.env.LINKEDIN_CLIENT_SECRET ?? null;
};

const hexHmac = (message: string, secret: string) =>
  crypto.createHmac("sha256", secret).update(message).digest("hex");

// LinkedIn's challenge handshake: respond within 3s with
//   { challengeCode, challengeResponse: hex(HMACSHA256(challengeCode, clientSecret)) }
export async function GET(request: NextRequest) {
  const challengeCode = request.nextUrl.searchParams.get("challengeCode");
  if (!challengeCode) {
    return NextResponse.json(
      { ok: false, error: "missing challengeCode" },
      { status: 400 }
    );
  }
  const secret = await linkedInClientSecret();
  if (!secret) {
    return NextResponse.json(
      {
        ok: false,
        error:
          "LinkedIn client secret is not configured. Set it via Connections → Setup before subscribing this webhook."
      },
      { status: 503 }
    );
  }
  const challengeResponse = hexHmac(challengeCode, secret);
  return NextResponse.json({ challengeCode, challengeResponse });
}

// Lead push: LinkedIn POSTs the notification JSON with
//   X-LI-Signature: hmacsha256=<hex(HMACSHA256(rawBody, clientSecret))>
// We verify the signature over the raw body, then append the event to the
// lead log. Production setups should swap this file write for a CRM push.
export async function POST(request: NextRequest) {
  const signatureHeader = request.headers.get("x-li-signature") ?? "";
  const expectedPrefix = "hmacsha256=";
  if (!signatureHeader.startsWith(expectedPrefix)) {
    return NextResponse.json(
      { ok: false, error: "missing or malformed X-LI-Signature" },
      { status: 401 }
    );
  }
  const secret = await linkedInClientSecret();
  if (!secret) {
    return NextResponse.json(
      { ok: false, error: "LinkedIn client secret is not configured" },
      { status: 503 }
    );
  }

  const rawBody = await request.text();
  const provided = signatureHeader.slice(expectedPrefix.length);
  const computed = hexHmac(rawBody, secret);
  const a = Buffer.from(provided, "hex");
  const b = Buffer.from(computed, "hex");
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    return NextResponse.json(
      { ok: false, error: "signature mismatch" },
      { status: 401 }
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(rawBody);
  } catch {
    return NextResponse.json(
      { ok: false, error: "body is not valid JSON" },
      { status: 400 }
    );
  }

  const entry = {
    receivedAt: new Date().toISOString(),
    event: parsed
  };
  await fs.mkdir(DATA_DIR, { recursive: true });
  await fs.appendFile(LEAD_LOG, `${JSON.stringify(entry)}\n`, "utf8");

  return NextResponse.json({ ok: true });
}
