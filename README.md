# YieldAgent

Foundations for autonomous agents that run the operational work of adtech companies — across media buying, campaign setup, and ad operations.

## What this is

Adtech is one of the most agent-ready domains in software. It is API-driven end to end, decisions are scoped and largely reversible, and ground truth — ROAS, fill rate, CTR, viewability — is measurable within hours. YieldAgent is an open-source project that builds the substrate on which agents for adtech can be developed, evaluated, and run safely against real platforms.

The project covers both sides of the market:

- **Demand-side agents.** Media buyers and campaign-setup assistants for advertisers and agencies — planning, trafficking, bid and budget management, optimization, and reporting.
- **Supply-side agents.** AdOps agents for publishers and SSPs — trafficking, troubleshooting, yield management, and inventory hygiene.

## Foundational layers

YieldAgent is organized around six pillars. Every adtech agent, regardless of role, stands on the same foundation:

1. **Domain model.** A shared ontology of adtech entities — campaigns, line items, creatives, audiences, deals, insertion orders, KPIs — so agents on either side of the market interoperate cleanly and hand work off without translation loss.
2. **Integration layer.** Tool wrappers and MCP servers over the platforms agents actually act on: ad networks, DSPs, SSPs, ad servers, attribution and verification vendors. This is where most of the value lives.
3. **Role definitions with scoped authority.** Each agent declares what it can *recommend* versus *execute*, with per-action budget and policy guardrails. A media buyer can shift budget within a band; AdOps can pause but not delete.
4. **Memory and state.** Long-lived, per-account memory: action logs, KPI snapshots, learned heuristics. Campaigns run for weeks — in-context memory is not enough.
5. **Evaluation loop.** Performance data is wired back as the reward signal, so agents are measured and improved against real outcomes rather than vibes.
6. **Human-in-the-loop and audit trail.** Approval gates above configurable thresholds and an immutable log of every spend-affecting action, with rationale. Non-negotiable when real money is moving.

## First vertical slice — campaign setup on Meta

The first milestone forces all six pillars through one concrete workflow: a campaign-setup agent that reads a markdown brief and produces a paused draft campaign on Meta (Facebook + Instagram), end to end. What it exercises:

- **Domain model** (`src/yieldagent/domain/`) — platform-neutral `Brief` and `Campaign` types.
- **Integration layer** (`src/yieldagent/integrations/meta/`) — an MCP server over the Meta Marketing API that refuses to write to live ad accounts by default.
- **Role with scoped authority** — the publish step only creates `PAUSED` objects; flipping anything live is out of scope for the agent.
- **State and audit** — every node appends an `AuditEntry`; the full trail is printed at the end of each run.
- **Human-in-the-loop** — a LangGraph `interrupt()` between planning and publishing. The agent stops, surfaces the draft, and waits for an approval decision before touching the platform.

Additional roles (optimization, reporting), platforms (Google, TikTok, DV360), and supply-side workflows stack on top of the same foundation.

### Quick start

Prerequisites: Python 3.11+, a Meta Business Manager **test ad account**, a system user access token with `ads_management` scope, and an Anthropic API key.

```bash
# 1. Install with the meta integration and the agent extras
pip install -e ".[meta,agent]"

# 2. Configure credentials
cp .env.example .env
# edit .env: META_ACCESS_TOKEN, META_AD_ACCOUNT_ID, META_PAGE_ID, ANTHROPIC_API_KEY

# 3. Run the agent against the example brief
set -a; source .env; set +a
python -m yieldagent.agents.campaign_setup briefs/example_brief.md
```

The agent will print the planned draft, ask for approval on stdin, and — if you approve — create the campaign, ad sets, and ads on Meta in `PAUSED` state. The Meta MCP server refuses non-test accounts unless you set `YIELDAGENT_ALLOW_LIVE=1`.

For CI / smoke tests pass `--auto-approve` to skip the gate. **Do not** combine `--auto-approve` with `YIELDAGENT_ALLOW_LIVE=1`.

### Repository layout

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
    cli.py                      # Interactive CLI entry point
briefs/
  example_brief.md              # Reference brief for the example run
docs/
  campaign-setup-agent.md       # Graph topology, safety model, embedding
  meta-integration.md           # MCP tools, env, test-account guard, mapping
  brief-format.md               # What a Brief looks like and how it's parsed
```

## Documentation

- [Campaign-setup agent](docs/campaign-setup-agent.md) — graph topology, safety guarantees, how to embed it.
- [Meta integration](docs/meta-integration.md) — MCP server, environment, mapping, known limits.
- [Brief format](docs/brief-format.md) — what the planner LLM expects and how to write briefs that round-trip cleanly.

## Status

Early. One vertical slice is working end to end against Meta test accounts; the rest of the platform matrix and the supply-side workflows are not built yet. The repository is intentionally minimal while the design is shaped in the open. Issues, discussions, and proposals are welcome.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 TensorOps.
