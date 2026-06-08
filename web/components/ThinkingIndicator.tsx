"use client";

import { useEffect, useState } from "react";

// Claude-Code-style rotating status words so a busy agent never looks frozen,
// especially on slower models. Mixes whimsy with domain-relevant phrases.
const PHRASES = [
  "Thinking",
  "Cooking",
  "Pondering",
  "Consulting LinkedIn",
  "Sizing the audience",
  "Crunching targeting",
  "Drafting copy",
  "Computing reach",
  "Assembling the draft",
  "Wrangling facets",
  "Checking the taxonomy",
  "Noodling",
  "Reticulating splines",
  "Lining up the ads",
];

export function ThinkingIndicator() {
  const [i, setI] = useState(0);
  useEffect(() => {
    // Start somewhere random so each thinking session feels different.
    setI(Math.floor(Math.random() * PHRASES.length));
    const id = setInterval(() => setI((n) => (n + 1) % PHRASES.length), 2200);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="flex items-center gap-2.5 pl-1 text-[13px] text-muted">
      <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-brand/25 border-t-brand" />
      <span className="animate-pulse">{PHRASES[i]}…</span>
    </div>
  );
}
