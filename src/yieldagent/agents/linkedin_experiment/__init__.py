"""LinkedIn A/B creative experiment agent.

Given a set of creative URNs and an evaluation window, this agent pulls
analytics, ranks variants by a primary metric, and emits a structured
recommendation. Mutations stay gated by the underlying MCP tools — the
agent only recommends; the operator approves `pause_campaign` /
`activate_draft_campaign` calls separately.
"""

from .graph import ExperimentResult, build_graph, run_experiment

__all__ = ["ExperimentResult", "build_graph", "run_experiment"]
