# Brief format

A `Brief` is the platform-neutral input contract handed to a campaign-setup agent. A planner — human or upstream agent — writes one; a downstream agent reads it and produces a draft `Campaign` for one or more platforms.

Schema lives in `src/yieldagent/domain/brief.py`. A reference brief is in `briefs/example_brief.md`.

## Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `advertiser` | string | yes | Brand or client name. |
| `product` | string | yes | What is being advertised. |
| `objective` | enum | yes | One of `awareness`, `traffic`, `engagement`, `leads`, `app_promotion`, `sales`. |
| `kpis` | list of `KPI` | yes | Each `KPI` has `metric` (free-form, e.g. `"ROAS"`, `"CPA"`, `"CTR"`) and optional numeric `target`. |
| `budget` | `Money` | yes | `amount` > 0 and ISO 4217 `currency` (e.g. `"USD"`). |
| `flight` | `Flight` | yes | `start_date` and `end_date` (inclusive). `end_date` must be ≥ `start_date`. |
| `audience` | `Audience` | yes | See below. |
| `creatives` | list of `CreativeAsset` | yes | One per creative the planner wants in market. |
| `platforms` | list of strings | yes | Lowercase platform keys. Today only `"meta"` is wired up. |
| `notes` | string | no | Free-form. The planner LLM uses this for naming hints and phasing instructions. |

### `Audience`

| Field | Type | Notes |
|---|---|---|
| `description` | string | Required, free-form. The planner reads this. |
| `age_min`, `age_max` | int 13–99 | Optional. |
| `genders` | list | Optional. `"male"` / `"female"` map to Meta; anything else is dropped at mapping time. |
| `geos` | list | ISO 3166-1 alpha-2 country codes. Finer-grained geos are out of scope for the brief and handled per-platform. |
| `interests` | list | Free-form strings. **Currently dropped** when targeting Meta — Meta needs `adinterest` IDs from its search endpoint. |
| `exclusions` | list | Free-form, advisory. |

### `CreativeAsset`

| Field | Notes |
|---|---|
| `name` | Required. Used in the resulting Ad name. |
| `headline` | Maps to Meta `link_data.name`. |
| `primary_text` | Maps to Meta `link_data.message`. |
| `description` | Maps to Meta `link_data.description`. |
| `image_url` / `video_url` | Reference only — upload-to-`image_hash` resolution is not implemented yet. |
| `call_to_action` | Free text. Upper-snake-cased at mapping time (`"Shop Now"` → `"SHOP_NOW"`). Must match a Meta CTA enum value to be accepted by Meta. |
| `landing_url` | The destination URL. Required for the CTA block to be sent. |

## How the planner LLM reads markdown

`PARSE_BRIEF_SYSTEM` (`src/yieldagent/agents/campaign_setup/prompts.py`) drives a structured-output Anthropic call that returns a `Brief`. The rules it applies:

- Leave fields **null or empty** rather than invent values.
- Convert currency symbols to ISO codes (`$` → `USD`, `€` → `EUR`).
- Convert dates to ISO 8601.
- Normalize platform names: `"Facebook"` or `"Instagram"` → `"meta"`, `"Google Ads"` → `"google"`, `"TikTok"` → `"tiktok"`.

The markdown format in `briefs/example_brief.md` is a recommendation, not a requirement — the parser accepts any prose as long as the fields are recoverable. Section headers help the model and also help humans review the brief later.

## How the planner LLM turns a Brief into a Campaign

`PLAN_CAMPAIGN_SYSTEM` enforces:

- The `Campaign.objective` matches the `Brief.objective`.
- `status` is always `draft` — this is also enforced in code as a defense in depth (`nodes.py:make_plan_campaign_node`).
- One `LineItem` covering the full flight with the full budget, **unless the Brief notes ask for phasing**. Example: the reference brief asks to hold the promo creative until week 2; a planner can split into two LineItems based on that signal.
- One `Ad` per creative. Each `Ad.line_item_name` must reference an existing `LineItem.name` — this is how creatives get attached to line items before any platform IDs exist.
- Audience is carried through to `LineItem.targeting.audience` unchanged unless the Brief specifies sub-audience splits.

## Worked example — Brief → Campaign

Using the reference [`briefs/example_brief.md`](../briefs/example_brief.md) (Glow Roast "Midnight Brew" launch):

| Brief input | Lands in planned `Campaign` as |
|---|---|
| `advertiser: "Glow Roast Coffee"`, `product: "Midnight Brew"` | `Campaign.name` — e.g. `"Glow Roast — Midnight Brew Launch (Jun 2026)"` (notes inform naming) |
| `objective: sales` | `Campaign.objective = "sales"` (must match the Brief) |
| `budget: $15,000 USD` | Distributed across `LineItem.budget` entries (single LineItem unless phased) |
| `flight: 2026-06-01 → 2026-06-30` | `LineItem.flight` (single LineItem unless phased) |
| `audience: US, 25–44, specialty coffee drinkers` | `LineItem.targeting.audience` — carried through unchanged |
| 3 creatives (Hero video, Lifestyle still, Promo still) | 3 `Ad` entries, each `line_item_name` pointing at a `LineItem` |
| `notes: "Hold the promo creative until week 2."` | Triggers the phasing rule — planner splits into 2 `LineItem`s and attaches the promo `Ad` to the later one |
| `notes: "Keep all initial drafts paused..."` | Always true regardless; `Campaign.status = "draft"` is forced |

A plausible plan from the reference brief — the structure is deterministic, the exact names and budget split vary per run:

```jsonc
{
  "name": "Glow Roast — Midnight Brew Launch (Jun 2026)",
  "objective": "sales",
  "status": "draft",                        // forced — never "active" out of plan_campaign
  "line_items": [
    {
      "name": "Midnight Brew — always-on",
      "budget":  {"amount": "11000.00", "currency": "USD"},
      "flight":  {"start_date": "2026-06-01", "end_date": "2026-06-30"},
      "targeting": {"audience": { /* carried from Brief.audience */ }}
    },
    {
      "name": "Midnight Brew — promo (week 2+)",
      "budget":  {"amount": "4000.00",  "currency": "USD"},
      "flight":  {"start_date": "2026-06-08", "end_date": "2026-06-30"},
      "targeting": {"audience": { /* carried from Brief.audience */ }}
    }
  ],
  "ads": [
    {"name": "Hero video",      "line_item_name": "Midnight Brew — always-on",     "creative": { /* from creatives[0] */ }},
    {"name": "Lifestyle still", "line_item_name": "Midnight Brew — always-on",     "creative": { /* from creatives[1] */ }},
    {"name": "Promo still",     "line_item_name": "Midnight Brew — promo (week 2+)", "creative": { /* from creatives[2] */ }}
  ]
}
```

To see the actual output for your own brief, run `python -m yieldagent.agents.campaign_setup <your-brief>.md --dry-run` — the planned `Campaign` JSON is printed before the human gate, no Meta credentials required.

## Writing your own brief

Copy `briefs/example_brief.md` and edit. Anything goes as long as the planner can extract the fields above. The fastest way to be sure a brief parses cleanly is to run it through the agent with `--dry-run` (no Meta credentials needed; see [campaign-setup-agent.md](campaign-setup-agent.md#dry-run-no-meta-credentials-needed)) and inspect the planned `Campaign` in the printed JSON and audit detail.
