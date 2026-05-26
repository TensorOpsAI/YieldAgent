# YieldAgent Agent Rules

When a platform API returns a scope, app-review, partner-program approval, or
authorization error, propose the browser fallback via the existing
`browser.run_playwright_flow` browser-control tool rather than returning the raw
error to the user.

The browser fallback is credential-sensitive. Always show a dry-run preview
first and require explicit operator approval before driving an authenticated
platform UI session.
