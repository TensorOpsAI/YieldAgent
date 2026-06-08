"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Replace em/en dashes with a plain hyphen so the UI never shows them, whatever
 *  the model emits. The system prompt also asks models to avoid them; this is the
 *  guarantee on top of that. */
export function sanitizeDashes(s: string): string {
  return s.replace(/[—–]/g, "-");
}

/** Render model/assistant text as Markdown with compact, on-brand styling.
 *  Self-contained: element styles are mapped here, no global prose stylesheet. */
export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        ul: ({ children }) => (
          <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
        ),
        li: ({ children }) => <li className="pl-0.5">{children}</li>,
        strong: ({ children }) => (
          <strong className="font-semibold text-ink">{children}</strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="text-brand-strong underline underline-offset-2"
          >
            {children}
          </a>
        ),
        code: ({ children }) => (
          <code className="nums rounded bg-paper px-1 py-0.5 text-[13px] ring-1 ring-line">
            {children}
          </code>
        ),
        h1: ({ children }) => <div className="mb-1 mt-2 font-semibold first:mt-0">{children}</div>,
        h2: ({ children }) => <div className="mb-1 mt-2 font-semibold first:mt-0">{children}</div>,
        h3: ({ children }) => <div className="mb-1 mt-2 font-semibold first:mt-0">{children}</div>,
      }}
    >
      {sanitizeDashes(children)}
    </ReactMarkdown>
  );
}
