import { NextResponse } from "next/server";

import {
  decryptCredential,
  getStoredConnection,
  listLinkedInAdAccounts,
  providerStatuses,
  saveConnection
} from "../../../../../lib/connections";

export const runtime = "nodejs";

export async function POST() {
  const connection = await getStoredConnection("linkedin");
  if (!connection) {
    return NextResponse.json({ ok: false, error: "LinkedIn Ads is not connected" }, { status: 404 });
  }

  try {
    const credential = decryptCredential<{ access_token: string }>(connection.encryptedCredential);
    const accounts = await listLinkedInAdAccounts(credential.access_token);
    await saveConnection({
      ...connection,
      accounts,
      lastValidatedAt: new Date().toISOString()
    });

    return NextResponse.json({ ok: true, providers: await providerStatuses() });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "LinkedIn test failed" },
      { status: 502 }
    );
  }
}
