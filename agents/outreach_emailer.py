"""
Outreach Emailer — sends partnership pitch emails via Gmail SMTP.
Uses GMAIL_USER and GMAIL_APP_PASSWORD from .env.

Setup:
1. Go to myaccount.google.com → Security → 2-Step Verification → App Passwords
2. Create an App Password for "Mail" + "Mac"
3. Add to .env:
   GMAIL_USER=your@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx  (16-char Google App Password)
"""

import smtplib
import os
import json
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

OUTREACH_DIR = Path(__file__).parent.parent / "outreach"
OUTBOX_FILE = OUTREACH_DIR / "outbox.json"
SENT_LOG_FILE = OUTREACH_DIR / "sent_log.json"

FROM_NAME = "Steven Samori"


def _load_json(path: Path) -> list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def _save_json(path: Path, data):
    OUTREACH_DIR.mkdir(exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _send_one(to_email: str, subject: str, body: str) -> bool:
    """Send a single email via Gmail SMTP SSL."""
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    if not gmail_user or not gmail_password:
        raise EnvironmentError(
            "GMAIL_USER and GMAIL_APP_PASSWORD not set in .env\n"
            "See agents/outreach_emailer.py for setup instructions."
        )

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


def send_all_emails(dry_run: bool = False, delay_seconds: int = 90, limit: int = None):
    """
    Send all draft emails in outbox that have a contact_email.

    Args:
        dry_run: If True, print emails but don't send
        delay_seconds: Wait between sends (default 90s — avoids Gmail spam triggers)
        limit: Max number of emails to send in this run (None = all)
    """
    outbox = _load_json(OUTBOX_FILE)
    sent_log = _load_json(SENT_LOG_FILE)

    to_send = [
        e for e in outbox
        if e.get("status") == "draft" and e.get("contact_email")
    ]
    no_email = [
        e for e in outbox
        if e.get("status") == "draft" and not e.get("contact_email")
    ]
    already_sent = [e for e in outbox if e.get("status") == "sent"]

    print(f"\n📧 EMAIL OUTBOX SUMMARY")
    print(f"   Ready to send:      {len(to_send)}")
    print(f"   No email address:   {len(no_email)}")
    print(f"   Already sent:       {len(already_sent)}")

    if no_email:
        print(f"\n⚠️  Targets missing email (will skip):")
        for e in no_email:
            print(f"   - {e['name']} | category: {e.get('category', '?')}")

    if not to_send:
        print("\nNothing to send. Draft pitches first: python main.py outreach draft")
        return

    if limit:
        to_send = to_send[:limit]
        print(f"\n   Limiting to first {limit} emails this run")

    if dry_run:
        print(f"\n🧪 DRY RUN — {len(to_send)} emails (not actually sending)\n")
        print("=" * 70)
        for e in to_send:
            print(f"\nTO: {e['contact_email']}")
            print(f"SUBJECT: {e['subject']}")
            print(f"\n{e['body']}")
            print("\n" + "=" * 70)
        return

    print(f"\n📤 Sending {len(to_send)} emails ({delay_seconds}s delay between each)...")
    print(f"   Estimated time: ~{len(to_send) * delay_seconds // 60} minutes\n")

    sent_count = 0
    failed_count = 0

    for i, entry in enumerate(to_send, 1):
        print(f"[{i}/{len(to_send)}] → {entry['name']} <{entry['contact_email']}>")
        print(f"  Subject: {entry['subject']}")

        try:
            _send_one(
                to_email=entry["contact_email"],
                subject=entry["subject"],
                body=entry["body"]
            )

            sent_at = datetime.utcnow().isoformat()

            # Update outbox
            for e in outbox:
                if e["target_key"] == entry["target_key"]:
                    e["status"] = "sent"
                    e["sent_at"] = sent_at

            # Append to sent log
            sent_log.append({**entry, "sent_at": sent_at})

            _save_json(OUTBOX_FILE, outbox)
            _save_json(SENT_LOG_FILE, sent_log)

            print(f"  ✓ Sent!\n")
            sent_count += 1

            if i < len(to_send):
                print(f"  ⏳ Waiting {delay_seconds}s...")
                time.sleep(delay_seconds)

        except Exception as e:
            print(f"  ✗ FAILED: {e}\n")
            for entry_item in outbox:
                if entry_item["target_key"] == entry["target_key"]:
                    entry_item["status"] = "failed"
                    entry_item["error"] = str(e)
            _save_json(OUTBOX_FILE, outbox)
            failed_count += 1

    print(f"\n✅ Done: {sent_count} sent, {failed_count} failed")


def mark_dm_sent(handle: str):
    """Mark a DM as sent in dm_queue.json after you've manually sent it."""
    dm_path = OUTREACH_DIR / "dm_queue.json"
    dm_queue = _load_json(dm_path)

    for d in dm_queue:
        if d.get("handle") == handle or d.get("target_key") == handle:
            d["status"] = "sent"
            d["sent_at"] = datetime.utcnow().isoformat()
            _save_json(dm_path, dm_queue)
            print(f"✓ Marked @{handle} DM as sent")
            return

    print(f"⚠ Handle @{handle} not found in DM queue")


def outreach_status():
    """Print a full dashboard of outreach progress."""
    outbox = _load_json(OUTBOX_FILE)
    dm_queue = _load_json(OUTREACH_DIR / "dm_queue.json")
    cache_path = OUTREACH_DIR / "research_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    total_targets = sum(
        len(json.loads((OUTREACH_DIR / "targets" / f).read_text()))
        for f in ["influencers.json", "brands.json", "delivery.json"]
        if (OUTREACH_DIR / "targets" / f).exists()
    )

    researched = len([v for v in cache.values() if "error" not in v])
    research_errors = len([v for v in cache.values() if "error" in v])

    email_draft = len([e for e in outbox if e["status"] == "draft"])
    email_sent = len([e for e in outbox if e["status"] == "sent"])
    email_failed = len([e for e in outbox if e["status"] == "failed"])
    email_no_addr = len([e for e in outbox if e["status"] == "draft" and not e.get("contact_email")])

    dm_ready = len([d for d in dm_queue if d["status"] == "ready"])
    dm_sent = len([d for d in dm_queue if d["status"] == "sent"])

    print(f"""
╔══════════════════════════════════════════════╗
║       SPIRIT LIBRARY OUTREACH DASHBOARD      ║
╚══════════════════════════════════════════════╝

📋 TARGETS
   Total defined:       {total_targets}
   Researched:          {researched}
   Research errors:     {research_errors}
   Not yet researched:  {total_targets - researched - research_errors}

📧 EMAILS
   Drafted:             {email_draft}
   Missing address:     {email_no_addr}
   Sent:                {email_sent}
   Failed:              {email_failed}

💬 DMs
   Ready to send:       {dm_ready}
   Sent (manual):       {dm_sent}

🚀 NEXT STEPS""")

    if researched < total_targets:
        print(f"   → python main.py outreach research")
    if email_draft > email_no_addr:
        print(f"   → python main.py outreach send-emails --dry-run  (preview)")
        print(f"   → python main.py outreach send-emails             (send)")
    if dm_ready > 0:
        print(f"   → python main.py outreach show-dms                (copy DM text)")
        print(f"   → python main.py outreach mark-sent @handle       (after DMing)")
    if email_draft == 0 and dm_ready == 0:
        print(f"   → python main.py outreach draft")

    print()
