from coldreach import finder
from coldreach.drafts import render
from coldreach.sender import build_message

PROFILE = {
    "first_name": "Alex",
    "from_email": "alex@example.com",
    "school": "Waterloo",
    "degree": "computer engineering",
    "graduation": "April 2027",
    "intern_window": "January to April 2027",
    "newgrad_start": "July or August 2027",
    "proof": {"intern": "I built a thing with 2M users.", "newgrad": "I did three internships."},
    "signature": "Alex Chen\ngithub.com/alexchen",
}
PERSON = {"email": "jane@acme.com", "first_name": "Jane", "last_name": "Doe", "title": "CTO",
          "confidence": 95, "verification": "valid"}


def company(**overrides):
    base = {"name": "Acme", "domain": "acme.com", "track": "intern", "target": "founder",
            "hook": "I used your API in a side project."}
    return {**base, **overrides}


def test_recruiter_titles_are_ranked_and_filtered():
    assert finder.score("University Recruiter", "recruiter", 90, "valid") > finder.score(
        "Talent Acquisition Partner", "recruiter", 90, "valid")
    assert finder.score("Payroll Specialist", "recruiter", 99, "valid") is None
    assert finder.score("International HR Lead", "recruiter", 99, "valid") is None  # not "intern"


def test_pick_skips_low_confidence_already_emailed_and_nameless():
    people = [
        {**PERSON, "email": "a@acme.com", "title": "Founder", "confidence": 40},
        {**PERSON, "email": "b@acme.com", "title": "Co-founder & CEO"},
        {**PERSON, "email": "c@acme.com", "title": "CTO"},
        {**PERSON, "email": "d@acme.com", "title": "Founder", "first_name": ""},
    ]
    chosen = finder.pick(company(), people, [], per_company=3, min_confidence=70, skip={"b@acme.com"})
    assert [p["email"] for p in chosen] == ["c@acme.com"]


def test_render_fills_everything_and_stays_short():
    draft = render(company(), PERSON, PROFILE)
    assert draft.template == "intern_founder"
    assert draft.sendable and not draft.warnings
    assert "{" not in draft.subject + draft.body
    assert draft.body.startswith("Hi Jane,")
    assert "I used your API in a side project." in draft.body
    assert "\n\n\n" not in draft.body


def test_founder_email_without_hook_is_blocked_recruiter_only_warned():
    assert not render(company(hook=""), PERSON, PROFILE).sendable
    recruiter = render(company(hook="", track="newgrad", target="recruiter"), PERSON, PROFILE)
    assert recruiter.sendable and recruiter.warnings


def test_role_line_only_appears_when_a_role_is_given():
    base = company(track="newgrad", target="recruiter")
    assert "posting" not in render(base, PERSON, PROFILE).body
    assert "Software Engineer, New Grad posting" in render(
        {**base, "role": "Software Engineer, New Grad"}, PERSON, PROFILE).body


def test_stock_phrases_are_flagged():
    draft = render(company(hook="I am passionate about your mission."), PERSON, PROFILE)
    assert any("passionate" in w for w in draft.warnings)


def test_followup_threads_onto_the_first_email():
    draft = render(company(), PERSON, PROFILE, template="followup",
                   extra={"original_subject": "Winter intern at Acme?"})
    draft.in_reply_to = "<abc@example.com>"
    message = build_message(draft, PROFILE)
    assert message["Subject"] == "Re: Winter intern at Acme?"
    assert message["In-Reply-To"] == "<abc@example.com>"
    assert message.get_content_type() == "text/plain"
