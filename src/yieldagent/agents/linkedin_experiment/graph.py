"""Deterministic LangGraph for LinkedIn creative-variant experiments.

Three nodes — pull_analytics, score_variants, recommend — chained as a
simple state machine. The graph contains no LLM calls so it can run
without ANTHROPIC_API_KEY and tests can drive it with a fake analytics
fetcher.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

# ---------- types -----------------------------------------------------

PrimaryMetric = Literal["ctr", "cpc", "cpl"]

AnalyticsFetcher = Callable[
    ["ExperimentConfig"],
    Awaitable[list[dict[str, Any]]],
]


class ExperimentState(TypedDict, total=False):
    config: "ExperimentConfig"
    elements: list[dict[str, Any]]
    rankings: list["VariantScore"]
    recommendation: "ExperimentResult"


@dataclass(frozen=True)
class ExperimentConfig:
    creative_urns: list[str]
    date_start: date
    date_end: date
    primary_metric: PrimaryMetric = "ctr"
    min_impressions: int = 1000


@dataclass(frozen=True)
class VariantScore:
    creative_urn: str
    impressions: int
    clicks: int
    cost: float
    conversions: int
    leads: int
    ctr: float
    cpc: float | None
    cpl: float | None
    primary_score: float | None
    sufficient_data: bool


@dataclass(frozen=True)
class ExperimentRecommendation:
    creative_urn: str
    action: Literal["keep", "pause", "scale", "needs_data"]
    rationale: str


@dataclass(frozen=True)
class ExperimentResult:
    primary_metric: PrimaryMetric
    rankings: list[VariantScore]
    recommendations: list[ExperimentRecommendation]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_metric": self.primary_metric,
            "rankings": [score.__dict__ for score in self.rankings],
            "recommendations": [rec.__dict__ for rec in self.recommendations],
            "notes": list(self.notes),
        }


# ---------- nodes -----------------------------------------------------


def _safe_float(value: Any) -> float:
    """LinkedIn returns costInLocalCurrency as a string; coerce safely."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def score_elements(
    elements: list[dict[str, Any]],
    *,
    primary_metric: PrimaryMetric,
    min_impressions: int,
) -> list[VariantScore]:
    """Pure function: aggregate analytics rows into per-creative scores.

    LinkedIn's pivot=CREATIVE response returns one element per (creative,
    date-bucket) — so we group by `pivotValues[0]` (the creative URN) and
    sum. Designed to be testable without any network.
    """
    by_creative: dict[str, dict[str, float]] = {}
    for element in elements:
        pivot_values = element.get("pivotValues") or []
        if not pivot_values:
            continue
        urn = str(pivot_values[0])
        bucket = by_creative.setdefault(
            urn,
            {"impressions": 0.0, "clicks": 0.0, "cost": 0.0, "conversions": 0.0, "leads": 0.0},
        )
        bucket["impressions"] += _safe_int(element.get("impressions"))
        bucket["clicks"] += _safe_int(element.get("clicks"))
        bucket["cost"] += _safe_float(element.get("costInLocalCurrency"))
        bucket["conversions"] += _safe_int(element.get("externalWebsiteConversions"))
        bucket["leads"] += _safe_int(element.get("oneClickLeads"))

    scores: list[VariantScore] = []
    for urn, totals in by_creative.items():
        impressions = int(totals["impressions"])
        clicks = int(totals["clicks"])
        cost = totals["cost"]
        conversions = int(totals["conversions"])
        leads = int(totals["leads"])
        ctr = (clicks / impressions) if impressions else 0.0
        cpc = (cost / clicks) if clicks else None
        cpl = (cost / leads) if leads else None
        if primary_metric == "ctr":
            primary_score: float | None = ctr
        elif primary_metric == "cpc":
            primary_score = cpc
        else:
            primary_score = cpl
        scores.append(
            VariantScore(
                creative_urn=urn,
                impressions=impressions,
                clicks=clicks,
                cost=round(cost, 4),
                conversions=conversions,
                leads=leads,
                ctr=round(ctr, 6),
                cpc=round(cpc, 4) if cpc is not None else None,
                cpl=round(cpl, 4) if cpl is not None else None,
                primary_score=(round(primary_score, 6) if primary_score is not None else None),
                sufficient_data=impressions >= min_impressions,
            )
        )

    # CTR: descending; CPC/CPL: ascending (lower is better). Variants with
    # no primary_score sink to the bottom.
    reverse = primary_metric == "ctr"

    def sort_key(score: VariantScore) -> tuple[int, float]:
        if score.primary_score is None:
            return (1, 0.0)
        return (0, -score.primary_score if reverse else score.primary_score)

    return sorted(scores, key=sort_key)


