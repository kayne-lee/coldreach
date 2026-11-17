"""Paths and loading of the user's local (gitignored) files."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path.cwd()
TEMPLATES = ROOT / "templates"
DATA = ROOT / "data"
OUT = ROOT / "out"
CONTACTS_CACHE = DATA / "contacts.json"
SENT_LOG = DATA / "sent.json"

TRACKS = ("intern", "newgrad")
TARGETS = ("recruiter", "founder", "engineering")
DEFAULT_TARGET = {"intern": "founder", "newgrad": "recruiter"}


class ConfigError(Exception):
    pass


def load_env() -> None:
    load_dotenv(ROOT / ".env")


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise ConfigError(f"{name} is not set. Add it to .env (see .env.example).")
    return value


def _yaml(path: Path, example: str):
    if not path.exists():
        raise ConfigError(f"{path.name} not found. Copy {example} to {path.name} and fill it in.")
    return yaml.safe_load(path.read_text()) or {}


def load_profile() -> dict:
    profile = _yaml(ROOT / "profile.yaml", "profile.example.yaml")
    for key in ("first_name", "from_email", "signature", "proof"):
        if not profile.get(key):
            raise ConfigError(f"profile.yaml is missing '{key}'.")
    return profile


def load_companies() -> list[dict]:
    companies = _yaml(ROOT / "companies.yaml", "companies.example.yaml")
    if not isinstance(companies, list):
        raise ConfigError("companies.yaml should be a list of companies.")
    for c in companies:
        if not c.get("name") or not c.get("domain"):
            raise ConfigError(f"Every company needs a name and a domain: {c}")
        c["domain"] = c["domain"].lower().removeprefix("https://").removeprefix("www.").strip("/")
        c.setdefault("track", "newgrad")
        if c["track"] not in TRACKS:
            raise ConfigError(f"{c['name']}: track must be one of {TRACKS}.")
        c.setdefault("target", DEFAULT_TARGET[c["track"]])
        if c["target"] not in TARGETS:
            raise ConfigError(f"{c['name']}: target must be one of {TARGETS}.")
        c["hook"] = " ".join((c.get("hook") or "").split())
    return companies


def load_manual_contacts() -> dict[str, list[dict]]:
    """contacts.csv: people you found yourself. Keyed by lowercase company name."""
    path = ROOT / "contacts.csv"
    by_company: dict[str, list[dict]] = {}
    if not path.exists():
        return by_company
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            email = (row.get("email") or "").strip().lower()
            if not email:
                continue
            by_company.setdefault((row.get("company") or "").strip().lower(), []).append(
                {
                    "email": email,
                    "first_name": (row.get("first_name") or "").strip(),
                    "last_name": (row.get("last_name") or "").strip(),
                    "title": (row.get("title") or "").strip(),
                    "confidence": None,
                    "verification": "manual",
                    "source": "manual",
                }
            )
    return by_company


def read_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))
