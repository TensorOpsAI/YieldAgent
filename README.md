# YieldAgent

**Open-source toolkit for building autonomous agents that run the operational work of adtech** — media buying, campaign setup, and ad operations across both sides of the market.

---

## What it does today

Hand the agent a markdown campaign brief. It parses the brief, plans a platform-neutral draft `Campaign`, pauses for a human approval decision, and — only on approval — publishes the draft to **Meta (Facebook + Instagram) as `PAUSED` objects** via an MCP server. Nothing goes live without a second human action in Meta Business Manager.

<p align="center">
  <img src="docs/img/campaign_setup_graph.png" alt="Campaign-setup agent — LangGraph topology" width="280">
</p>

```
brief.md ──► [parse_brief] ──► [plan_campaign] ──► [human_gate] ──► [publish_draft] ──► Meta IDs
                                                          │
                                                          └─► (rejected) ──► END
```

Every node appends to an immutable audit trail. Nothing is sent to Meta unless the human gate resumes with `approved=True`. The Meta integration refuses to write to live ad accounts unless you explicitly opt in.

## See it run in 30 seconds (no Meta account needed)

The `--dry-run` flag swaps the Meta MCP server for a stub. The planner LLM still runs, the human gate still fires, the audit trail still records everything — but no API calls leave your machine.

```bash
git clone https://github.com/tensorops/YieldAgent.git && cd YieldAgent
pip install -e ".[agent]"
export ANTHROPIC_API_KEY=sk-ant-...

python -m yieldagent.agents.campaign_setup briefs/example_brief.md --dry-run
```

What you'll see: the planned draft printed as JSON, an interactive `Approve and publish? [y/N]` prompt, then a fake publish result and the full audit trail. Reject it and the flow short-circuits to `END` with nothing "published".

## Run it against your Meta test ad account

Prerequisites: Python 3.11+, a Meta Business Manager **test ad account**, a system user access token with `ads_management` scope, and an Anthropic API key.

```bash
# 1. Install the meta + agent extras
pip install -e ".[meta,agent]"

# 2. Configure credentials
cp .env.example .env
# edit .env: META_ACCESS_TOKEN, META_AD_ACCOUNT_ID, META_PAGE_ID, ANTHROPIC_API_KEY

# 3. Run the agent against the example brief
set -a; source .env; set +a
python -m yieldagent.agents.campaign_setup briefs/example_brief.md
```

The agent prints the planned draft, waits for approval on stdin, and — on `y` — creates the campaign, ad sets, and ads on Meta in `PAUSED` state. The Meta MCP server refuses non-test accounts unless `YIELDAGENT_ALLOW_LIVE=1` is set explicitly.

For CI / smoke tests pass `--auto-approve` to skip the human gate. **Never combine `--auto-approve` with `YIELDAGENT_ALLOW_LIVE=1`.**

There's also a notebook walkthrough at [`notebooks/campaign_setup.ipynb`](notebooks/campaign_setup.ipynb) that runs the slice end-to-end against a test account, renders the graph, and prints the audit trail cell-by-cell.

## Run the workspace interface

The `web/` app is a Next.js interface for the governed campaign-operations workspace: dashboard, agent console, connections, target profiles, campaign briefs, tool registry, approvals, and audit log.

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:3000`. The interface starts empty and reads connection state from local API routes rather than seeded demo data.

### Connect an ads platform

Provider OAuth credentials are entered through the UI — there's no env-var prerequisite.

1. Create an OAuth app in the provider's developer console (LinkedIn Developer, Meta for Developers, or Google Cloud Console). The drawer in step 3 links to the right docs page per provider.
2. Register `http://localhost:3000/api/oauth/<provider>/callback` as an authorized redirect URL on that app. The drawer displays this URL with a copy button.
3. In the workspace, open **Connections → Setup**, paste Client ID + Client Secret (Google Ads also asks for a Developer Token and an optional Manager Customer ID), and save.
4. Click **Connect** to run the OAuth flow.

Saved credentials are AES-256-GCM-encrypted in `.yieldagent/connections.json`. The encryption key lives in `.yieldagent/secret.key` (auto-generated on first save with mode `0600`), so no manual key setup is required. To rotate or supply your own key, set `YIELDAGENT_SECRET_KEY` (32+ chars) before starting the app.

Env vars (`LINKEDIN_CLIENT_ID`, `META_APP_ID`, `GOOGLE_ADS_CLIENT_ID`, etc.) are still honored as optional fallbacks for scripted/CI setups — see `.env.example`.

> Status: LinkedIn OAuth start + callback routes are wired. Meta and Google Ads can save credentials through the UI, but their OAuth routes are not yet implemented.