def recommend(
    rankings: list[VariantScore],
    *,
    primary_metric: PrimaryMetric,
) -> ExperimentResult:
    """Pure function: map ranked variants to actionable recommendations."""
    notes: list[str] = []
    if not rankings:
        notes.append("No analytics rows returned — nothing to score.")
        return ExperimentResult(
            primary_metric=primary_metric, rankings=[], recommendations=[], notes=notes
        )

    sufficient = [score for score in rankings if score.sufficient_data]
    insufficient = [score for score in rankings if not score.sufficient_data]
    if insufficient:
        notes.append(
            f"{len(insufficient)} variant(s) below the impressions floor — held as 'needs_data'."
        )

    recommendations: list[ExperimentRecommendation] = []
    if sufficient:
        winner = sufficient[0]
        recommendations.append(
            ExperimentRecommendation(
                creative_urn=winner.creative_urn,
                action="scale",
                rationale=(
                    f"Leads on {primary_metric}={winner.primary_score}; "
                    f"impressions={winner.impressions}, clicks={winner.clicks}."
                ),
            )
        )
        for loser in sufficient[1:]:
            recommendations.append(
                ExperimentRecommendation(
                    creative_urn=loser.creative_urn,
                    action="pause",
                    rationale=(
                        f"{primary_metric}={loser.primary_score} trails "
                        f"winner {winner.primary_score} on {winner.impressions} impressions."
                    ),
                )
            )

    for held in insufficient:
        recommendations.append(
            ExperimentRecommendation(
                creative_urn=held.creative_urn,
                action="needs_data",
                rationale=(
                    f"Only {held.impressions} impressions — under the minimum threshold."
                ),
            )
        )

    return ExperimentResult(
        primary_metric=primary_metric,
        rankings=rankings,
        recommendations=recommendations,
        notes=notes,
    )


# ---------- graph -----------------------------------------------------


def build_graph(fetcher: AnalyticsFetcher):
    """Compile a LangGraph for the experiment. Inject `fetcher` to swap the data source."""

    async def pull_node(state: ExperimentState) -> ExperimentState:
        config = state["config"]
        elements = await fetcher(config)
        return {"elements": elements}

    async def score_node(state: ExperimentState) -> ExperimentState:
        config = state["config"]
        rankings = score_elements(
            state.get("elements") or [],
            primary_metric=config.primary_metric,
            min_impressions=config.min_impressions,
        )
        return {"rankings": rankings}

    async def recommend_node(state: ExperimentState) -> ExperimentState:
        config = state["config"]
        result = recommend(
            state.get("rankings") or [],
            primary_metric=config.primary_metric,
        )
        return {"recommendation": result}

    graph = StateGraph(ExperimentState)
    graph.add_node("pull_analytics", pull_node)
    graph.add_node("score_variants", score_node)
    graph.add_node("recommend", recommend_node)
    graph.add_edge(START, "pull_analytics")
    graph.add_edge("pull_analytics", "score_variants")
    graph.add_edge("score_variants", "recommend")
    graph.add_edge("recommend", END)
    return graph.compile()


# ---------- default real-world fetcher --------------------------------


async def _default_fetcher(config: ExperimentConfig) -> list[dict[str, Any]]:
    """Pull analytics directly via the LinkedIn client (for CLI runs)."""
    from yieldagent.integrations.linkedin.client import LinkedInClient
    from yieldagent.integrations.linkedin.config import LinkedInConfig

    fields = [
        "impressions",
        "clicks",
        "costInLocalCurrency",
        "externalWebsiteConversions",
        "oneClickLeads",
        "pivotValues",
        "dateRange",
    ]
    async with LinkedInClient(LinkedInConfig.from_env()) as client:
        payload = await client.get_ad_analytics(
            pivot="CREATIVE",
            date_start=config.date_start,
            date_end=config.date_end,
            time_granularity="ALL",
            creative_urns=config.creative_urns,
            fields=fields,
        )
    return payload.get("elements", [])


async def run_experiment(
    config: ExperimentConfig,
    *,
    fetcher: AnalyticsFetcher | None = None,
) -> ExperimentResult:
    """Drive the experiment graph end-to-end. Returns the structured result."""
    app = build_graph(fetcher or _default_fetcher)
    final = await app.ainvoke({"config": config})
    return final["recommendation"]
