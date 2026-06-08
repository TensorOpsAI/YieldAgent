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

from yieldagent.domain import BiddingStrategy

from .client import LinkedInClient, LinkedInError


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
# proportionally larger total. Observed: EUR daily min 10.
_MIN_DAILY_BUDGET: dict[str, Decimal] = {
    "EUR": Decimal("10"),
    "USD": Decimal("10"),
    "GBP": Decimal("10"),
}
_DEFAULT_MIN_DAILY_BUDGET = Decimal("10")

# LinkedIn's privacy floor: an audience under this size cannot run.
AUDIENCE_MIN_SIZE = 300


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
        "audience": {"min_size": AUDIENCE_MIN_SIZE},
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

        # An explicit daily budget must clear the per-day minimum.
        if li.daily_budget is not None:
            cur = li.daily_budget.currency.upper()
            min_daily = _MIN_DAILY_BUDGET.get(cur, _DEFAULT_MIN_DAILY_BUDGET)
            if Decimal(li.daily_budget.amount) < min_daily:
                problems.append(
                    _problem(
                        f"line_items[{li.name}].daily_budget",
                        f"Daily budget {li.daily_budget.amount} {cur} is below the "
                        f"minimum {min_daily} {cur}.",
                        f"Raise the daily budget to at least {min_daily} {cur}.",
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
