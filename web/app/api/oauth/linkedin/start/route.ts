import crypto from "node:crypto";
import { NextResponse } from "next/server";

import {
  appBaseUrl,
  getProviderConfig,
  linkedinRedirectUri,
  linkedinScopes,
  providerSetup
} from "../../../../../lib/connections";

export const runtime = "nodejs";

export async function GET() {
  const setup = (await providerSetup()).linkedin;
  const stored = await getProviderConfig("linkedin");
  const clientId = stored?.clientId ?? process.env.LINKEDIN_CLIENT_ID;
  if (!setup.configured || !clientId) {
    return NextResponse.redirect(
      `${appBaseUrl()}/?connection_error=${encodeURIComponent(
        `LinkedIn setup missing: ${setup.setupItems.join(", ")}`
      )}`
    );
  }

  const state = crypto.randomBytes(24).toString("base64url");
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: linkedinRedirectUri(),
    state,
    scope: linkedinScopes().join(" ")
  });
  const response = NextResponse.redirect(
    `https://www.linkedin.com/oauth/v2/authorization?${params.toString()}`
  );

  response.cookies.set("yieldagent_linkedin_oauth_state", state, {
    httpOnly: true,
    maxAge: 60 * 10,
    path: "/",
    sameSite: "lax",
    secure: appBaseUrl().startsWith("https://")
  });

  return response;
}
