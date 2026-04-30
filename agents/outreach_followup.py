"""
Outreach Follow-up Agent — generates and sends follow-up emails
for anything sent 14+ days ago with no reply recorded.

Run manually:    python main.py outreach follow-up
Auto-scheduled:  runs via cron every day, only acts when targets are due
"""

import anthropic
import json
import os
import re
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

OUTREACH_DIR = Path(__file__).parent.parent / "outreach"
OUTBOX_FILE = OUTREACH_DIR / "outbox.json"
SENT_LOG_FILE = OUTREACH_DIR / "sent_log.json"
FOLLOWUP_LOG_FILE = OUTREACH_DIR / "followup_log.json"

FROM_NAME = "Steven Samori | Spirit Library"
FOLLOWUP_DAYS = 14


def _load_json(path: Path) -> list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def _save_json(path: Path, data):
    OUTREACH_DIR.mkdir(exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return json.loads(match.group())
        raise


def _generate_followup(client, original: dict) -> dict:
    """Generate a short, fresh follow-up email referencing the original pitch."""
    prompt = f"""You are writing a short follow-up email for Spirit Library, a cocktail recipe iOS app.

The original email was sent 2 weeks ago and hasn't received a reply yet.

ORIGINAL EMAIL:
Subject: {original.get('subject', '')}
To: {original.get('name', '')} ({original.get('category', '')})
Key hook: {original.get('key_hook', '')}

Write a brief, friendly follow-up (80-120 words MAX). Rules:
- Reference the original outreach in one line ("Following up on my note from two weeks ago...")
- Add ONE new angle or piece of value not in the original — a new feature, a new use case, or a timely hook
- Keep it genuinely short — busy people respond to short emails
- Single CTA: reply or a 15-min call
- No desperation, no "just checking in" — add real value
- Sign off: Steven Samori, Spirit Library

Respond as JSON only:
{{
  "subject": "Re: {original.get('subject', '')}",
  "body": "full follow-up email text"
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    return _extract_json(response.content[0].text)


def _send_email(to_email: str, subject: str, body: str) -> bool:
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{gmail_user}>"
    msg["To"] = to_email
    msg["Reply-To"] = gmail_user
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, to_email, msg.as_string())
    return True


def run_followups(dry_run: bool = False, days: int = FOLLOWUP_DAYS):
    """
    Find all emails sent {days}+ days ago with no follow-up, generate + send follow-ups.
    Safe to run daily — only acts when targets are actually due.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    outbox = _load_json(OUTBOX_FILE)
    followup_log = _load_json(FOLLOWUP_LOG_FILE)

    already_followed_up = {f["target_key"] for f in followup_log}
    cutoff = datetime.utcnow() - timedelta(days=days)

    due = []
    for e in outbox:
        if e.get("status") != "sent":
            continue
        if e["target_key"] in already_followed_up:
            continue
        if not e.get("contact_email"):
            continue
        sent_at = datetime.fromisoformat(e["sent_at"])
        if sent_at <= cutoff:
            due.append(e)

    print(f"\n📬 Follow-up check ({days}-day window)")
    print(f"   Due for follow-up: {len(due)}")
    print(f"   Already followed up: {len(already_followed_up)}")

    if not due:
        print("   Nothing due yet.")
        return

    if dry_run:
        print(f"\n🧪 DRY RUN — {len(due)} follow-ups would be sent:")
        for e in due:
            sent_date = e["sent_at"][:10]
            print(f"   - {e['name']} <{e['contact_email']}> (sent {sent_date})")
        return

    print(f"\n📤 Sending {len(due)} follow-ups...\n")

    for i, entry in enumerate(due, 1):
        print(f"[{i}/{len(due)}] → {entry['name']} <{entry['contact_email']}>")

        try:
            followup = _generate_followup(client, entry)

            _send_email(
                to_email=entry["contact_email"],
                subject=followup["subject"],
                body=followup["body"]
            )

            log_entry = {
                "target_key": entry["target_key"],
                "name": entry["name"],
                "contact_email": entry["contact_email"],
                "subject": followup["subject"],
                "body": followup["body"],
                "original_sent_at": entry["sent_at"],
                "followup_sent_at": datetime.utcnow().isoformat()
            }
            followup_log.append(log_entry)
            _save_json(FOLLOWUP_LOG_FILE, followup_log)

            print(f"   ✓ Sent follow-up")
            print(f"   Subject: {followup['subject']}")

            if i < len(due):
                time.sleep(90)

        except Exception as e:
            print(f"   ✗ Failed: {e}")

    print(f"\n✅ Follow-up run complete: {len(due)} sent")
