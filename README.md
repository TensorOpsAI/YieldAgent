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

## Roadmap

The first milestone is a single vertical slice — a campaign-setup agent that reads a brief and produces a draft campaign in one platform, end to end — exercised against the foundation above. Forcing one slice through all six layers is what turns the design into a real system. Additional roles, platforms, and supply-side workflows stack on top of that loop.

## Status

Early. The repository is intentionally minimal while the design is shaped in the open. Issues, discussions, and proposals are welcome.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 TensorOps.
