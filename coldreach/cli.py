"""coldreach: find people, draft emails, review them, then send."""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import config, finder, sender
from .drafts import Draft, render

console = Console()


def build_queue(args) -> list[Draft]:
    """Everyone we would email right now, with the email each one would get."""
    profile = config.load_profile()
    companies = config.load_companies()
    if args.track:
        companies = [c for c in companies if c["track"] == args.track]
    manual = config.load_manual_contacts()
    api_key = os.environ.get("HUNTER_API_KEY")
    skip = sender.already_emailed()
    queue: list[Draft] = []
    for company in companies:
        try:
            people = finder.find_contacts(company, api_key, refresh=getattr(args, "refresh", False))
        except finder.FinderError as error:
            console.print(f"[red]{company['name']}: {error}[/red]")
            people = []
        chosen = finder.pick(
            company, people, manual.get(company["name"].lower(), []),
            args.per_company, args.min_confidence, skip,
        )
        if not chosen:
            reason = "no matching contacts" if (people or api_key) else "not searched yet (no HUNTER_API_KEY)"
            console.print(f"[yellow]{company['name']}: {reason}. Add someone to contacts.csv.[/yellow]")
        queue.extend(render(company, person, profile) for person in chosen)
    return queue


def followup_queue(args) -> list[Draft]:
    profile = config.load_profile()
    log = sender.load_log()
    followed = {e["email"] for e in log if e["kind"] == "followup"}
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    queue = []
    for entry in log:
        if entry["kind"] != "initial" or entry["replied"] or entry["email"] in followed:
            continue
        if datetime.fromisoformat(entry["sent_at"]) > cutoff:
            continue
        company = {"name": entry["company"], "track": entry["track"], "target": entry["target"]}
        person = {k: entry.get(k, "") for k in ("email", "first_name", "last_name", "title")}
        draft = render(company, person, profile, template="followup",
                       extra={"original_subject": entry["subject"]})
        draft.in_reply_to = entry["message_id"]
        queue.append(draft)
    return queue


def show(queue: list[Draft]) -> None:
    """The review screen: the full recipient list, then every email in full."""
    table = Table(title=f"{len(queue)} recipients", title_justify="left")
    for column in ("#", "Company", "Name", "Title", "Email", "Conf.", "Template", "Status"):
        table.add_column(column, overflow="fold")
    for i, d in enumerate(queue, 1):
        status = "[red]blocked[/red]" if d.blockers else ("[yellow]check[/yellow]" if d.warnings else "[green]ready[/green]")
        confidence = d.verification if d.confidence is None else f"{d.confidence}% {d.verification}"
        table.add_row(str(i), d.company, f"{d.first_name} {d.last_name}".strip(), d.title, d.to,
                      confidence, d.template, status)
    console.print(table)
    for i, d in enumerate(queue, 1):
        notes = [f"[red]BLOCKED: {b}[/red]" for b in d.blockers] + [f"[yellow]check: {w}[/yellow]" for w in d.warnings]
        text = f"[bold]To:[/bold] {d.to}\n[bold]Subject:[/bold] {d.subject}\n\n{d.body}"
        if notes:
            text += "\n\n" + "\n".join(notes)
        console.print(Panel(text, title=f"{i}. {d.company}", title_align="left"))


def deliver(queue: list[Draft], kind: str, args) -> None:
    profile = config.load_profile()
    ready = [d for d in queue if d.sendable][: args.limit]
    blocked = len([d for d in queue if not d.sendable])
    if blocked:
        console.print(f"[red]{blocked} blocked email(s) will not be sent.[/red]")
    if not ready:
        console.print("Nothing to send.")
        return
    if args.dry_run:
        console.print(f"Dry run: would send {len(ready)} email(s) from {profile['from_email']}.")
        return
    if not sys.stdin.isatty():
        console.print("[red]Sending needs a terminal so you can confirm. Nothing sent.[/red]")
        return
    answer = console.input(
        f"\nSend {len(ready)} email(s) from [bold]{profile['from_email']}[/bold]? Type [bold]send[/bold] to confirm: "
    )
    if answer.strip().lower() != "send":
        console.print("Nothing sent.")
        return
    with sender.Mailer() as mailer:
        for i, draft in enumerate(ready):
            message = sender.build_message(draft, profile)
            try:
                mailer.send(message)
            except Exception as error:  # keep going; one bad address should not stop the batch
                console.print(f"[red]failed: {draft.to}: {error}[/red]")
                continue
            sender.record(draft, message, kind)
            console.print(f"[green]sent[/green] {draft.to}")
            if i < len(ready) - 1:
                time.sleep(random.uniform(args.min_gap, args.min_gap * 2))


