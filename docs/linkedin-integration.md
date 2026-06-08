# LinkedIn integration

An MCP server over the LinkedIn Marketing API, plus a thin async HTTP client and the platform-neutral → LinkedIn payload mapping. The web console drives this integration in-process through the LinkedIn connector; any external MCP client can drive it over stdio.

Source: `src/yieldagent/integrations/linkedin/`.

## Hierarchy mapping

LinkedIn's three-level hierarchy lines up cleanly with the YieldAgent domain model — only the naming shifts:

| YieldAgent | LinkedIn       | Notes |
|------------|----------------|---|
| `Campaign` | Campaign Group | Container; carries the rollup budget. |
| `LineItem` | Campaign       | Where targeting, schedule, and budget live. |
| `Ad`       | Creative       | Single-share Sponsored Content; references an existing post or a minted one. |

This means a planned `yieldagent.domain.Campaign` with N `LineItem`s and M `Ad`s becomes one LinkedIn **Campaign Group**, N **Campaigns**, and M **Creatives**.

## Tools exposed

The server is implemented with `FastMCP` and registers a single one-shot tool (see `server.py`):

| Tool | Purpose |
|---|---|
| `publish_draft_campaign` | Create a whole campaign as `DRAFT` in one call: chains create group → one Campaign per `LineItem` (resolving B2B targeting) → one Creative per `Ad` (sponsoring an existing post, or minting a Direct Sponsored Content post). Accepts a serialized `yieldagent.domain.Campaign`. |

It calls `LinkedInClient.assert_account_allowed()` before any write, and rolls back partial work if a later step fails (LinkedIn has no transaction).

The create primitives it chains — `get_ad_account`, `create_campaign_group`, `create_campaign`, `create_creative` — are methods on `LinkedInClient` (`client.py`), not separate MCP tools. Call them directly when embedding the client.

## Environment

Required:

| Variable | Meaning |
|---|---|
| `LINKEDIN_ACCESS_TOKEN` | OAuth 2.0 access token with `r_ads`, `rw_ads`, and `r_ads_reporting` scopes. |
| `LINKEDIN_AD_ACCOUNT_ID` | Numeric ad account id (with or without the `urn:li:sponsoredAccount:` prefix — the config normalizes it). |

Optional:

| Variable | Default | Meaning |
|---|---|---|
| `LINKEDIN_API_VERSION` | `202605` | Versioned API header (`LinkedIn-Version`). |
| `LINKEDIN_ALLOWED_AD_ACCOUNTS` | unset | Comma-separated allowlist of ad account ids. The configured account must be in the list, or `YIELDAGENT_ALLOW_LIVE=1` must be set. |
| `YIELDAGENT_ALLOW_LIVE` | unset | Set to `1` to bypass the allowlist. Disables the only safety net LinkedIn offers through this integration — use sparingly. |

## Safety model

LinkedIn has no test-account or sandbox concept, so the safety model is built from two independent layers:

1. **Account allowlist.** `LinkedInClient.assert_account_allowed` refuses to touch any account that is not in `LINKEDIN_ALLOWED_AD_ACCOUNTS` unless `YIELDAGENT_ALLOW_LIVE=1` is set. `publish_draft_campaign` runs the guard before it creates anything.
2. **`DRAFT` is the only status the client writes.** `client.py` rejects any attempt to set `ACTIVE` (or `COMPLETED`). Drafts cannot serve impressions or spend budget — they must be activated manually in LinkedIn Campaign Manager. **There is no API path from agent action to live spend.**

Combined, the agent can be wrong in two ways that matter — wrong account or wrong campaign — and neither one can spend money without a human pressing a button in Campaign Manager.

Errors surface as `LinkedInError(status_code, payload)` carrying the parsed JSON body, so the agent's audit trail records LinkedIn's own error codes rather than generic exceptions.

## Running standalone

The server speaks MCP over stdio:

```bash
python -m yieldagent.integrations.linkedin.server
```

The web console does not spawn this subprocess — it calls `publish_draft_campaign` in-process through the LinkedIn connector (`connectors/linkedin.py`). External MCP clients connect over stdio the same way:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
import sys

