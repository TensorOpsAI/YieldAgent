"""Tests for the B2B targeting resolver.

These pin the two resolution paths (standardized-enum lookup vs. typeahead),
the no-guess contract (unmatched names are surfaced, never fabricated into a
URN), the targetingCriteria shape, and that standardized lists are fetched once.
"""

from __future__ import annotations

from yieldagent.domain import Audience
from yieldagent.integrations.linkedin.targeting import (
    DEFAULT_GEO_URN,
    FACET_INDUSTRIES,
    FACET_JOB_FUNCTIONS,
    FACET_LOCATIONS,
    FACET_SENIORITIES,
    FACET_SKILLS,
    FACET_STAFF_COUNT,
    FACET_TITLES,
    TargetingResolver,
)

_US_GEO = "urn:li:geo:103644278"
_PT_GEO = "urn:li:geo:100364837"


def _named(id_: int, name: str) -> dict:
    return {"id": id_, "name": {"localized": {"en_US": name}}}


class _FakeTargetingClient:
    """Serves canned standardized lists + typeahead hits; counts list fetches."""

    def __init__(self) -> None:
        self.seniority_calls = 0
        self.function_calls = 0
        self.typeahead_calls: list[tuple[str, str]] = []
        # facet -> query(lowercased) -> hits
        self.typeahead: dict[str, dict[str, list[dict]]] = {
            FACET_LOCATIONS: {
                "united states": [{"urn": _US_GEO, "name": "United States"}],
                "portugal": [
                    {"urn": _PT_GEO, "name": "Portugal"},
                    {"urn": "urn:li:geo:105374601", "name": "Porto, Portugal"},
                ],
            },
            FACET_INDUSTRIES: {
                "advertising": [{"urn": "urn:li:industry:80", "name": "Advertising Services"}],
            },
            FACET_TITLES: {
                "marketing manager": [
                    {"urn": "urn:li:title:99", "name": "Senior Marketing Manager"},
                    {"urn": "urn:li:title:26", "name": "Marketing Manager"},
                ],
                "growth hacker": [{"urn": "urn:li:title:500", "name": "Growth Lead"}],
            },
            FACET_SKILLS: {
                "programmatic advertising": [
                    {"urn": "urn:li:skill:60778", "name": "Programmatic Advertising"}
                ],
            },
        }

    async def list_seniorities(self) -> list[dict]:
        self.seniority_calls += 1
        return [_named(6, "Director"), _named(7, "VP"), _named(8, "CXO")]

    async def list_functions(self) -> list[dict]:
        self.function_calls += 1
        return [_named(15, "Marketing"), _named(25, "Sales")]

    async def typeahead_targeting_entities(self, *, facet: str, query: str) -> list[dict]:
        self.typeahead_calls.append((facet, query))
        return self.typeahead.get(facet, {}).get(query.strip().lower(), [])


def _clause_facets(criteria: dict) -> dict[str, list]:
    """Flatten the include/and/or structure into {facetUrn: values}."""
    out: dict[str, list] = {}
    for clause in criteria["include"]["and"]:
        out.update(clause["or"])
    return out


async def test_geo_only_defaults_to_us_when_empty() -> None:
    resolver = TargetingResolver(_FakeTargetingClient())
    resolved = await resolver.resolve(Audience(description="x", geos=[]))
    assert _clause_facets(resolved.criteria) == {FACET_LOCATIONS: [DEFAULT_GEO_URN]}
    assert resolved.unresolved == {}


async def test_geos_resolve_via_typeahead_by_country_name() -> None:
    resolver = TargetingResolver(_FakeTargetingClient())
    resolved = await resolver.resolve(Audience(description="x", geos=["US", "PT"]))
    # "PT" -> "Portugal" exact match wins over "Porto, Portugal".
    assert _clause_facets(resolved.criteria) == {FACET_LOCATIONS: [_US_GEO, _PT_GEO]}
    assert resolved.unresolved == {}


