"""
Cold + followup templates for the hr_advisory lane.

Imported by pitch_hr_advisory.py. Kept here (next to scraper + seeds) so the
vertical is self-contained — same pattern as outreach/verticals/property_management/.

Hook (option 5b from Steven 2026-06-17): free 30-min HR workflow audit. NO
rate-card in cold or followup. Rate ($1,000/hr) only surfaces if recipient
asks directly — see senders/hr_advisory.json `pricing_disclosure_policy`.

Differentiator vs the existing claudesonnet111 pitch:
  - claudesonnet111 = trades-SMB-Westchester, "small AI agents + websites"
  - hr_advisory     = HR-vertical, "AI on top of your existing stack
                      (Workday/Greenhouse/Lattice)" — workflow-specific
  - Both honest about AI co-author (Smore Labs brand). HR version puts the
    transparency line in a P.S. so it doubles as the demo for an AI-consulting
    audience that knows what good AI-assisted copy reads like.
"""
from __future__ import annotations

SENDER_EMAIL = "claudesonnet111@gmail.com"
SENDER_NAME = "Steven Samori | Smore Labs AI Advisory"


SUBJECT_VARIANTS = [
    "30-min AI workflow audit for {company} HR?",
    "Quick AI audit for one {company} HR workflow",
    "AI on one HR workflow at {company} — 30 min?",
]


def hr_advisory_cold(first_name: str, company: str, subject_variant: str | None = None) -> dict:
    salutation = f"Hi {first_name.split()[0]}" if first_name else "Hi there"
    subject = (subject_variant or SUBJECT_VARIANTS[0]).format(company=company)
    return {
        "subject": subject,
        "body": (
            f"{salutation},\n\n"
            "Quick note from Steven — I build production AI agents for companies that want measurable workflow wins (not slide decks). "
            "I've been mapping where AI quietly takes hours out of HR ops: req-to-offer routing, screening pre-pass, onboarding workflow generation, candidate comms, headcount-plan modeling. "
            "Most of it isn't a new tool — it's an agent sitting on top of whatever you already run (Workday, Greenhouse, Lattice, etc.).\n\n"
            f"If you're open to it, I'd run a free 30-min audit of one HR workflow at {company} — your pick — and walk you through what I'd ship, what it'd save, and what it'd cost. "
            "No deck. Actual mockups against your real flow.\n\n"
            "Proof I ship production AI, not slideware:\n"
            "• Spirit Library — live iOS app, 1,700+ recipes, autonomous agents running it 24/7 (https://spiritlibrary.app)\n"
            "• 4 Seasons Organic — full ops calendar + drag-to-reschedule for an NYC cleaner (https://4seasons-ops.vercel.app)\n"
            "• Supreme Seams — 24/7 AI lead capture for an auto shop (https://supreme-seams.com)\n\n"
            "Open to 30 min on Zoom this week or next?\n\n"
            "Best,\n"
            "Steven Samori\n"
            "Smore Labs · AI Advisory\n"
            "P.S. This note was drafted by my AI co-pilot and reviewed by me before send — it's also the demo.\n\n"
            "—\n"
            "One-time intro. Reply 'unsubscribe' and you're off the list immediately.\n"
            "Smore Labs Inc · Westchester County, NY\n"
        ),
    }


def hr_advisory_followup(first_name: str, company: str) -> dict:
    salutation = f"Hi {first_name.split()[0]}" if first_name else "Following up"
    return {
        "subject": f"Re: 30-min AI workflow audit for {company} HR?",
        "body": (
            f"{salutation},\n\n"
            "Circling back on the free 30-min HR workflow audit.\n\n"
            "If it's not the right time, just reply 'no' and I'll close the loop.\n\n"
            f"If it'd be more useful than a call — I can put together a quick before/after mock of one specific {company} HR workflow (you pick) and send it over, so you can decide without a meeting.\n\n"
            "— Steven\n"
            "Smore Labs · AI Advisory\n"
        ),
    }
