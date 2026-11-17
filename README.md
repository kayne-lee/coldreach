# coldreach

Find the right person at a company, draft a short cold email to them, show you every recipient and every email, and only then send.

Built for a student job search: winter internships at startups and new grad roles at bigger companies. Nothing is sent until you have seen the full list and typed `send`.

## How it works

1. You list companies in `companies.yaml` with a track (`intern` or `newgrad`) and one sentence about each (the hook).
2. `coldreach find` asks [Hunter](https://hunter.io) for people at each domain: recruiters and campus hiring for big companies, founders or engineering leads for startups. It ranks them by job title and drops low-confidence addresses.
3. `coldreach review` prints a table of everyone it would email, then each email in full, with warnings on anything that reads like a template.
4. `coldreach send` shows the same review, asks you to type `send`, then sends plain-text emails one at a time with a random gap, and logs them so nobody is emailed twice.
5. `coldreach followup` drafts a single follow-up, threaded onto the first email, for people who have not replied after 6 days.

## Setup

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
cp profile.example.yaml profile.yaml
cp companies.example.yaml companies.yaml
```

Then fill in:

- `.env`: a Hunter API key (the free plan covers roughly 50 company searches a month) and SMTP login. For Gmail, use an [app password](https://myaccount.google.com/apppasswords). Personal Outlook.com accounts no longer accept password SMTP logins, so use `coldreach export` there (see below).
- `profile.yaml`: who you are and one or two sentences of proof per track.
- `companies.yaml`: your targets.

All three are gitignored, along with `data/` and `out/`.

## Commands

```bash
uv run coldreach find                 # look up contacts (cached, one Hunter credit per company)
uv run coldreach review               # recipient list + every email, sends nothing
uv run coldreach send                 # review, confirm, send (max 20 per run)
uv run coldreach send --dry-run       # the full send flow without sending
uv run coldreach export               # write .eml drafts to out/ for Outlook or Apple Mail
uv run coldreach followup             # show follow-ups that are due
uv run coldreach followup --send      # send them
uv run coldreach replied a@b.com      # stop follow-ups to someone who answered
uv run coldreach status               # everything sent so far
```

Useful flags on `review`, `send` and `export`: `--track intern`, `--per-company 2`, `--min-confidence 80`, `--refresh`.

Found someone yourself on LinkedIn or a team page? Add them to `contacts.csv` (see `contacts.example.csv`). Manual contacts are used before Hunter results.

## The emails

Templates are plain text files in `templates/`, one per track and audience. The first line is the subject. Edit them freely, in your own voice.

| File | For |
| --- | --- |
| `intern_founder.txt` | Winter internship, to a founder or engineering lead |
| `intern_recruiter.txt` | Winter internship, to a recruiter |
| `newgrad_recruiter.txt` | New grad role, to a recruiter or campus hiring |
| `newgrad_founder.txt` | New grad role, to a founder or engineering lead |
| `followup.txt` | One follow-up, sent as a reply to the first email |

Every email has the same four parts, in under about 100 words:

1. **Hook**: one sentence about this company that only you could write. It comes from `companies.yaml`, not from a template, which is the whole point. Founder emails are blocked without one.
2. **Who you are**: school, year, what you want and when.
3. **Proof**: one concrete thing you built, with a number.
4. **One small ask**: a yes/no question that is easy to answer from a phone.

The review step flags emails over 120 words, long dashes, stacked exclamation marks, and stock phrases such as "I hope this email finds you well", "passionate" and "I wanted to reach out".

## Why the templates look like this

Most published numbers on cold email come from sales-tool vendors measuring B2B sales outreach, so treat them as directional rather than proven for job hunting. The points below are the ones several independent sources agree on.

- **Short.** Guides for job seekers cap emails at about 200 words and recommend 6 to 7 lines; sales datasets put the best reply rates under 100 words. Recruiters skim in seconds. ([Next Play](https://nextplayso.substack.com/p/the-guide-to-getting-a-job-with-cold), [The Hustling Engineer](https://thehustlingengineer.substack.com/p/cold-outreach-messages-that-actually), [Autobound](https://www.autobound.ai/blog/how-writing-style-impacts-sales-email-performance))
- **Who you are, why you are writing, why they should care, one ask.** The most common failure is no clear ask. ([Next Play](https://nextplayso.substack.com/p/the-guide-to-getting-a-job-with-cold))
- **Real personalization beats merge fields.** In one 5.5M-email dataset, reply rate went from 3% to 7% with personalization. Fake familiarity ("huge fan", "saw your post") is worse than none. ([Belkins](https://belkins.io/blog/b2b-cold-email-subject-line-statistics))
- **Short, specific subject lines.** 2 to 4 words had the highest open rate in the same dataset, and questions did well. Jargon and urgency words did worst. ([Belkins](https://belkins.io/blog/b2b-cold-email-subject-line-statistics))
- **Email the person who decides.** At a startup under about 50 people that is a founder; at a large company it is a recruiter or campus hiring, never the CEO. ([Whali](https://whali.co.uk/blog/cold-email-ceo-founder-internship))
- **Concrete proof, plain words.** "Built X used by 200 people" instead of "drove results". Read it aloud; if you would not say it, cut it. ([Next Play](https://nextplayso.substack.com/p/the-guide-to-getting-a-job-with-cold))
- **Follow up once.** A second or third chase costs more goodwill than it earns.
- **Plain text, no tracking.** Open-tracking pixels and heavy HTML hurt deliverability, so this tool sends neither and attaches nothing.

Expect most emails to go unanswered. Self-reported reply rates for student outreach sit around 5 to 10%, which is why the quality of the list and the hook matter more than volume.

## Being a decent sender

- One person per company by default. Emailing five people at the same startup gets noticed, badly.
- 20 emails per run with 45 to 90 seconds between them, to keep your account out of spam folders.
- Nobody is emailed twice, and anyone marked as replied gets no follow-up.
- If someone asks you to stop, stop.

## Tests

```bash
uv run pytest
```
