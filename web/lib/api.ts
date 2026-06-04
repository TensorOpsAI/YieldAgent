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
