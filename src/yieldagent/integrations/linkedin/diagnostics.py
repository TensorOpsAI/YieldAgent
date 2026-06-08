"""Two-layer campaign validation: predict the predictable, translate the rest.

LinkedIn rejects a campaign for many reasons, and it has no transaction — a
mid-flow rejection strands partial DRAFTs we then have to roll back. So we guard
in two layers:

  * **Pre-flight** (`preflight_problems`) catches the cheap, knowable rejections
    BEFORE creating anything — currency mismatch, sub-minimum budget, past flight
    dates. No resource is created for a problem we could have predicted.

  * **Translation** (`explain_linkedin_error`) is the backstop for everything we
    can't predict: it turns a raw `LinkedInError` payload into the same clean,
    actionable `Problem` shape so the agent can relay it and the user can fix the
    draft. LinkedIn's own API is the source of truth for rules that change.

Both produce a `Problem = {field, message, fix}`, and both surface through
`CampaignProblems`, a single exception the publish flow raises so callers handle
fixable issues uniformly (and never see a raw traceback).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, TypedDict

from yieldagent.domain import BiddingStrategy, Objective

from .client import LinkedInClient, LinkedInError
from .mapping import (
    AUTO_BID_COST_TYPE,
    DEFAULT_CAMPAIGN_TYPE,
    OBJECTIVE_TO_LINKEDIN,
    campaign_optimization_target,
)


class Problem(TypedDict):
    field: str
    message: str
    fix: str


class CampaignValidationError(Exception):
    """Fixable campaign problems — pre-flight or LinkedIn-reported.

    Carries structured `problems` so the agent can tell the user exactly what to
    change. `rolled_back` is True when LinkedIn had already created partial work
    that we tore down before raising.
    """

    def __init__(self, problems: list[Problem], *, rolled_back: bool = False) -> None:
        self.problems = problems
        self.rolled_back = rolled_back
        summary = "; ".join(p["message"] for p in problems) or "campaign was rejected"
        super().__init__(summary)


# LinkedIn campaign-group total/lifetime budget minimums. Observed: EUR min 100.
# Used only as a fast local guard — the API is the real authority, so an unknown
# currency just falls back to the conservative default and lets the API decide.
_MIN_GROUP_BUDGET: dict[str, Decimal] = {
    "EUR": Decimal("100"),
    "USD": Decimal("100"),
    "GBP": Decimal("100"),
}
_DEFAULT_MIN_GROUP_BUDGET = Decimal("100")

# Per-day delivery minimum. A campaign's effective daily spend (total budget /
# flight days) must clear this or it cannot deliver — so a short flight needs a
# proportionally larger total.
#
# This table is LAST RESORT. LinkedIn's real per-day floor depends on
# (account, objective, audience, bidding strategy) and is only knowable through
# the `adBudgetPricing` finder (see `quote_budget_floor` below). The values here
# are intentionally conservative so a fallback rarely lets a sub-floor budget
# through to a publish-time rejection.
_MIN_DAILY_BUDGET: dict[str, Decimal] = {
    "EUR": Decimal("11"),
    "USD": Decimal("11"),
    "GBP": Decimal("11"),
}
_DEFAULT_MIN_DAILY_BUDGET = Decimal("11")

# LinkedIn's privacy floor: an audience under this size cannot run.
AUDIENCE_MIN_SIZE = 300


def _money(amount: Decimal | str, currency: str) -> dict[str, str]:
    return {"amount": str(amount), "currency": currency.upper()}


def fallback_floor(currency: str | None) -> dict[str, Any]:
    """Conservative, currency-only floor used when the live quote is unavailable."""
    key = (currency or "").upper()
    return {
        "min_daily": _money(
            _MIN_DAILY_BUDGET.get(key, _DEFAULT_MIN_DAILY_BUDGET), key or "EUR"
        ),
        "min_total": _money(
            _MIN_GROUP_BUDGET.get(key, _DEFAULT_MIN_GROUP_BUDGET), key or "EUR"
        ),
        "source": "fallback",
        "notes": "Currency-only fallback; the live floor depends on objective and audience.",
    }


def _pick_amount(*candidates: Any) -> Decimal | None:
    """First non-None candidate that parses as a Decimal."""
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return Decimal(str(candidate))
        except (ValueError, ArithmeticError):
            continue
    return None


def _box_min(box: Any, *, fallback: Any) -> tuple[Decimal | None, str | None]:
    """Pull (amount, currencyCode) from one limits box across known shapes.

    A limits box may be `{min: {amount, currencyCode}}`, `{minimum: {...}}`, or a
    flat `{amount, currencyCode}`. Returns (None, None) for anything else, with
    `fallback` (a sibling flat amount) used when the box has no usable number.
    """
    if not isinstance(box, dict):
        return _pick_amount(fallback), None
    inner = box.get("min") if isinstance(box.get("min"), dict) else box.get("minimum")
    inner = inner if isinstance(inner, dict) else {}
    amount = _pick_amount(inner.get("amount"), box.get("amount"), fallback)
    currency = inner.get("currencyCode") or box.get("currencyCode")
    return amount, currency


def _parse_pricing(payload: dict[str, Any], currency: str | None) -> dict[str, Any] | None:
    """Reduce an adBudgetPricing response to `{min_daily, min_total}`.

    LinkedIn's response shape has shifted across API versions: the floor may live
    on top-level `dailyBudgetLimits`/`lifetimeBudgetLimits`, on the first
    `elements` entry, or under `suggestedDailyBudget.min`. We look in the common
    spots and bail out (returning None) if we can't pull a number — the caller
    then falls back to the conservative table rather than guessing.
    """
    root = payload or {}
    elements = root.get("elements") or []
    candidates = [elements[0]] if elements else []
    candidates.append(root)

    daily: Decimal | None = None
    total: Decimal | None = None
    out_currency = (currency or "").upper()

    for src in candidates:
        if not isinstance(src, dict):
            continue
        daily_amount, daily_cur = _box_min(
            src.get("dailyBudgetLimits") or src.get("suggestedDailyBudget"),
            fallback=src.get("minDailyBudgetAmount"),
        )
        total_amount, total_cur = _box_min(
            src.get("lifetimeBudgetLimits") or src.get("suggestedLifetimeBudget"),
            fallback=src.get("minLifetimeBudgetAmount"),
        )
        daily = daily or daily_amount
        total = total or total_amount
        if daily_cur or total_cur:
            out_currency = str(daily_cur or total_cur).upper()

    if daily is None and total is None:
        return None

    result: dict[str, Any] = {"source": "live"}
    if daily is not None:
        result["min_daily"] = _money(daily, out_currency or "EUR")
    if total is not None:
        result["min_total"] = _money(total, out_currency or "EUR")
    return result


def _bid_type_for(strategy: BiddingStrategy | None) -> str | None:
    if strategy is BiddingStrategy.manual:
        return "CPC_BID"
    return None  # let LinkedIn default for auto/cost_cap


async def quote_budget_floor(
    client: LinkedInClient,
    *,
    objective: str | None,
    currency: str | None,
    targeting_criteria: dict[str, Any] | None = None,
    bidding_strategy: BiddingStrategy | None = None,
) -> dict[str, Any]:
    """Ask LinkedIn for the live per-plan floor; fall back to the table on trouble.

    Always returns a neutral `{min_daily, min_total, source, notes?}` so callers
    do not have to handle exceptions. `source` is "live" when the number came
    from `adBudgetPricing`, "fallback" otherwise (missing config, API error,
    response shape we cannot parse). A fallback is safe to use for messaging but
    the platform will still quote its own number at publish-time.
    """
    try:
        platform_objective = (
            OBJECTIVE_TO_LINKEDIN[Objective(objective)] if objective else None
        )
    except (KeyError, ValueError):
        platform_objective = None

    if not platform_objective:
        return fallback_floor(currency)

    optimization_target = campaign_optimization_target(platform_objective)
    cost_type = AUTO_BID_COST_TYPE if optimization_target else None

    try:
        payload = await client.ad_budget_pricing(
            campaign_type=DEFAULT_CAMPAIGN_TYPE,
            objective_type=platform_objective,
            targeting_criteria=targeting_criteria,
            optimization_target=optimization_target,
            bid_type=_bid_type_for(bidding_strategy) or cost_type,
        )
    except Exception:  # noqa: BLE001 — any failure: fall back, never raise to caller
        return fallback_floor(currency)

    parsed = _parse_pricing(payload, currency)
    if parsed is None:
        return fallback_floor(currency)
    # When the parse succeeds we trust the live quote in full — that is the
    # whole point of asking. The table is fallback only.
    return parsed


# Optional campaign fields the operator may set or delegate. `status` tells the
# agent what we do with each: "settable" = the operator can set it and we apply it
# on create; "auto" = we set it from the objective unless overridden; "manual" =
# not sent on create, note it for the operator to set in Campaign Manager.
_OPTIONAL_FIELDS: list[dict[str, Any]] = [
    {
        "key": "daily_budget",
        "desc": "Daily spend cap ({amount, currency}); combine with the total budget "
        "or use alone. If omitted, LinkedIn derives a daily from the total over the "
        "flight; that derived daily must clear min_daily below.",
        "status": "settable",
    },
    {
        "key": "bidding_strategy",
        "desc": "How LinkedIn bids. cost_cap and manual require bid_amount.",
        "allowed": ["maximum_delivery", "cost_cap", "manual"],
        "default": "maximum_delivery",
        "status": "settable",
    },
    {
        "key": "bid_amount",
        "desc": "Bid or cost cap ({amount, currency}); required for cost_cap and manual.",
        "status": "settable",
    },
    {
        "key": "optimization_goal",
        "desc": "What delivery optimizes for (e.g. MAX_IMPRESSION, MAX_CLICK, "
        "MAX_LEAD, MAX_CONVERSION); set from the objective unless you override it.",
        "status": "auto",
    },
    {
        "key": "audience_expansion",
        "desc": "Let LinkedIn broaden to similar members.",
        "allowed": [True, False],
        "default": False,
        "status": "settable",
    },
    {
        "key": "audience_network",
        "desc": "Deliver off-LinkedIn via the LinkedIn Audience Network.",
        "allowed": [True, False],
        "default": False,
        "status": "settable",
    },
    {
        "key": "frequency_cap",
        "desc": "Max times one member sees the ad.",
        "default": "automatic",
        "status": "manual",
    },
]


async def describe_constraints(client: LinkedInClient) -> dict[str, Any]:
    """A self-describing snapshot of this platform's hard rules.

    The agent calls this once the operator picks a platform, so it can propose a
    valid campaign up front instead of relying on the publish-time backstop. The
    shape is platform-neutral on purpose — it is the contract any connector fills
    in (a Meta connector returns the same keys with its own values), so the agent
    never hard-codes one platform's rules. Account currency is fetched live.
    """
    try:
        account = await client.get_ad_account()
        currency = (account or {}).get("currency")
    except Exception:  # noqa: BLE001 — constraints are advisory; the API backstops
        currency = None
    key = (currency or "").upper()
    min_total = _MIN_GROUP_BUDGET.get(key, _DEFAULT_MIN_GROUP_BUDGET)
    min_daily = _MIN_DAILY_BUDGET.get(key, _DEFAULT_MIN_DAILY_BUDGET)
    return {
        "platform": "linkedin",
        "currency": currency,
        "fields": {
            "required": ["objective", "budget", "flight", "audience", "creative"],
            "optional": _OPTIONAL_FIELDS,
        },
        # The exact objective values to use — so the agent picks "awareness", not
        # free-text like "brand awareness".
        "objectives": [o.value for o in Objective],
        "budget": {
            "min_total": str(min_total),
            "min_daily": str(min_daily),
            "currency_must_match_account": True,
            "note": (
                "Effective daily spend = total budget / flight days, and must be at "
                f"least {min_daily} {currency or ''}. So a short flight needs a larger "
                "total (e.g. a 15-day flight needs total >= 15 x the daily minimum)."
            ),
        },
        "flight": {"must_start_today_or_later": True},
        "audience": {
            "min_size": AUDIENCE_MIN_SIZE,
            # The audience facets this platform supports — the agent fills only these
            # (a Meta connector would advertise geos/age/genders/interests instead).
            "facets": [
                "geos",
                "seniorities",
                "job_functions",
                "industries",
                "job_titles",
                "skills",
                "company_sizes",
            ],
            "notes": [
                "geos are country-level (ISO alpha-2); for a city, target its country.",
                "Seniority is the LEVEL (Manager, Director, VP, CXO) — target job roles "
                "(Founder, CEO, 'VP of Engineering') as job_titles via search_targeting, "
                "not as seniorities.",
            ],
        },
        "creative": {
            "can_sponsor_existing_post": True,
            "reshares_sponsorable": False,  # only original organization posts
            "needs_copy_or_existing_post": True,
            "landing_url_optional": True,
        },
        "locale": {
            "auto_selected": True,
            "note": (
                "Locale is derived from the audience geo automatically; geos with no "
                "LinkedIn-supported interface locale fall back to en_US. Do not ask the "
                "operator for it."
            ),
        },
        "objective_notes": {
            "leads": "A Lead Gen Form is added manually in Campaign Manager before launch.",
        },
        "notes": [
            "Everything is created as DRAFT; activation is manual in Campaign Manager.",
        ],
    }


def _problem(field: str, message: str, fix: str) -> Problem:
    return {"field": field, "message": message, "fix": fix}


def _group_budget(campaign: Any) -> tuple[Decimal, str] | None:
    """Mirror server._group_budget without importing it (avoids a cycle)."""
    if campaign.lifetime_budget is not None:
        return Decimal(campaign.lifetime_budget.amount), campaign.lifetime_budget.currency
    if campaign.line_items:
        currency = campaign.line_items[0].budget.currency
        amount = sum(
            (
                Decimal(li.budget.amount)
                for li in campaign.line_items
                if li.budget.currency == currency
            ),
            Decimal(0),
        )
        return amount, currency
    return None


async def _line_item_floor(
    client: LinkedInClient, campaign: Any, line_item: Any
) -> dict[str, Any]:
    """Quote the live per-plan floor for one line item, resolving its audience.

    Best-effort: any failure (audience resolution, API) returns the table-based
    fallback rather than blocking pre-flight.
    """
    # Lazy import to avoid a cycle (targeting imports from this package's siblings).
    from .targeting import TargetingResolver

    criteria: dict[str, Any] | None = None
    try:
        resolved = await TargetingResolver(client).resolve(line_item.targeting.audience)
        criteria = resolved.criteria
    except Exception:  # noqa: BLE001 — quote without targeting is still useful
        criteria = None

    objective = (
        campaign.objective.value if hasattr(campaign.objective, "value") else campaign.objective
    )
    return await quote_budget_floor(
        client,
        objective=objective,
        currency=line_item.budget.currency,
        targeting_criteria=criteria,
        bidding_strategy=line_item.bidding_strategy,
    )


async def preflight_problems(
    client: LinkedInClient, campaign: Any, *, today: date | None = None
) -> list[Problem]:
    """Cheap checks for the rejections we can predict, before creating anything.

    `campaign` is a parsed `yieldagent.domain.Campaign`. Fetches the ad account
    once to validate currency; everything else is local. Returns an empty list
    when the campaign looks publishable.
    """
    today = today or date.today()
    problems: list[Problem] = []

    # Per-line-item checks: flight dates, bidding bid requirement, daily budget min.
    for li in campaign.line_items:
        if li.flight.start_date < today:
            problems.append(
                _problem(
                    f"line_items[{li.name}].flight.start_date",
                    f"Flight start {li.flight.start_date.isoformat()} is in the past.",
                    f"Use a start date on or after {today.isoformat()}.",
                )
            )

        # cost_cap and manual bidding need an explicit bid/cost cap.
        if (
            li.bidding_strategy in (BiddingStrategy.cost_cap, BiddingStrategy.manual)
            and li.bid_amount is None
        ):
            problems.append(
                _problem(
                    f"line_items[{li.name}].bid_amount",
                    f"{li.bidding_strategy.value} bidding needs a bid_amount.",
                    "Provide bid_amount, or use maximum_delivery (auto bidding).",
                )
            )

        # Quote LinkedIn's live per-plan daily floor (or fall back to the table) for
        # this line item's (objective, audience, bidding) tuple, and check both the
        # explicit daily and — when the operator only gave a total — the derived
        # daily = total / flight_days. This catches the "210 EUR over 21 days →
        # 10.00/day, LinkedIn wants 10.40/day" rejection class before publish.
        floor = await _line_item_floor(client, campaign, li)
        min_daily_amount = Decimal(floor["min_daily"]["amount"])
        floor_cur = floor["min_daily"]["currency"]

        if li.daily_budget is not None:
            cur = li.daily_budget.currency.upper()
            if Decimal(li.daily_budget.amount) < min_daily_amount:
                problems.append(
                    _problem(
                        f"line_items[{li.name}].daily_budget",
                        f"Daily budget {li.daily_budget.amount} {cur} is below the "
                        f"{floor['source']} minimum {min_daily_amount} {floor_cur}.",
                        f"Raise the daily budget to at least {min_daily_amount} {floor_cur}.",
                    )
                )
        else:
            flight_days = (li.flight.end_date - li.flight.start_date).days + 1
            if flight_days > 0:
                derived_daily = Decimal(li.budget.amount) / Decimal(flight_days)
                if derived_daily < min_daily_amount:
                    needed_total = (min_daily_amount * flight_days).quantize(Decimal("0.01"))
                    problems.append(
                        _problem(
                            f"line_items[{li.name}].budget",
                            f"Total {li.budget.amount} {li.budget.currency} over "
                            f"{flight_days} days is {derived_daily.quantize(Decimal('0.01'))} "
                            f"{li.budget.currency}/day, below the {floor['source']} minimum "
                            f"{min_daily_amount} {floor_cur}/day.",
                            f"Raise the total to at least {needed_total} {floor_cur}, "
                            f"shorten the flight, or set daily_budget at or above "
                            f"{min_daily_amount} {floor_cur}.",
                        )
                    )

    # All line items must share a currency — otherwise the group budget (summed in
    # the first line item's currency) silently drops the others.
    currencies = {li.budget.currency.upper() for li in campaign.line_items}
    if len(currencies) > 1:
        problems.append(
            _problem(
                "line_items[].budget.currency",
                f"Line items mix currencies ({', '.join(sorted(currencies))}).",
                "Use a single currency across all line items in one campaign.",
            )
        )

    budget = _group_budget(campaign)
    if budget is not None:
        amount, currency = budget
        minimum = _MIN_GROUP_BUDGET.get(currency.upper(), _DEFAULT_MIN_GROUP_BUDGET)
        if amount < minimum:
            problems.append(
                _problem(
                    "campaign.budget",
                    f"Total budget {amount} {currency} is below LinkedIn's minimum.",
                    f"Raise the budget to at least {minimum} {currency}.",
                )
            )

        # Budget currency must match the ad account's currency.
        try:
            account = await client.get_ad_account()
            account_currency = (account or {}).get("currency")
        except Exception:  # noqa: BLE001 — currency check is best-effort; API backstops it
            account_currency = None
        if account_currency and account_currency.upper() != currency.upper():
            problems.append(
                _problem(
                    "campaign.budget.currency",
                    f"Budget currency {currency} does not match the ad account "
                    f"currency {account_currency}.",
                    f"Set every budget currency to {account_currency}.",
                )
            )

    return problems


# Field-path / code hints that make a raw LinkedIn error actionable. Matched as
# substrings against the error's fieldPath or code, most specific first.
_FIX_HINTS: list[tuple[str, str]] = [
    ("totalBudget", "Raise the total budget — LinkedIn enforces a per-currency minimum."),
    ("dailyBudget", "Raise the daily budget — LinkedIn enforces a per-currency minimum."),
    ("currency", "Set the budget currency to match the ad account's currency."),
    ("runSchedule", "Use flight dates that start today or later."),
    # Locale hints come before the generic targetingCriteria hint: a locale error's
    # fieldPath is often /Campaign/targetingCriteria, so locale must win the match.
    ("locale", "Use a LinkedIn-supported locale/interface locale for this country."),
    ("targetingCriteria", "Adjust targeting — a facet value is invalid or unsupported."),
]


def _hint_for(field_path: str, code: str) -> str:
    haystack = f"{field_path} {code}"
    for needle, hint in _FIX_HINTS:
        if needle.lower() in haystack.lower():
            return hint
    return "Adjust this field and re-propose the draft."


def explain_linkedin_error(exc: LinkedInError) -> list[Problem]:
    """Translate a raw `LinkedInError` payload into clean, actionable problems.

    Reads `errorDetails.inputErrors[]` when present (the per-field validation
    failures), falling back to the top-level message so we always return at least
    one problem the agent can relay.
    """
    payload = exc.payload if isinstance(exc.payload, dict) else {}
    input_errors = (payload.get("errorDetails") or {}).get("inputErrors") or []

    problems: list[Problem] = []
    for err in input_errors:
        field_path = ((err.get("inputPath") or {}).get("fieldPath")) or "campaign"
        code = err.get("code") or ""
        message = err.get("description") or err.get("message") or "Invalid value."
        problems.append(
            _problem(field_path.lstrip("/"), message, _hint_for(field_path, code))
        )

    if not problems:
        message = payload.get("message") if isinstance(payload, dict) else str(exc.payload)
        problems.append(
            _problem(
                "campaign",
                f"LinkedIn rejected the campaign (HTTP {exc.status_code}): {message}",
                "Review the draft and re-propose; adjust the flagged field if shown.",
            )
        )
    return problems


__all__ = [
    "AUDIENCE_MIN_SIZE",
    "CampaignValidationError",
    "Problem",
    "describe_constraints",
    "explain_linkedin_error",
    "preflight_problems",
]
