"""Turn a contact plus a template into an email, and check it reads like a person wrote it."""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field

from . import config

MAX_WORDS = 120

# Phrases that mark an email as templated or machine-written.
STOCK_PHRASES = [
    "i hope this email finds you well", "i hope you're doing well", "i hope this finds you",
    "my name is", "i am writing to", "i'm writing to", "i wanted to reach out",
    "passionate", "excited to", "thrilled", "leverage", "synergy", "delve",
    "fast-paced", "cutting-edge", "innovative", "i would be a great fit", "perfect fit",
    "pick your brain", "at your earliest convenience", "do not hesitate", "esteemed",
    "i came across your profile", "huge fan", "to whom it may concern",
]

ROLE_LINE = "I saw the {role} posting and wanted to reach out directly."
WHAT = {"intern": "a winter internship", "newgrad": "a new grad role"}


@dataclass
class Draft:
    to: str
    first_name: str
    last_name: str
    title: str
    company: str
    track: str
    target: str
    template: str
    subject: str
    body: str
    confidence: int | None = None
    verification: str = ""
    in_reply_to: str | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def sendable(self) -> bool:
        return not self.blockers


class _Fields(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.missing: list[str] = []

    def __missing__(self, key):
        self.missing.append(key)
        return "{" + key + "}"


def _load_template(name: str) -> tuple[str, str]:
    path = config.TEMPLATES / f"{name}.txt"
    if not path.exists():
        raise config.ConfigError(f"Template not found: {path}")
    head, _, body = path.read_text().partition("\n")
    if not head.lower().startswith("subject:"):
        raise config.ConfigError(f"{path.name} must start with a 'Subject:' line.")
    return head.split(":", 1)[1].strip(), body


def _tidy(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.strip().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


def lint(draft: Draft, signature: str) -> None:
    text = draft.body.replace(signature.strip(), "")
    words = len(text.split())
    if words > MAX_WORDS:
        draft.warnings.append(f"{words} words; aim for under {MAX_WORDS}")
    lowered = f"{draft.subject}\n{text}".lower().replace("’", "'")
    for phrase in STOCK_PHRASES:
        if phrase in lowered:
            draft.warnings.append(f'stock phrase: "{phrase}"')
    if "—" in text or "–" in text:
        draft.warnings.append("has a long dash; use a comma or period")
    if text.count("!") > 1:
        draft.warnings.append("more than one exclamation mark")


def render(company: dict, person: dict, profile: dict, template: str | None = None,
           extra: dict | None = None) -> Draft:
    track, target = company["track"], company["target"]
    if template is None:
        template = f"{track}_{'recruiter' if target == 'recruiter' else 'founder'}"
    subject_tpl, body_tpl = _load_template(template)

    role = (company.get("role") or "").strip()
    fields = _Fields(
        {key: value for key, value in profile.items() if isinstance(value, (str, int))},
        first_name=person["first_name"].strip(),
        company=company["name"],
        hook=company.get("hook", ""),
        proof=" ".join(str((profile.get("proof") or {}).get(track, "")).split()),
        role_line=ROLE_LINE.format(role=role) if role else "",
        what=WHAT[track],
        signature=profile["signature"].strip(),
        **(extra or {}),
    )
    formatter = string.Formatter()
    draft = Draft(
        to=person["email"],
        first_name=person["first_name"].strip(),
        last_name=person.get("last_name", ""),
        title=person.get("title", ""),
        company=company["name"],
        track=track,
        target=target,
        template=template,
        subject=_tidy(formatter.vformat(subject_tpl, (), fields)),
        body=_tidy(formatter.vformat(body_tpl, (), fields)),
        confidence=person.get("confidence"),
        verification=person.get("verification", ""),
    )

    for key in dict.fromkeys(fields.missing):
        draft.blockers.append(f"profile.yaml has no '{key}'")
    if not draft.first_name:
        draft.blockers.append("no first name; a 'Hi there' email is not worth sending")
    if not fields["proof"]:
        draft.blockers.append(f"profile.yaml has no proof for '{track}'")
    if template != "followup" and not fields["hook"]:
        message = "no hook: add one sentence about this company to companies.yaml"
        (draft.warnings if target == "recruiter" else draft.blockers).append(message)
    lint(draft, fields["signature"])
    return draft
