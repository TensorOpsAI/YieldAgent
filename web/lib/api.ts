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

export type CampaignRow = {
  id: string;
  created_at: string;
  platform: string;
  name: string;
  objective: string;
  status: string;
  lcm_url: string | null;
  targeting: Record<string, string[]>;
};

export type Summary = { campaigns: number; drafts: number };

export async function fetchCampaigns(): Promise<CampaignRow[]> {
  // no-store: the dashboard must reflect a just-created draft, never a cached list.
  const res = await fetch(`${API_BASE}/api/campaigns`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch campaigns");
  return res.json();
}

export async function fetchSummary(): Promise<Summary> {
  const res = await fetch(`${API_BASE}/api/summary`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch summary");
  return res.json();
}

/** Forget a campaign locally (removes it from the dashboard). Does not touch LinkedIn. */
export async function deleteCampaign(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete campaign");
}