def cmd_find(args) -> None:
    api_key = config.env("HUNTER_API_KEY")
    for company in config.load_companies():
        try:
            people = finder.find_contacts(company, api_key, refresh=args.refresh)
        except finder.FinderError as error:
            console.print(f"[red]{company['name']}: {error}[/red]")
            continue
        console.print(f"{company['name']}: {len(people)} {company['target']} contact(s) from Hunter")


def cmd_review(args) -> None:
    queue = build_queue(args)
    show(queue)


def cmd_send(args) -> None:
    queue = build_queue(args)
    show(queue)
    deliver(queue, "initial", args)


def cmd_followup(args) -> None:
    queue = followup_queue(args)
    if not queue:
        console.print(f"No one is due a follow-up (sent {args.days}+ days ago, no reply, not followed up).")
        return
    show(queue)
    if args.send:
        deliver(queue, "followup", args)
    else:
        console.print("Run with --send to send these.")


def cmd_export(args) -> None:
    """Write .eml drafts you can open in Outlook or Apple Mail and send by hand."""
    profile = config.load_profile()
    queue = [d for d in build_queue(args) if d.sendable]
    config.OUT.mkdir(exist_ok=True)
    for draft in queue:
        message = sender.build_message(draft, profile)
        message["X-Unsent"] = "1"
        name = re.sub(r"[^a-z0-9]+", "-", f"{draft.company}-{draft.first_name}".lower()).strip("-")
        (config.OUT / f"{name}.eml").write_bytes(bytes(message))
    console.print(f"Wrote {len(queue)} draft(s) to {config.OUT}/. They are not logged as sent.")


def cmd_replied(args) -> None:
    count = sender.mark_replied(args.email)
    console.print(f"Marked {count} message(s) to {args.email} as replied." if count else "No sent email to that address.")


def cmd_status(args) -> None:
    log = sender.load_log()
    table = Table(title=f"{len(log)} sent", title_justify="left")
    for column in ("Sent", "Company", "Name", "Email", "Kind", "Replied"):
        table.add_column(column)
    for e in log:
        table.add_row(e["sent_at"][:10], e["company"], e["first_name"], e["email"], e["kind"],
                      "yes" if e["replied"] else "")
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(prog="coldreach", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def queue_options(p):
        p.add_argument("--track", choices=config.TRACKS, help="only this track")
        p.add_argument("--per-company", type=int, default=1, help="people to email per company (default 1)")
        p.add_argument("--min-confidence", type=int, default=70, help="minimum Hunter confidence (default 70)")
        p.add_argument("--refresh", action="store_true", help="search Hunter again instead of using the cache")

    def send_options(p):
        p.add_argument("--limit", type=int, default=20, help="most emails to send in one run (default 20)")
        p.add_argument("--min-gap", type=float, default=45, help="seconds between sends, randomised up to 2x")
        p.add_argument("--dry-run", action="store_true", help="show everything, send nothing")

    p = sub.add_parser("find", help="search Hunter for contacts at every company")
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(run=cmd_find)

    p = sub.add_parser("review", help="show who would be emailed and the exact email each would get")
    queue_options(p)
    p.set_defaults(run=cmd_review)

    p = sub.add_parser("send", help="review, confirm, then send")
    queue_options(p)
    send_options(p)
    p.set_defaults(run=cmd_send)

    p = sub.add_parser("export", help="write .eml drafts to out/ to send from your own mail app")
    queue_options(p)
    p.set_defaults(run=cmd_export)

    p = sub.add_parser("followup", help="one follow-up to people who have not replied")
    p.add_argument("--days", type=int, default=6, help="days since the first email (default 6)")
    p.add_argument("--send", action="store_true")
    send_options(p)
    p.set_defaults(run=cmd_followup)

    p = sub.add_parser("replied", help="mark someone as having replied so they get no follow-up")
    p.add_argument("email")
    p.set_defaults(run=cmd_replied)

    p = sub.add_parser("status", help="list everything sent so far")
    p.set_defaults(run=cmd_status)

    args = parser.parse_args()
    config.load_env()
    try:
        args.run(args)
    except config.ConfigError as error:
        console.print(f"[red]{error}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