## Use cases

### Working today
| Use case | Status |
|---|---|
| **Campaign setup on Meta from a markdown brief** | Working — see above |

### On the same substrate, planned next
| Demand-side | Supply-side |
|---|---|
| Campaign setup on Google Ads, TikTok, DV360 | AdOps trafficking (line item QA, creative associations) |
| Budget pacing & in-flight optimization (within scoped bands) | Yield troubleshooting (fill rate, viewability, discrepancies) |
| Performance reporting & anomaly alerts | Inventory hygiene (orphaned placements, blocklist drift) |
| Creative rotation & A/B test scheduling | Deal/PMP setup and monitoring |

All of these reuse the same six layers (below). Adding a new platform mostly means writing an integration + mapping; adding a new role mostly means writing prompts + nodes.

### Why adtech is agent-shaped
- **API-driven end to end** — every platform exposes the surface agents need.
- **Decisions are scoped and largely reversible** — pause, shift budget, rotate creative.
- **Ground truth is fast** — ROAS, fill rate, CTR, viewability all measurable within hours, so agents are evaluable against real outcomes rather than vibes.

## How it's built — six foundational layers

Every adtech agent in this repo, regardless of role, stands on the same foundation:

1. **Domain model** (`src/yieldagent/domain/`) — a shared ontology of adtech entities (campaigns, line items, creatives, audiences, KPIs) so agents on either side of the market interoperate cleanly.
2. **Integration layer** (`src/yieldagent/integrations/`) — tool wrappers and MCP servers over the platforms agents actually act on. Most of the work lives here.
3. **Role definitions with scoped authority** — each agent declares what it can *recommend* vs *execute*, with per-action guardrails. The campaign-setup agent can plan and publish-as-paused; it cannot flip live.
4. **Memory and state** — per-account action logs and KPI snapshots. Campaigns run for weeks, so in-context memory isn't enough. (Today's slice exercises the action-log half via the audit trail.)
5. **Evaluation loop** — performance data wired back as the reward signal. (Hooks present; full loop lands with the optimization agent.)
6. **Human-in-the-loop and audit trail** — approval gates above configurable thresholds, and an immutable log of every spend-affecting action with rationale. Non-negotiable when real money is moving.

The campaign-setup slice forces all six through one concrete workflow. See [`docs/campaign-setup-agent.md`](docs/campaign-setup-agent.md) for how each pillar shows up in the code.

## Repository layout

```
src/yieldagent/
  domain/                       # Pillar 1 — platform-neutral types
    brief.py                    # Brief, Audience, CreativeAsset, Money, KPI
    campaign.py                 # Campaign, LineItem, Ad, CampaignStatus
  integrations/meta/            # Pillar 2 — Meta Marketing API
    client.py                   # Async HTTP client (writes default to PAUSED)
    config.py                   # Env-driven config + live-account guard
    mapping.py                  # Domain ↔ Meta payload translation
    server.py                   # MCP server exposing the tools
  agents/campaign_setup/        # First vertical slice
    graph.py                    # LangGraph wiring with human gate
    nodes.py                    # parse_brief, plan_campaign, human_gate, publish_draft
    prompts.py                  # System prompts for the planner LLM
    state.py                    # AgentState + AuditEntry
    cli.py                      # Interactive CLI entry point (--dry-run for no-creds runs)
briefs/
  example_brief.md              # Reference brief for the example run
notebooks/
  campaign_setup.ipynb          # End-to-end walkthrough with graph render
docs/
  campaign-setup-agent.md       # Graph topology, safety model, embedding
  meta-integration.md           # MCP tools, env, test-account guard, mapping
  brief-format.md               # What a Brief looks like and how it's parsed
  img/campaign_setup_graph.png  # Rendered LangGraph topology
web/
  app/                          # Next.js workspace interface
```

## Documentation

- **[Campaign-setup agent](docs/campaign-setup-agent.md)** — graph topology, safety guarantees, how to embed it in your own runtime.
- **[Meta integration](docs/meta-integration.md)** — MCP server, environment, domain → Meta mapping, known limits.
- **[Brief format](docs/brief-format.md)** — what the planner LLM expects, a worked brief → Campaign example, and how to write briefs that round-trip cleanly.

## Status

Early. The campaign-setup-on-Meta slice is working end-to-end against test accounts; the rest of the platform matrix and the supply-side roles are not built yet. The repository is intentionally minimal while the design is shaped in the open.

Issues, discussions, and proposals are welcome — especially platform integrations (Google Ads, TikTok, DV360, GAM) and supply-side workflows.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 TensorOps.
