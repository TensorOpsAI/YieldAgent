# LinkedIn integration

An MCP server over the LinkedIn Marketing API, plus a thin async HTTP client and the platform-neutral → LinkedIn payload mapping. Any MCP client — the LinkedIn campaign-setup agent in this repo, or your own — can drive LinkedIn through it.

Source: `src/yieldagent/integrations/linkedin/`.

## Hierarchy mapping

LinkedIn's three-level hierarchy lines up cleanly with the YieldAgent domain model — only the naming shifts:

| YieldAgent | LinkedIn       | Notes |
|------------|----------------|---|
| `Campaign` | Campaign Group | Container; carries the rollup budget. |
| `LineItem` | Campaign       | Where targeting, schedule, and budget live. |
| `Ad`       | Creative       | Sponsored Content single-image is the default in this slice. |

This means a planned `yieldagent.domain.Campaign` with N `LineItem`s and M `Ad`s becomes one LinkedIn **Campaign Group**, N **Campaigns**, and M **Creatives**.

## Tools exposed

The server is implemented with `FastMCP` and registers five tools (see `server.py`):

| Tool | Purpose | Notes |
|---|---|---|
| `get_ad_account` | Return metadata for the configured account. | Used to sanity-check creds. |
| `create_campaign_group` | Create a `DRAFT` Campaign Group. | Total budget required. |
| `create_campaign` | Create a `DRAFT` Campaign under a group. | `objective_type` must be a LinkedIn value (e.g. `LEAD_GENERATION`); requires `targeting_criteria` and `locale`. |
| `create_creative` | Create a `DRAFT` Creative under a Campaign. | Caller supplies the `content` block. |
| `publish_draft_campaign` | One-shot chain: create group → campaigns (per `LineItem`) → creatives (per `Ad`). | Accepts a serialized `yieldagent.domain.Campaign`. Used by the agent. |

Every write tool calls `LinkedInClient.assert_account_allowed` first.

## Environment

Required:

| Variable | Meaning |
|---|---|
| `LINKEDIN_ACCESS_TOKEN` | OAuth 2.0 access token with `r_ads`, `rw_ads`, and `r_ads_reporting` scopes. |
| `LINKEDIN_AD_ACCOUNT_ID` | Numeric ad account id (with or without the `urn:li:sponsoredAccount:` prefix — the config normalizes it). |

Optional:

| Variable | Default | Meaning |
|---|---|---|
| `LINKEDIN_API_VERSION` | `202405` | Versioned API header (`LinkedIn-Version`). |
| `LINKEDIN_ALLOWED_AD_ACCOUNTS` | unset | Comma-separated allowlist of ad account ids. The configured account must be in the list, or `YIELDAGENT_ALLOW_LIVE=1` must be set. |
| `YIELDAGENT_ALLOW_LIVE` | unset | Set to `1` to bypass the allowlist. Disables the only safety net LinkedIn offers through this integration — use sparingly. |

## Safety model

LinkedIn has no test-account or sandbox concept (unlike Meta), so the safety model is built from two independent layers:

1. **Account allowlist.** `LinkedInClient.assert_account_allowed` refuses to touch any account that is not in `LINKEDIN_ALLOWED_AD_ACCOUNTS` unless `YIELDAGENT_ALLOW_LIVE=1` is set. The guard runs on every write tool, not just the chained `publish_draft_campaign`.
2. **`DRAFT` is the only status the client writes.** `client.py` rejects any attempt to set `ACTIVE` (or `COMPLETED`). Drafts cannot serve impressions or spend budget — they must be activated manually in LinkedIn Campaign Manager. **There is no API path from agent action to live spend.**

Combined, the agent can be wrong in two ways that matter — wrong account or wrong campaign — and neither one can spend money without a human pressing a button in Campaign Manager.

Errors surface as `LinkedInError(status_code, payload)` carrying the parsed JSON body, so the agent's audit trail records LinkedIn's own error codes rather than generic exceptions.

## Running standalone

The server speaks MCP over stdio:

```bash
python -m yieldagent.integrations.linkedin.server
```

The LinkedIn campaign-setup agent spawns this as a subprocess via `MultiServerMCPClient` (`agents/linkedin_setup/graph.py:_default_linkedin_mcp_tool_loader`). Other MCP clients can connect to it the same way:

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

- **Objectives.** `Objective.leads` → `LEAD_GENERATION`, `Objective.sales` → `WEBSITE_CONVERSIONS`, `Objective.traffic` → `WEBSITE_VISITS`, etc. Full table in `OBJECTIVE_TO_LINKEDIN`.
- **Budgets are strings, not minor units.** LinkedIn's API expects `{"amount": "1000.00", "currencyCode": "USD"}`. No zero-decimal special cases.
- **Flight dates.** `Flight.start_date` becomes UTC midnight; `Flight.end_date` becomes 23:59:59.999999 UTC of that day (inclusive end). Encoded as epoch-millisecond `runSchedule` ints.
- **Geos → URN lookup.** LinkedIn does **not** accept ISO codes — every location is a `urn:li:geo:{id}` URN. A small built-in table (`ISO_TO_LINKEDIN_GEO_URN`) covers ~15 common countries; everything else is dropped with a fallback to `US`. Production use should resolve via the LinkedIn typeahead endpoint (`/geo` typeahead).
- **B2B facets are not pushed.** `audience.industries`, `job_functions`, `seniorities`, `company_sizes`, and `skills` from the Brief are carried through the domain model but **not sent to LinkedIn** in this slice — every one of them requires URN resolution via typeahead. They are surfaced in the publish result under `notes.unresolved_b2b_targeting` so the operator knows to add them in Campaign Manager before activation.
- **Locale.** Required by LinkedIn on every Campaign. Derived from the first audience geo (`country` field), defaults to `en/US`.
- **Creatives.** Built as single-share Sponsored Content (`article` block). Headline → `article.title`, primary text → `commentary`, CTA upper-snake-cased.

## Known limits

- **No image/video uploads.** Creatives reference `image_url` / `video_url` as inputs, but the agent does not yet upload assets via the LinkedIn `/assets` API and substitute the returned URNs. Real campaigns need a separate upload pass.
- **B2B targeting is not wired.** See above. The single biggest gap vs. a fully usable LinkedIn agent — fixing it means wiring the typeahead resolver into `mapping.py`.
- **Sponsored Content only.** Other campaign formats (Message Ads, Conversation Ads, Dynamic Ads, Text Ads) are out of scope for this slice. `DEFAULT_CAMPAIGN_TYPE` in `mapping.py` is hardcoded to `SPONSORED_UPDATES`.
- **Total-budget only.** The chained `publish_draft_campaign` uses `totalBudget`. Daily budgets are supported by the lower-level `create_campaign` tool but the LineItem domain type currently only carries one budget that maps to total.
- **No update/delete.** The tool surface is strictly create-only. Edits and pauses on existing campaigns are out of scope for this slice.