client = MultiServerMCPClient({
    "linkedin": {
        "command": sys.executable,
        "args": ["-m", "yieldagent.integrations.linkedin.server"],
        "transport": "stdio",
    }
})
tools = await client.get_tools()
```

## Domain → LinkedIn mapping

`mapping.py` is the single place where platform-neutral domain types are translated to LinkedIn payloads. Highlights:

- **Objectives.** `Objective.awareness` → `BRAND_AWARENESS`, `Objective.leads` → `LEAD_GENERATION`, `Objective.sales` → `WEBSITE_CONVERSIONS`, `Objective.traffic` → `WEBSITE_VISITS`, etc. Full table in `OBJECTIVE_TO_LINKEDIN`.
- **Budgets are strings, not minor units.** LinkedIn's API expects `{"amount": "1000.00", "currencyCode": "USD"}`. No zero-decimal special cases. A `LineItem` carries a total budget and an optional `daily_budget`; both are sent when present.
- **Bidding.** `campaign_bidding` maps the line item's strategy: `maximum_delivery` (default) auto-bids with the objective's optimization target (`MAX_IMPRESSION`/`MAX_CLICK`/…) and no manual price; `cost_cap` and `manual` carry `bid_amount` as the cap/bid. `audience_expansion` and the LinkedIn Audience Network are off by default.
- **Flight dates.** `Flight.start_date` becomes UTC midnight; `Flight.end_date` becomes 23:59:59.999999 UTC of that day (inclusive end). Encoded as epoch-millisecond `runSchedule` ints. The Campaign Group's schedule spans the earliest start and latest end across its line items.
- **Geos → URN.** LinkedIn does **not** accept ISO codes — every location is a `urn:li:geo:{id}` URN. The resolver (`targeting.py`) expands each ISO 3166-1 alpha-2 code to a country name via `pycountry`, then resolves it through the LinkedIn **locations typeahead** — so any country works, not a hardcoded shortlist. A code that does not expand or match is surfaced as unresolved; only when *nothing* resolves does it fall back to the default geo (`urn:li:geo:103644278`, US), since LinkedIn requires at least one location.
- **B2B facets are resolved, not dropped.** Each `Audience` facet is resolved to LinkedIn URNs and sent in `targetingCriteria`: `seniorities` and `job_functions` against the standardized `/seniorities` and `/functions` taxonomies (name match); `industries`, `job_titles`, and `skills` via the typeahead finder; `company_sizes` via the static `COMPANY_SIZE_TO_STAFF_RANGE` map. A name that resolves to nothing is **never guessed** — it is surfaced in the publish result under `notes.unresolved_b2b_targeting` so the operator can add it manually in Campaign Manager.
- **Locale.** Required on every Campaign, and it must be a *supported* member-UI interface locale (e.g. `en_PT` is rejected). `line_item_locale` looks the first audience geo up in `SUPPORTED_LOCALE_BY_COUNTRY` and falls back to `en_US` for anything LinkedIn does not support.
- **Creatives — two paths.** When the ad's creative has an `existing_post_urn`, the Creative references that hand-published post directly (the console's default). Otherwise the integration mints a Direct Sponsored Content post authored by the org: an `article` block (headline → `article.title`, description → `article.description`, landing URL → `source`) when there's a `landing_url`, else a text-only post. The post commentary is `primary_text` → `headline` → `name`.

## Known limits

- **No asset uploads for minted posts.** When the integration mints its own Direct Sponsored Content post, it cannot yet upload an `image_url` / `video_url` via the LinkedIn Images/Videos API and attach the returned URN, so a minted post renders with LinkedIn's default link preview. Sponsoring an `existing_post_urn` carries that post's real media, so it is the way to ship rich creative today.
- **Sponsored Content only.** Other campaign formats (Message Ads, Conversation Ads, Dynamic Ads, Text Ads) are out of scope. `DEFAULT_CAMPAIGN_TYPE` in `mapping.py` is hardcoded to `SPONSORED_UPDATES`.
- **No update/delete.** The MCP surface is create-only (`publish_draft_campaign` does roll back its own partial work on failure). Edits and pauses on existing campaigns are out of scope.
