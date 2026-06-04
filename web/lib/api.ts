export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type Provider = {
  id: string;
  label: string;
  connected: boolean;
  reason: string | null;
  models: string[];
};

/** LLM providers with live connection state + usable models. */
export async function fetchProviders(test = false): Promise<Provider[]> {
  const res = await fetch(`${API_BASE}/api/providers${test ? "?test=1" : ""}`);
  if (!res.ok) throw new Error("Failed to fetch providers");
  return res.json();
}

export type AdPlatform = {
  platform: string;
  connected: boolean;
  can_create: boolean;
};

/** Ad platforms and whether campaigns can be created on each. */
export async function fetchAdPlatforms(): Promise<AdPlatform[]> {
  const res = await fetch(`${API_BASE}/api/ad-platforms`);
  if (!res.ok) throw new Error("Failed to fetch ad platforms");
  return res.json();
}