async def test_unknown_geo_code_is_unresolved_not_guessed() -> None:
    resolver = TargetingResolver(_FakeTargetingClient())
    resolved = await resolver.resolve(Audience(description="x", geos=["ZZ"]))
    # Invalid ISO code -> surfaced as unresolved; locations falls back to default.
    assert _clause_facets(resolved.criteria) == {FACET_LOCATIONS: [DEFAULT_GEO_URN]}
    assert resolved.unresolved == {"geos": ["ZZ"]}


async def test_geo_codes_are_normalized_before_lookup() -> None:
    resolver = TargetingResolver(_FakeTargetingClient())
    resolved = await resolver.resolve(Audience(description="x", geos=[" us ", "Pt"]))
    # Whitespace/case variations still resolve to the same URNs.
    assert _clause_facets(resolved.criteria) == {FACET_LOCATIONS: [_US_GEO, _PT_GEO]}
    assert resolved.unresolved == {}


async def test_unresolved_geo_is_reported_normalized() -> None:
    resolver = TargetingResolver(_FakeTargetingClient())
    resolved = await resolver.resolve(Audience(description="x", geos=["zz "]))
    # Unresolved output is the normalized code, not the raw padded input.
    assert resolved.unresolved == {"geos": ["ZZ"]}


async def test_enum_facets_resolve_and_surface_misses() -> None:
    resolver = TargetingResolver(_FakeTargetingClient())
    resolved = await resolver.resolve(
        Audience(
            description="x",
            geos=["US"],
            seniorities=["Director", "VP", "Wizard"],  # Wizard has no match
            job_functions=["marketing"],  # case-insensitive
        )
    )
    facets = _clause_facets(resolved.criteria)
    assert facets[FACET_SENIORITIES] == ["urn:li:seniority:6", "urn:li:seniority:7"]
    assert facets[FACET_JOB_FUNCTIONS] == ["urn:li:function:15"]
    assert resolved.unresolved == {"seniorities": ["Wizard"]}


async def test_typeahead_prefers_exact_then_top_hit() -> None:
    resolver = TargetingResolver(_FakeTargetingClient())
    resolved = await resolver.resolve(
        Audience(
            description="x",
            geos=["US"],
            industries=["advertising"],
            job_titles=["Marketing Manager", "Growth Hacker"],
            skills=["Programmatic Advertising"],
        )
    )
    facets = _clause_facets(resolved.criteria)
    assert facets[FACET_INDUSTRIES] == ["urn:li:industry:80"]
    # "Marketing Manager" exact match wins over the higher-ranked "Senior..."; the
    # non-exact "Growth Hacker" falls back to LinkedIn's top hit (Growth Lead).
    assert facets[FACET_TITLES] == ["urn:li:title:26", "urn:li:title:500"]
    assert facets[FACET_SKILLS] == ["urn:li:skill:60778"]
    assert resolved.unresolved == {}


async def test_typeahead_no_hits_is_unresolved_not_guessed() -> None:
    resolver = TargetingResolver(_FakeTargetingClient())
    resolved = await resolver.resolve(
        Audience(description="x", geos=["US"], industries=["Nonexistent Industry"])
    )
    assert FACET_INDUSTRIES not in _clause_facets(resolved.criteria)
    assert resolved.unresolved == {"industries": ["Nonexistent Industry"]}


async def test_company_sizes_map_to_staff_ranges() -> None:
    resolver = TargetingResolver(_FakeTargetingClient())
    resolved = await resolver.resolve(
        Audience(description="x", geos=["US"], company_sizes=["11-50", "1001-5000", "bogus"])
    )
    facets = _clause_facets(resolved.criteria)
    assert facets[FACET_STAFF_COUNT] == [
        "urn:li:staffCountRange:(11,50)",
        "urn:li:staffCountRange:(1001,5000)",
    ]
    assert resolved.unresolved == {"company_sizes": ["bogus"]}


async def test_standardized_lists_fetched_once() -> None:
    client = _FakeTargetingClient()
    resolver = TargetingResolver(client)
    await resolver.resolve(Audience(description="x", geos=["US"], seniorities=["Director", "VP"]))
    await resolver.resolve(Audience(description="x", geos=["US"], seniorities=["CXO"]))
    assert client.seniority_calls == 1
