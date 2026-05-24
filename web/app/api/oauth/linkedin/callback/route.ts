import { NextRequest, NextResponse } from "next/server";

import {
  appBaseUrl,
  encryptCredential,
  exchangeLinkedInCode,
  linkedinScopes,
  listLinkedInAdAccounts,
  saveConnection
} from "../../../../../lib/connections";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const error = url.searchParams.get("error");
  if (error) {
    return NextResponse.redirect(`${appBaseUrl()}/?connection_error=${encodeURIComponent(error)}`);
  }

  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const expectedState = request.cookies.get("yieldagent_linkedin_oauth_state")?.value;

  if (!code || !state || !expectedState || state !== expectedState) {
    return NextResponse.redirect(
      `${appBaseUrl()}/?connection_error=${encodeURIComponent("LinkedIn OAuth state validation failed")}`
    );
  }

  try {
    const token = await exchangeLinkedInCode(code);
    const accounts = await listLinkedInAdAccounts(token.access_token);
    const now = new Date();
    const expiresAt = token.expires_in
      ? new Date(now.getTime() + token.expires_in * 1000).toISOString()
      : undefined;

    await saveConnection({
      platform: "linkedin",
      connectedAt: now.toISOString(),
      lastValidatedAt: now.toISOString(),
      expiresAt,
      scopes: token.scope?.split(/\s+/).filter(Boolean) ?? linkedinScopes(),
      encryptedCredential: encryptCredential(token),
      accounts,
      selectedAccountId: accounts[0]?.id
    });

    const response = NextResponse.redirect(`${appBaseUrl()}/?connected=linkedin`);
    response.cookies.delete("yieldagent_linkedin_oauth_state");
    return response;
  } catch (callbackError) {
    return NextResponse.redirect(
      `${appBaseUrl()}/?connection_error=${encodeURIComponent(
        callbackError instanceof Error ? callbackError.message : "LinkedIn callback failed"
      )}`
    );
  }
}
