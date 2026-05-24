import { NextResponse } from "next/server";

import { providerStatuses } from "../../../lib/connections";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ providers: await providerStatuses() });
}
