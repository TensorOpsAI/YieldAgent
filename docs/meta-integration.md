# Meta integration

An MCP server over the Meta Marketing API (Facebook + Instagram), plus a thin async HTTP client and the platform-neutral → Meta payload mapping. Any MCP client — the campaign-setup agent in this repo, or your own — can drive Meta through it.

Source: `src/yieldagent/integrations/meta/`.

## Tools exposed

The server is implemented with `FastMCP` and registers four tools (see `server.py`):

| Tool | Purpose | Notes |
|---|---|---|
| `get_ad_account` | Return metadata for the configured account. | Used to verify test-account status; safe on live accounts. |
| `create_campaign` | Create a `PAUSED` campaign. | `objective` must be a Meta `OUTCOME_*` value. |
| `create_ad_set` | Create a `PAUSED` ad set under a campaign. | Lifetime budget in minor units; ISO-8601 `start_time` / `end_time`; raw Meta targeting spec. |
| `create_ad` | Create a `PAUSED` ad under an ad set. | Caller supplies the creative payload. |
| `publish_draft_campaign` | One-shot chain: create campaign → ad sets (per `LineItem`) → ads (per `Ad`). | Accepts a serialized `yieldagent.domain.Campaign`. Used by the campaign-setup agent. |

Every write tool calls `MetaClient.assert_test_account` first.

## Environment

Required:

| Variable | Meaning |
|---|---|
| `META_ACCESS_TOKEN` | System user token with `ads_management` scope. |
| `META_AD_ACCOUNT_ID` | Numeric ad account id, with or without `act_` prefix. The config normalizes it. |
| `META_PAGE_ID` | Required to create ads (Meta links link-ad creatives to a Page). |

Optional:

| Variable | Default | Meaning |
|---|---|---|
| `META_API_VERSION` | `v22.0` | Graph API version. |
| `YIELDAGENT_ALLOW_LIVE` | unset | Set to `1` to allow writes against a non-test account. Leave unset for normal development. |

Get a test ad account from Meta Business Manager → *Business Settings → Accounts → Ad Accounts → Add → Create a Test Ad Account*. Test accounts behave like real accounts but never charge and never serve impressions.

## Safety model

- **Test-account guard.** `MetaClient.assert_test_account` fetches `is_test_account` from the Graph API. If it's `false` and `YIELDAGENT_ALLOW_LIVE` is not `1`, every write tool raises `MetaError(403, …)` before sending anything to Meta. The guard runs on the create-campaign / create-ad-set / create-ad path too — not just the chained `publish_draft_campaign`.
- **PAUSED is the only status the client writes.** `client.py` hard-codes `status='PAUSED'` on every create call. There is no method to set status to `ACTIVE`. Flipping a campaign live is intentionally a separate human action outside the agent.
- **Error surfacing.** Any non-2xx response is raised as `MetaError(status_code, payload)` with the parsed JSON body, so agent failures carry the Meta error code/message rather than a generic exception.

## Running standalone

The server speaks MCP over stdio:

```bash
python -m yieldagent.integrations.meta.server
```

The campaign-setup agent spawns this as a subprocess via `MultiServerMCPClient` (`graph.py:_default_meta_mcp_tool_loader`). Other MCP clients can connect to it the same way, or wire it into a multi-server config:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
import sys

client = MultiServerMCPClient({
    "meta": {
        "command": sys.executable,
        "args": ["-m", "yieldagent.integrations.meta.server"],
        "transport": "stdio",
    }
})
tools = await client.get_tools()
```

## Domain → Meta mapping

`mapping.py` is the single place where platform-neutral domain types are translated to Meta payloads. Highlights:

- **Objectives.** `Objective.sales` → `OUTCOME_SALES`, `Objective.leads` → `OUTCOME_LEADS`, etc. Full table in `OBJECTIVE_TO_META`.
- **Budgets in minor units.** `to_minor_units(Decimal, currency)` accounts for zero-decimal currencies (`JPY`, `KRW`, `VND`, `CLP`) and three-decimal currencies (`BHD`, `KWD`, `OMR`, `JOD`, `TND`). Most currencies use 2 minor units. Anything not in the special-case lists is treated as 2 minor units.
- **Flight dates.** `Flight.start_date` becomes UTC midnight; `Flight.end_date` becomes 23:59:59.999999 UTC of that day (inclusive end). Returned as ISO-8601 strings.
- **Audience → targeting.** Geos become `geo_locations.countries` (ISO 3166-1 alpha-2, uppercased). Age and gender pass through. **Interests are intentionally omitted** — Meta requires `adinterest` IDs from a search endpoint, which should be resolved in a follow-up pass rather than guessed.
- **Creatives.** Built as link ads with an `object_story_spec` referencing `META_PAGE_ID`. Headline → `link_data.name`, primary text → `link_data.message`, CTA upper-snake-cased.

## Known limits

- **No image/video uploads.** Creatives reference `image_url` / `video_url` as inputs but the agent does not yet resolve them into Meta `image_hash` / `video_id`. Real campaigns need a separate upload pass via `/{ad_account_id}/adimages` and `/{ad_account_id}/advideos`.
- **Interests are dropped.** See above — `audience.interests` from a Brief is not forwarded into Meta targeting until interest-ID resolution lands.
- **Only lifetime budgets.** The chained `publish_draft_campaign` uses `lifetime_budget_minor`. Daily budgets are supported by the lower-level `create_ad_set` tool but the LineItem domain type currently only carries a single budget that maps to lifetime.
- **No update/delete.** The tool surface is strictly create-only. Edits and pauses on existing campaigns are out of scope for this slice.
