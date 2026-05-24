import { NextRequest, NextResponse } from "next/server";

import {
  type ProviderConfig,
  type ProviderFieldKey,
  type ProviderKey,
  deleteProviderConfig,
  getProviderConfig,
  providerFieldSchema,
  providerStatuses,
  saveProviderConfig
} from "../../../../../lib/connections";

export const runtime = "nodejs";

const isProviderKey = (value: string): value is ProviderKey =>
  value === "linkedin" || value === "meta" || value === "google";

const knownFieldKeys: readonly ProviderFieldKey[] = [
  "clientId",
  "clientSecret",
  "developerToken",
  "loginCustomerId"
];

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ provider: string }> }
) {
  const { provider } = await params;
  if (!isProviderKey(provider)) {
    return NextResponse.json({ ok: false, error: "Unknown provider" }, { status: 404 });
  }

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON body" }, { status: 400 });
  }

  const incoming: ProviderConfig = {};
  for (const key of knownFieldKeys) {
    const value = body[key];
    if (typeof value === "string" && value.trim().length > 0) {
      incoming[key] = value.trim();
    }
  }

  const existing = (await getProviderConfig(provider)) ?? {};
  const merged: ProviderConfig = { ...existing, ...incoming };

  const schema = providerFieldSchema()[provider];
  const missing = schema.fields
    .filter((field) => field.required && !merged[field.key])
    .map((field) => field.label);

  if (missing.length > 0) {
    return NextResponse.json(
      { ok: false, error: `Missing required fields: ${missing.join(", ")}` },
      { status: 400 }
    );
  }

  try {
    await saveProviderConfig(provider, merged);
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : "Failed to save credentials"
      },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true, providers: await providerStatuses() });
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ provider: string }> }
) {
  const { provider } = await params;
  if (!isProviderKey(provider)) {
    return NextResponse.json({ ok: false, error: "Unknown provider" }, { status: 404 });
  }

  try {
    await deleteProviderConfig(provider);
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : "Failed to clear credentials"
      },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true, providers: await providerStatuses() });
}
