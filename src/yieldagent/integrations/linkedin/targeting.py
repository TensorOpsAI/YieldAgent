"""Resolve Audience B2B facets into LinkedIn `targetingCriteria` URNs.

An LLM extracts free-text facet names from a brief ("Marketing", "Director",
"Programmatic Advertising"); LinkedIn's `targetingCriteria` needs entity URNs.
This module bridges the two, choosing a resolution path per facet based on what
the API exposes (the `availableEntityFinders` on `GET /adTargetingFacets`):

  * Closed enums — seniorities, jobFunctions — do NOT support the typeahead
    finder. Their full taxonomy (with display names) comes from the
    standardized-data endpoints `/seniorities` and `/functions`; we fetch once
    and match names against it. URNs are `urn:li:seniority:{id}` / `urn:li:function:{id}`.
  * Open taxonomies — industries, titles, skills — are resolved via the
    typeahead finder, which returns `{urn, name}` ranked by relevance.
  * company_sizes — a fixed 9-bucket enum whose targeting values are range
    tuple URNs (`urn:li:staffCountRange:(min,max)`), mapped statically.
  * locations — the brief carries ISO 3166-1 alpha-2 codes; each is expanded to
    its country name via `pycountry` and resolved through the same typeahead
    finder, so any country works (not just a hardcoded shortlist).

Names that resolve to no real LinkedIn URN are never guessed: they are collected
in `ResolvedTargeting.unresolved` so the caller can surface them as a manual step
in Campaign Manager. Every URN that *is* used was returned by LinkedIn itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import pycountry

from yieldagent.domain import Audience

FACET_LOCATIONS = "urn:li:adTargetingFacet:locations"
FACET_SENIORITIES = "urn:li:adTargetingFacet:seniorities"
FACET_JOB_FUNCTIONS = "urn:li:adTargetingFacet:jobFunctions"
FACET_INDUSTRIES = "urn:li:adTargetingFacet:industries"
FACET_TITLES = "urn:li:adTargetingFacet:titles"
FACET_SKILLS = "urn:li:adTargetingFacet:skills"
FACET_STAFF_COUNT = "urn:li:adTargetingFacet:staffCountRanges"

# LinkedIn requires at least one location. When a brief names no resolvable
# country we fall back to this (United States) so the campaign is still valid;
# the unresolved codes are still surfaced so the caller knows to fix them.
DEFAULT_GEO_URN = "urn:li:geo:103644278"

# Brief company-size buckets -> LinkedIn staffCountRange URNs. In targetingCriteria
# the value is a range tuple URN (min,max), NOT the SIZE_* enum the facet listing
# returns; the open-ended top bucket uses INT_MAX (2147483647) as its upper bound.
COMPANY_SIZE_TO_STAFF_RANGE: dict[str, str] = {
    "1": "urn:li:staffCountRange:(1,1)",
    "2-10": "urn:li:staffCountRange:(2,10)",
    "11-50": "urn:li:staffCountRange:(11,50)",
    "51-200": "urn:li:staffCountRange:(51,200)",
    "201-500": "urn:li:staffCountRange:(201,500)",
    "501-1000": "urn:li:staffCountRange:(501,1000)",
    "1001-5000": "urn:li:staffCountRange:(1001,5000)",
    "5001-10000": "urn:li:staffCountRange:(5001,10000)",
    "10001+": "urn:li:staffCountRange:(10001,2147483647)",
}


class _TargetingClient(Protocol):
    async def typeahead_targeting_entities(
        self, *, facet: str, query: str
    ) -> list[dict[str, Any]]: ...
    async def list_seniorities(self) -> list[dict[str, Any]]: ...
    async def list_functions(self) -> list[dict[str, Any]]: ...


@dataclass
class ResolvedTargeting:
    criteria: dict[str, Any]
    unresolved: dict[str, list[str]] = field(default_factory=dict)


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().replace("-", " ").split())


def _norm_size(value: str) -> str:
    return value.strip().lower().replace(" ", "")


def localized_name(entity: dict[str, Any]) -> str | None:
    """Pull the en_US display name out of a LinkedIn standardized-taxonomy entity."""
    return entity.get("name", {}).get("localized", {}).get("en_US")


def _country_name(code: str) -> str | None:
    """Map an ISO 3166-1 alpha-2 code to a country name LinkedIn will recognise.

    Prefers the colloquial `common_name` (e.g. "South Korea" over "Korea,
    Republic of") since that is what the locations typeahead indexes. Returns
    None for codes `pycountry` does not know, so they surface as unresolved.
    """
    country = pycountry.countries.get(alpha_2=code.strip().upper())
    if country is None:
        return None
    return getattr(country, "common_name", None) or country.name


def _best_typeahead_match(query: str, hits: list[dict[str, Any]]) -> str | None:
    """Prefer an exact (normalized) name match; else LinkedIn's top-ranked hit.

    Returns None only when typeahead found nothing — we never fabricate a URN.
    """
    if not hits:
        return None
    target = _norm(query)
    for hit in hits:
        if _norm(hit.get("name", "")) == target:
            return hit.get("urn")
    return hits[0].get("urn")


class TargetingResolver:
    """Resolves an `Audience` into a LinkedIn `targetingCriteria` payload.

    Standardized lists are fetched lazily and cached for the resolver's lifetime
    (one publish), so repeated facets cost a single round-trip each.
    """

    def __init__(self, client: _TargetingClient) -> None:
        self._client = client
        self._seniority_index: dict[str, str] | None = None
        self._function_index: dict[str, str] | None = None

    async def _seniorities(self) -> dict[str, str]:
        if self._seniority_index is None:
            self._seniority_index = {
                _norm(name): f"urn:li:seniority:{e['id']}"
                for e in await self._client.list_seniorities()
                if (name := localized_name(e))
            }
        return self._seniority_index

    async def _functions(self) -> dict[str, str]:
        if self._function_index is None:
            self._function_index = {
                _norm(name): f"urn:li:function:{e['id']}"
                for e in await self._client.list_functions()
                if (name := localized_name(e))
            }
        return self._function_index

    @staticmethod
    def _resolve_against_index(
        names: list[str], index: dict[str, str]
    ) -> tuple[list[str], list[str]]:
        urns: list[str] = []
        unresolved: list[str] = []
        for name in names:
            urn = index.get(_norm(name))
            if urn:
                urns.append(urn)
            else:
                unresolved.append(name)
        return urns, unresolved

    async def _resolve_typeahead(
        self, facet: str, names: list[str]
    ) -> tuple[list[str], list[str]]:
        urns: list[str] = []
        unresolved: list[str] = []
        for name in names:
            hits = await self._client.typeahead_targeting_entities(facet=facet, query=name)
            urn = _best_typeahead_match(name, hits)
            if urn:
                urns.append(urn)
            else:
                unresolved.append(name)
        return urns, unresolved

    @staticmethod
    def _resolve_company_sizes(sizes: list[str]) -> tuple[list[str], list[str]]:
        values: list[str] = []
        unresolved: list[str] = []
        for size in sizes:
            value = COMPANY_SIZE_TO_STAFF_RANGE.get(_norm_size(size))
            if value:
                values.append(value)
            else:
                unresolved.append(size)
        return values, unresolved

    async def _resolve_geos(self, audience: Audience) -> tuple[list[str], list[str]]:
        """Resolve ISO country codes to geo URNs via the locations typeahead.

        Each code is expanded to a country name (`pycountry`) and looked up; a
        code we cannot expand, or that the typeahead does not match, is returned
        as unresolved. Falls back to the default location when nothing resolves,
        since LinkedIn requires at least one.
        """
        urns: list[str] = []
        unresolved: list[str] = []
        for raw in audience.geos:
            code = raw.strip().upper()
            name = _country_name(code)
            urn = None
            if name:
                hits = await self._client.typeahead_targeting_entities(
                    facet=FACET_LOCATIONS, query=name
                )
                urn = _best_typeahead_match(name, hits)
            if urn:
                urns.append(urn)
            else:
                unresolved.append(code)
        return urns or [DEFAULT_GEO_URN], unresolved

    async def resolve(self, audience: Audience) -> ResolvedTargeting:
        geo_urns, geo_unresolved = await self._resolve_geos(audience)
        clauses: list[dict[str, Any]] = [{"or": {FACET_LOCATIONS: geo_urns}}]
        unresolved: dict[str, list[str]] = {}
        if geo_unresolved:
            unresolved["geos"] = geo_unresolved

        def _add(facet: str, urns: list[str], missing: list[str], key: str) -> None:
            if urns:
                clauses.append({"or": {facet: urns}})
            if missing:
                unresolved[key] = missing

        if audience.seniorities:
            urns, missing = self._resolve_against_index(
                audience.seniorities, await self._seniorities()
            )
            _add(FACET_SENIORITIES, urns, missing, "seniorities")

        if audience.job_functions:
            urns, missing = self._resolve_against_index(
                audience.job_functions, await self._functions()
            )
            _add(FACET_JOB_FUNCTIONS, urns, missing, "job_functions")

        if audience.industries:
            urns, missing = await self._resolve_typeahead(FACET_INDUSTRIES, audience.industries)
            _add(FACET_INDUSTRIES, urns, missing, "industries")

        if audience.job_titles:
            urns, missing = await self._resolve_typeahead(FACET_TITLES, audience.job_titles)
            _add(FACET_TITLES, urns, missing, "job_titles")

        if audience.skills:
            urns, missing = await self._resolve_typeahead(FACET_SKILLS, audience.skills)
            _add(FACET_SKILLS, urns, missing, "skills")

        if audience.company_sizes:
            values, missing = self._resolve_company_sizes(audience.company_sizes)
            _add(FACET_STAFF_COUNT, values, missing, "company_sizes")

        return ResolvedTargeting(criteria={"include": {"and": clauses}}, unresolved=unresolved)


__all__ = [
    "COMPANY_SIZE_TO_STAFF_RANGE",
    "DEFAULT_GEO_URN",
    "FACET_INDUSTRIES",
    "FACET_JOB_FUNCTIONS",
    "FACET_LOCATIONS",
    "FACET_SENIORITIES",
    "FACET_SKILLS",
    "FACET_STAFF_COUNT",
    "FACET_TITLES",
    "ResolvedTargeting",
    "TargetingResolver",
    "localized_name",
]
