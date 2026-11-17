"""Find the right people at a company through Hunter's Domain Search."""

from __future__ import annotations

import re

import requests

from . import config

HUNTER_URL = "https://api.hunter.io/v2/domain-search"

# Per target: the Hunter filter, and title keywords ordered best-first.
SEARCH = {
    "recruiter": {
        "params": {"department": "hr"},
        "keywords": [
            "university", "campus", "early career", "early talent", "emerging talent",
            "new grad", "intern", "technical recruiter", "engineering recruiter",
            "recruiter", "recruiting", "recruitment", "talent acquisition", "sourcer", "talent",
        ],
        "exclude": ["payroll", "benefits", "compensation", "executive recruiter", "sales recruiter"],
    },
    "founder": {
        "params": {"seniority": "executive"},
        "keywords": [
            "founder", "cto", "chief technology", "ceo", "chief executive",
            "head of engineering", "vp of engineering", "vp engineering",
        ],
        "exclude": ["assistant"],
    },
    "engineering": {
        "params": {"department": "it", "seniority": "senior,executive"},
        "keywords": [
            "engineering manager", "head of engineering", "director of engineering",
            "vp of engineering", "vp engineering", "tech lead", "team lead",
            "staff", "principal", "engineer",
        ],
        "exclude": ["sales engineer", "support"],
    },
}


class FinderError(Exception):
    pass


def _has(title: str, keyword: str) -> bool:
    return re.search(rf"\b{re.escape(keyword)}\b", title) is not None


def score(title: str, target: str, confidence: int | None, verification: str | None) -> float | None:
    """Higher is better. None means this person is not who we want."""
    title = (title or "").lower()
    spec = SEARCH[target]
    if any(_has(title, word) for word in spec["exclude"]):
        return None
    rank = next((i for i, word in enumerate(spec["keywords"]) if _has(title, word)), None)
    if rank is None:
        return None
    points = float(len(spec["keywords"]) - rank)
    points += (confidence or 0) / 100
    if verification == "valid":
        points += 0.5
    return points


def hunter_search(domain: str, target: str, api_key: str) -> list[dict]:
    params = {"domain": domain, "type": "personal", "limit": 10, **SEARCH[target]["params"]}
    try:
        response = requests.get(HUNTER_URL, params=params, headers={"X-API-KEY": api_key}, timeout=30)
    except requests.RequestException as error:
        raise FinderError(f"Could not reach Hunter: {error}") from error
    if response.status_code == 401:
        raise FinderError("Hunter rejected the API key. Check HUNTER_API_KEY in .env.")
    if response.status_code == 429:
        raise FinderError("Hunter monthly search quota is used up.")
    if response.status_code != 200:
        raise FinderError(f"Hunter returned {response.status_code} for {domain}: {response.text[:200]}")
    people = []
    for item in response.json().get("data", {}).get("emails", []):
        people.append(
            {
                "email": (item.get("value") or "").lower(),
                "first_name": item.get("first_name") or "",
                "last_name": item.get("last_name") or "",
                "title": item.get("position") or "",
                "confidence": item.get("confidence"),
                "verification": (item.get("verification") or {}).get("status") or "unknown",
                "linkedin": item.get("linkedin"),
                "source": "hunter",
            }
        )
    return people


def find_contacts(company: dict, api_key: str | None, refresh: bool = False) -> list[dict]:
    """Raw people for a company and target. Cached so a search costs one credit, once."""
    cache = config.read_json(config.CONTACTS_CACHE, {})
    key = f"{company['domain']}|{company['target']}"
    if refresh or key not in cache:
        if not api_key:
            return []
        cache[key] = hunter_search(company["domain"], company["target"], api_key)
        config.write_json(config.CONTACTS_CACHE, cache)
    return cache[key]


def pick(company: dict, people: list[dict], manual: list[dict], per_company: int,
         min_confidence: int, skip: set[str]) -> list[dict]:
    """Best contacts to email: manual ones first, then Hunter results by title fit."""
    chosen = [p for p in manual if p["email"] not in skip]
    ranked = []
    for person in people:
        if person["email"] in skip or not person["email"] or not person["first_name"]:
            continue
        if person["verification"] == "invalid" or (person["confidence"] or 0) < min_confidence:
            continue
        points = score(person["title"], company["target"], person["confidence"], person["verification"])
        if points is not None:
            ranked.append((points, person))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    seen = {p["email"] for p in chosen}
    for _, person in ranked:
        if person["email"] not in seen:
            chosen.append(person)
            seen.add(person["email"])
    return chosen[:per_company]
