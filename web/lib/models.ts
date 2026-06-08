// Display metadata for the model picker: a short speed/capability tag and a
// one-line blurb per model. Keyed by model id; unknown ids fall back to no tag.
export type ModelMeta = { tag: ModelTag; blurb: string };
export type ModelTag = "Smart" | "Balanced" | "Fast" | "";

const META: Record<string, ModelMeta> = {
  // Gemini
  "gemini-3.1-pro-preview": { tag: "Smart", blurb: "Deepest reasoning Gemini" },
  "gemini-3.5-flash": { tag: "Balanced", blurb: "Fast & reliable — recommended" },
  "gemini-3.1-flash-lite": { tag: "Fast", blurb: "Lightest, quickest Gemini" },
  // OpenAI
  "gpt-5.5": { tag: "Smart", blurb: "A new class of intelligence for pro work" },
  "gpt-5.4": { tag: "Balanced", blurb: "Intelligence at scale for agents" },
  "gpt-5.4-mini": { tag: "Fast", blurb: "Faster, cost-efficient GPT-5.4" },
  // Anthropic
  "claude-opus-4-8": { tag: "Smart", blurb: "Most capable Claude" },
  "claude-sonnet-4-6": { tag: "Balanced", blurb: "Balanced speed and depth" },
  "claude-haiku-4-5": { tag: "Fast", blurb: "Fastest Claude" },
};

export function modelMeta(id: string): ModelMeta {
  return META[id] ?? { tag: "", blurb: "" };
}

// Badge styling per tag — stays within the emerald/neutral/amber palette.
export const TAG_STYLES: Record<Exclude<ModelTag, "">, string> = {
  Smart: "bg-brand-soft text-brand-strong ring-brand/20",
  Balanced: "bg-paper text-muted ring-line",
  Fast: "bg-amber-50 text-amber-700 ring-amber-200",
};
