"""
Scan BOTH outreach Gmail inboxes for replies and triage them.

Inboxes:
  - claudesonnet111@gmail.com   (Westchester / 4 Seasons / RPRJC pitch)
  - spiritlibraryapp@gmail.com  (Spirit Library bars/restaurants pitch)

Pipeline per unread message:
  1. Skip own outbound (digest loops, system mail).
  2. Regex pre-filter for hard opt-out signals (CAN-SPAM 10-day requirement).
  3. Claude Haiku classification: hot / lukewarm / cold / optout / auto-reply / not-a-reply / spam.
  4. Hot + lukewarm → state/hot_replies.json + leave UNREAD so Steven sees it.
  5. Optout → state/optout.txt + mark Seen.
  6. Everything else → mark Seen (silent triage).
  7. Send daily digest to claudesonnet111@gmail.com with:
     - CMO-drafted reply for each hot/lukewarm (ready to send from Gmail Drafts)
     - .ics calendar attachment per HOT lead ("Follow up with [Name]" event, next business day)
     - Immediate alert email for any HOT lead (doesn't wait for 8am digest)

Usage:
    python3 process_replies.py             # full pass on both inboxes + digest
    python3 process_replies.py --dry       # show classifications, change nothing
    python3 process_replies.py --inbox spirit   # only spirit library inbox
"""
import argparse, csv, imaplib, email, json, os, re, smtplib, sys, time, uuid
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path

import anthropic

from cmo_drafter import send_reply

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
try:
    from calendar_utils import create_proposed_event, create_event as create_confirmed_cal_event
    _CAL_UTILS = True
except ImportError:
    _CAL_UTILS = False

ENV_FILE = ROOT.parent / ".env"
OPTOUT = ROOT / "state" / "optout.txt"
PARTNERS = ROOT / "state" / "partners.txt"  # confirmed partners — Steven handles replies personally
HOT_REPLIES = ROOT / "state" / "hot_replies.json"
DRAFTED_KEYS = ROOT / "state" / "drafts_created.json"
REPLY_LOG = ROOT / "logs" / "replies.csv"
DIGEST_LOG = ROOT / "logs" / "reply_digest.log"

DIGEST_TO = "claudesonnet111@gmail.com"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

INBOXES = {
    "westchester": ("GMAIL_USER", "GMAIL_APP_PASSWORD"),
    "spirit":      ("SPIRIT_GMAIL_USER", "SPIRIT_GMAIL_APP_PASSWORD"),
}

# Inbox label → (profile name, shared state file). State file is shared with the legacy
# senders + the axon auto-sender daemon, so bounce marks land in the same dedup envelope
# every sender already reads.
INBOX_TO_PROFILE = {
    "westchester": ("claudesonnet111", "state/email_state.json"),
    "spirit": ("spiritlibraryapp", "state/spiritlibrary_email_state.json"),
}

BAD_DOMAINS_FILE = ROOT / "state" / "bad_domains.txt"
DOMAIN_BLACKLIST_THRESHOLD = 3

# NDR (non-delivery report) detection — matches the FROM address or subject of a bounce.
BOUNCE_FROM_INDICATORS = [
    r"mailer.?daemon@", r"postmaster@", r"mail.delivery.subsystem",
    r"noreply.*delivery", r"bounce.*@",
]
BOUNCE_SUBJECT_INDICATORS = [
    r"delivery status notification", r"undeliverable", r"undelivered mail",
    r"failure notice", r"mail delivery failed", r"returned mail",
    r"recipient address rejected", r"address not found",
]
# Body-level patterns that point at the original recipient inside an NDR.
NDR_RECIPIENT_PATTERNS = [
    re.compile(r"^Final-Recipient:\s*rfc822;\s*([^\s>]+)", re.M | re.I),
    re.compile(r"^Original-Recipient:\s*rfc822;\s*([^\s>]+)", re.M | re.I),
    re.compile(r"<([^@<>]+@[^@<>]+)>:\s*(?:host\s|.*does not exist|.*user unknown|.*not found)", re.I),
    re.compile(r"to <?([^@<>\s]+@[^@<>\s]+)>?\s+failed", re.I),
    re.compile(r"The following message to <?([^@<>\s]+@[^@<>\s]+)>? was undeliverable", re.I),
]

OPTOUT_PATTERNS = [
    r"\bunsubscribe\b", r"\bremove me\b", r"\btake me off\b",
    r"\bstop emailing\b", r"\bdo not email\b", r"\bopt.?out\b",
    r"^\s*stop\s*$", r"^\s*remove\s*$",
    r"^\s*no\.?\s*$", r"^\s*no\s+thanks?\.?\s*$", r"\bnot interested\b",
    r"\bplease remove\b", r"\bwrong (person|number|email)\b",
]


def load_env(key: str) -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE}")
    m = re.search(rf"^{key}\s*=\s*(.+)$", ENV_FILE.read_text(), re.M)
    if not m:
        sys.exit(f"{key} not in .env")
    return m.group(1).strip().strip('"').strip("'")


def decode(s) -> str:
    if not s:
        return ""
    try:
        out = []
        for txt, enc in decode_header(s):
            if isinstance(txt, bytes):
                out.append(txt.decode(enc or "utf-8", errors="ignore"))
            else:
                out.append(txt)
        return "".join(out)
    except Exception:
        return str(s)


def extract_body(msg) -> str:
    if msg.is_multipart():
        parts = []
        for p in msg.walk():
            if p.get_content_type() == "text/plain" and "attachment" not in str(p.get("Content-Disposition") or ""):
                try:
                    parts.append(p.get_payload(decode=True).decode(errors="ignore"))
                except Exception:
                    pass
        raw = "\n".join(parts)
    else:
        try:
            raw = msg.get_payload(decode=True).decode(errors="ignore")
        except Exception:
            raw = str(msg.get_payload())
    return strip_quoted(raw)


QUOTE_MARKERS = [
    re.compile(r"^On .+ wrote:\s*$", re.M),
    re.compile(r"^From: .+$", re.M),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.M | re.I),
    re.compile(r"^_{5,}", re.M),
]


def strip_quoted(text: str) -> str:
    """Drop the quoted portion of a reply so original-email footers (with
    'unsubscribe' / physical address) don't poison classification."""
    if not text:
        return ""
    earliest = len(text)
    for pat in QUOTE_MARKERS:
        m = pat.search(text)
        if m and m.start() < earliest:
            earliest = m.start()
    head = text[:earliest]
    # Also drop lines that start with '>' (typical reply quoting)
    kept = [ln for ln in head.splitlines() if not ln.lstrip().startswith(">")]
    return "\n".join(kept).strip()


def regex_optout(text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low, re.M) for p in OPTOUT_PATTERNS)


CLASSIFY_SYSTEM = (
    "You triage replies to cold outreach emails. Two campaigns are running:\n"
    "1. SPIRIT LIBRARY — pitching the Spirit Library cocktail recipe app to bars and restaurants.\n"
    "2. WESTCHESTER — pitching AI-built ops tools to Westchester/NJ/CT local SMBs (cleaners, landscapers, auto shops).\n\n"
    "Classify each message into exactly one category. Be precise — these get handled differently:\n"
    "  confirmed   — they have agreed to a SPECIFIC date and time for a Zoom call.\n"
    "                Examples: 'Yes, Thursday at 2pm works', 'Tuesday 3pm is good for me',\n"
    "                'I can do next Friday at noon', 'Send me a calendar invite for Wednesday at 10'.\n"
    "                Pattern: a specific date+time is stated AND they are agreeing to it.\n"
    "                This is DIFFERENT from hot — hot = interested but no time locked. confirmed = time locked.\n"
    "  hot         — clear interest, asks for a meeting, demo, info, or 'send me more'. Has momentum.\n"
    "                Examples (these are the gold-standard 'interested' signals):\n"
    "                  • 'How do you imagine this working with us as featured content?'\n"
    "                  • 'Send invite to taylor@... any time next week works'\n"
    "                  • 'Would love to get information if you can send us a mock and pricing'\n"
    "                  • 'We may be interested. Our manager will be in touch.'\n"
    "                  • 'ARE WE MEETING IN PERSON?'\n"
    "                  • 'Ok show me'\n"
    "                  • 'Cannot pay to play but open to collaborating — let me know what's possible'\n"
    "                Pattern: they're ASKING something specific that requires us to act. Door is open.\n"
    "  lukewarm    — soft interest, asks discovery questions, mild curiosity, says 'maybe' or 'tell me more'.\n"
    "                Examples: 'Can you send a website / linkedin?' (verification before engaging),\n"
    "                'thanks for the info!' (polite acknowledgment, may continue), 'will look into it'.\n"
    "  decline     — soft NO. 'not now', 'not a fit', 'not interested right now', 'we already have one',\n"
    "                'thanks but no', 'maybe later'. Polite pass — they'd reply if circumstances change.\n"
    "  optout      — hard STOP. 'unsubscribe', 'remove me', 'stop emailing', 'do not contact', curt 'no.',\n"
    "                'wrong person'. CAN-SPAM territory — must suppress immediately, no further outreach.\n"
    "  auto-reply  — vacation responder, bounce, mailer-daemon, delivery status, OOO.\n"
    "  not-a-reply — newsletter, transactional, system mail, unrelated cold inbound to us.\n"
    "  spam        — spammy / irrelevant / phishing.\n\n"
    "Key distinction: confirmed = specific time locked in. hot = interested, no time locked yet.\n"
    "lukewarm = open door (just careful). decline = closed politely. optout = closed firmly (legal).\n\n"
    "Reply with one word: confirmed, hot, lukewarm, decline, optout, auto-reply, not-a-reply, or spam."
)


def classify_with_claude(client, subject: str, from_addr: str, body: str) -> str:
    body = body[:2000]
    prompt = f"From: {from_addr}\nSubject: {subject}\n\n{body}"
    try:
        r = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=10,
            system=CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = r.content[0].text.strip().lower()
        # Order matters: check longest/most specific first to avoid 'not' matching 'not-a-reply' before 'not interested'
        for cat in ("not-a-reply", "auto-reply", "confirmed", "lukewarm", "decline", "optout", "spam", "hot"):
            if cat in text:
                return cat
        return "not-a-reply"
    except Exception as e:
        err = str(e)
        if "credit balance" in err or "rate_limit" in err.lower() or "overloaded" in err.lower():
            # API is down/rate-limited — return sentinel so message stays UNREAD for retry
            print(f"   ⚠️  Claude API unavailable: {err[:120]} — leaving UNREAD for retry")
            return "api-error"
        print(f"   ⚠️  Claude classify error: {e} — defaulting to not-a-reply")
        return "not-a-reply"


def is_partner(address: str) -> bool:
    if not PARTNERS.exists():
        return False
    addrs = {line.strip().lower() for line in PARTNERS.read_text().splitlines() if line.strip()}
    return address.lower().strip() in addrs


def add_partner(address: str, name: str = "") -> None:
    PARTNERS.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if PARTNERS.exists():
        existing = {line.split("#")[0].strip().lower() for line in PARTNERS.read_text().splitlines() if line.strip()}
    addr = address.lower().strip()
    if addr not in existing:
        with open(PARTNERS, "a") as f:
            label = f"  # {name}" if name else ""
            f.write(addr + label + "\n")


def append_optout(address: str) -> bool:
    OPTOUT.parent.mkdir(parents=True, exist_ok=True)
    current = set()
    if OPTOUT.exists():
        current = {line.strip().lower() for line in OPTOUT.read_text().splitlines() if line.strip()}
    addr = address.lower().strip()
    if not addr or addr in current:
        return False
    with open(OPTOUT, "a") as f:
        f.write(addr + "\n")
    return True


def is_bounce_message(from_addr: str, subj: str) -> bool:
    fa = (from_addr or "").lower()
    sb = (subj or "").lower()
    for pat in BOUNCE_FROM_INDICATORS:
        if re.search(pat, fa):
            return True
    for pat in BOUNCE_SUBJECT_INDICATORS:
        if re.search(pat, sb):
            return True
    return False


def extract_bounce_recipient(body: str) -> str | None:
    if not body:
        return None
    for rx in NDR_RECIPIENT_PATTERNS:
        m = rx.search(body)
        if m:
            return m.group(1).strip().lower()
    return None


def record_ndr_bounce(inbox_label: str, bounced_email: str) -> tuple[bool, bool]:
    """Mark a recipient as bounced in the sender profile's state.

    Returns (marked_new, domain_blacklisted).
    `marked_new` is True if this is the first time we've recorded a bounce for this email.
    `domain_blacklisted` is True if this bounce pushed the domain over threshold and we added it to bad_domains.txt.
    """
    entry = INBOX_TO_PROFILE.get(inbox_label)
    if not entry:
        return (False, False)
    _profile_name, state_rel = entry
    state_path = ROOT / state_rel
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {}
    else:
        state = {}
    state.setdefault("bounced", {})
    state.setdefault("domain_bounces", {})
    em = bounced_email.lower().strip()
    domain = em.rsplit("@", 1)[-1] if "@" in em else ""
    marked_new = em not in state["bounced"]
    state["bounced"][em] = datetime.now(timezone.utc).isoformat()
    if domain:
        state["domain_bounces"][domain] = state["domain_bounces"].get(domain, 0) + 1
    state_path.write_text(json.dumps(state, indent=2))

    blacklisted = False
    if domain and state["domain_bounces"][domain] >= DOMAIN_BLACKLIST_THRESHOLD:
        BAD_DOMAINS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = set()
        if BAD_DOMAINS_FILE.exists():
            existing = {l.strip().lower() for l in BAD_DOMAINS_FILE.read_text().splitlines() if l.strip()}
        if domain not in existing:
            with open(BAD_DOMAINS_FILE, "a") as f:
                f.write(f"{domain}\n")
            blacklisted = True
    return (marked_new, blacklisted)


def extract_confirmed_time(client, body: str, subject: str, proposed_times_hint: str = "") -> "datetime | None":
    """Ask Haiku to parse the confirmed meeting datetime from the email.
    proposed_times_hint: the times Steven proposed in the prior draft (if known),
    so Haiku can resolve 'yes that works' against a real set of options.
    Returns a UTC-aware datetime, or None if no specific time found."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    hint_block = f"\nSteven previously proposed these times:\n{proposed_times_hint}\n" if proposed_times_hint else ""
    prompt = (
        f"Today is {today} (America/New_York).{hint_block}\n"
        f"Subject: {subject}\n\nBody:\n{body[:1500]}\n\n"
        "Extract the confirmed meeting date and time. "
        "Reply with ONLY an ISO 8601 datetime in America/New_York local time (e.g. 2026-05-20T14:00:00), "
        "or reply with 'none' if no specific date+time can be determined."
    )
    try:
        r = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=30,
            system="Extract the confirmed meeting datetime from email text. Reply only with an ISO datetime (no timezone suffix) or 'none'.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = r.content[0].text.strip().split()[0]
        if not text or text.lower() == "none":
            return None
        dt = datetime.fromisoformat(text.rstrip("Z"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=et)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _book_confirmed_meeting(entry: dict, confirmed_dt: "datetime | None", client) -> "str | None":
    """Create a CONFIRMED calendar event and send the lead a real Google Calendar invite.
    Returns the calendar event link, or None on failure."""
    if not _CAL_UTILS:
        return None
    name = entry.get("from_name") or entry["from"].split("@")[0].replace(".", " ").title()
    campaign = {"westchester": "AI Consulting", "spirit": "Spirit Library"}.get(entry.get("inbox", ""), "Outreach")

    if confirmed_dt is None:
        # Time couldn't be parsed — fall back to HOT-style tentative proposal
        print(f"      ⚠️  Could not parse confirmed time — skipping calendar invite")
        return None

    summary = f"Zoom — {name} [{campaign}]"
    desc = (
        f"CONFIRMED Zoom call.\n\n"
        f"Lead: {entry['from']}\n"
        f"Subject: {entry['subject']}\n"
        f"Campaign: {entry.get('inbox', '?')}"
    )
    try:
        link = create_confirmed_cal_event(summary, confirmed_dt, entry["from"], desc)
        from calendar_utils import _to_et
        et_dt = _to_et(confirmed_dt)
        print(f"      📅 CONFIRMED invite sent: {name} — {et_dt.strftime('%b %-d at %-I:%M%p ET')}")
        add_partner(entry["from"], name)  # auto-promote to partner — their future replies go to Steven
        return link
    except Exception as e:
        print(f"      ⚠️  Calendar invite failed: {e}")
        return None


def next_business_day(dt: datetime) -> datetime:
    """Return the next business day at 9am America/New_York as a UTC-aware datetime."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    d = dt.astimezone(et).date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, 9, 0, 0, tzinfo=et).astimezone(timezone.utc)


def make_ics(name: str, email_addr: str, subject: str, note: str = "") -> str:
    """Generate a .ics calendar event: 'Follow up with [Name]' next business day at 9am."""
    now = datetime.now(timezone.utc)
    start = next_business_day(now)
    end = start + timedelta(minutes=30)
    fmt = "%Y%m%dT%H%M%SZ"
    uid = str(uuid.uuid4())
    summary = f"Follow up: {name or email_addr}"
    description = f"Hot lead from outreach.\\nEmail: {email_addr}\\nSubject: {subject}"
    if note:
        description += f"\\nNote: {note}"
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Smore Labs PM Agent//EN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{now.strftime(fmt)}\r\n"
        f"DTSTART:{start.strftime(fmt)}\r\n"
        f"DTEND:{end.strftime(fmt)}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{description}\r\n"
        "STATUS:CONFIRMED\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT15M\r\n"
        "ACTION:DISPLAY\r\n"
        f"DESCRIPTION:Reminder: {summary}\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def _book_proposed_slots(entry: dict, slots: list) -> None:
    """Two calendar events per HOT lead:
    1. TENTATIVE at each proposed Zoom time (so you see what times you offered).
    2. A follow-up reminder 10 days out — only fires if they go quiet.

    Falls back to calendar_queue.json if Python OAuth isn't set up."""
    if not _CAL_UTILS:
        return
    name = entry.get("from_name") or entry["from"].split("@")[0].replace(".", " ").title()
    campaign = {"westchester": "AI Consulting", "spirit": "Spirit Library"}.get(entry.get("inbox", ""), "Outreach")

    # Tentative events at each proposed Zoom time
    for slot in slots:
        summary = f"Zoom — {name} [{campaign}] (proposed)"
        desc = (
            f"PROPOSED — not yet confirmed\n\n"
            f"Lead: {entry['from']}\n"
            f"Subject: {entry['subject']}\n"
            f"Campaign: {entry.get('inbox', '?')}\n\n"
            f"Update to CONFIRMED when they accept. Delete the other time slots."
        )
        result = create_proposed_event(summary, slot["start"], entry["from"], desc)
        if result.get("queued"):
            print(f"      \U0001f4c5 Queued Zoom event: {slot['label']}")
        else:
            print(f"      \U0001f4c5 Tentative Zoom event: {slot['label']}")

    # One follow-up reminder 10 days out (in case they go quiet — 1.5-week rule)
    followup_dt = datetime.now(timezone.utc) + timedelta(days=10)
    followup_dt = followup_dt.replace(hour=9, minute=0, second=0, microsecond=0)
    while followup_dt.weekday() >= 5:
        followup_dt += timedelta(days=1)
    fu_summary = f"Check in: {name} [{campaign}] — if no response"
    fu_desc = (
        f"Auto-reminder: 10 days since draft was sent.\n"
        f"Lead: {entry['from']}\nSubject: {entry['subject']}\n\n"
        f"If they haven't replied, send a brief follow-up."
    )
    result = create_proposed_event(fu_summary, followup_dt, entry["from"], fu_desc)
    label = followup_dt.strftime("%a %b %-d")
    if result.get("queued"):
        print(f"      \U0001f4c5 Queued follow-up reminder: {label}")
    else:
        print(f"      \U0001f4c5 Follow-up reminder set: {label}")


def send_hot_alert(entry: dict, draft_body: str) -> None:
    """Fire an immediate email + .ics for a HOT lead — doesn't wait for the 8am digest."""
    try:
        user = load_env("GMAIL_USER")
        pw = load_env("GMAIL_APP_PASSWORD")
        name = entry.get("from_name") or entry["from"]
        preview = (entry.get("body_preview") or "")[:300]

        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"🔥 HOT LEAD: {name} — reply now"
        msg["From"] = f"PM Agent <{user}>"
        msg["To"] = DIGEST_TO

        body_html = (
            f"<p><b>🔥 Hot lead from outreach — respond today.</b></p>"
            f"<p><b>From:</b> {name} &lt;{entry['from']}&gt;<br>"
            f"<b>Subject:</b> {entry['subject']}<br>"
            f"<b>Inbox:</b> {entry['inbox']}</p>"
            f"<blockquote style='border-left:3px solid #c9a84c;padding:8px 12px;color:#555'>{preview}</blockquote>"
            f"<p><b>CMO Draft (in Gmail Drafts, ready to send):</b></p>"
            f"<pre style='background:#f5f5f5;padding:12px;border-radius:4px'>{draft_body}</pre>"
            f"<p style='color:#888;font-size:12px'>Calendar event attached — tap to add follow-up reminder.</p>"
        )
        msg.attach(MIMEText(body_html, "html"))

        ics = make_ics(name, entry["from"], entry["subject"])
        cal_part = MIMEBase("text", "calendar", method="PUBLISH")
        cal_part.set_payload(ics)
        safe_name = re.sub(r"[^\w]", "_", name)[:30]
        cal_part.add_header("Content-Disposition", "attachment", filename=f"followup_{safe_name}.ics")
        msg.attach(cal_part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pw)
            s.sendmail(user, [DIGEST_TO], msg.as_string())
        print(f"   🚨 Immediate hot-lead alert sent for {entry['from']}")
    except Exception as e:
        print(f"   ⚠️  Hot alert failed: {e}")


def send_confirmed_alert(entry: dict, draft_body: str) -> None:
    """Fire an immediate alert when a lead has confirmed a specific meeting time."""
    try:
        user = load_env("GMAIL_USER")
        pw = load_env("GMAIL_APP_PASSWORD")
        name = entry.get("from_name") or entry["from"]
        preview = (entry.get("body_preview") or "")[:300]
        cal_link = entry.get("_calendar_link", "")
        invite_status = f'<a href="{cal_link}">View calendar event</a>' if cal_link else "⚠️ Time could not be parsed — confirm-reply proposes times instead."

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🗓️ CONFIRMED MEETING: {name}"
        msg["From"] = f"PM Agent <{user}>"
        msg["To"] = DIGEST_TO

        body_html = (
            f"<p><b>🗓️ Meeting confirmed — calendar invite sent.</b></p>"
            f"<p><b>From:</b> {name} &lt;{entry['from']}&gt;<br>"
            f"<b>Subject:</b> {entry['subject']}<br>"
            f"<b>Inbox:</b> {entry['inbox']}<br>"
            f"<b>Invite:</b> {invite_status}</p>"
            f"<blockquote style='border-left:3px solid #2563eb;padding:8px 12px;color:#555'>{preview}</blockquote>"
            f"<p><b>Confirm-reply draft (in Gmail Drafts):</b></p>"
            f"<pre style='background:#f5f5f5;padding:12px;border-radius:4px'>{draft_body}</pre>"
        )
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pw)
            s.sendmail(user, [DIGEST_TO], msg.as_string())
        print(f"   🗓️  Confirmed-meeting alert sent for {entry['from']}")
    except Exception as e:
        print(f"   ⚠️  Confirmed alert failed: {e}")


def append_hot(entry: dict) -> None:
    HOT_REPLIES.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(HOT_REPLIES.read_text()) if HOT_REPLIES.exists() else []
    data.append(entry)
    HOT_REPLIES.write_text(json.dumps(data, indent=2))


def drafted_key(entry: dict) -> str:
    """Per-message idempotency key. Uses RFC 5322 Message-ID when available
    (each new message in a thread has a unique one — so 5 back-and-forth
    replies in the same thread = 5 distinct drafts). Falls back to
    inbox|from|subject if Message-ID missing (rare)."""
    mid = (entry.get("message_id") or "").strip()
    if mid:
        return f"{entry['inbox']}|{mid}"
    return f"{entry['inbox']}|{entry['from'].lower()}|{entry['subject'][:50].lower()}"


def already_drafted(entry: dict) -> bool:
    if not DRAFTED_KEYS.exists():
        return False
    try:
        keys = set(json.loads(DRAFTED_KEYS.read_text()))
    except Exception:
        return False
    return drafted_key(entry) in keys


def mark_drafted(entry: dict) -> None:
    DRAFTED_KEYS.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    if DRAFTED_KEYS.exists():
        try:
            keys = json.loads(DRAFTED_KEYS.read_text())
        except Exception:
            keys = []
    keys.append(drafted_key(entry))
    DRAFTED_KEYS.write_text(json.dumps(keys, indent=2))


def log_reply(inbox: str, addr: str, subj: str, klass: str) -> None:
    REPLY_LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not REPLY_LOG.exists()
    with open(REPLY_LOG, "a") as f:
        if new:
            f.write("timestamp_utc,inbox,email,subject,classification\n")
        subj_escaped = subj.replace('"', "'").replace("\n", " ")
        f.write(f'{datetime.now(timezone.utc).isoformat()},{inbox},{addr},"{subj_escaped}",{klass}\n')


SELF_ADDRS = {"stevensamori@gmail.com"}


def is_self_mail(from_addr: str) -> bool:
    own = {load_env(k).lower() for k in ("GMAIL_USER", "SPIRIT_GMAIL_USER")} | SELF_ADDRS
    return from_addr.lower() in own


def scan_inbox(inbox_label: str, user: str, pw: str, claude_client, dry: bool, include_seen: bool = False) -> dict:
    print(f"\n📥 [{inbox_label}] connecting as {user}")
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(user, pw)
    M.select("INBOX")

    if include_seen:
        # Recovery: scan last 7 days only (not 30) to avoid rate-limit blowout
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%d-%b-%Y")
        typ, data = M.search(None, f'(SINCE "{since}")')
        scope = f"all (since {since}, recovery mode)"
    else:
        typ, data = M.search(None, "UNSEEN")
        scope = "unread"
    ids = data[0].split()
    print(f"   {len(ids)} {scope}")

    counts = {"confirmed": 0, "hot": 0, "lukewarm": 0, "decline": 0, "optout": 0, "auto-reply": 0, "not-a-reply": 0, "spam": 0, "self": 0, "api-error": 0}
    new_hot = []
    partner_replies = []

    for num in ids:
        try:
            # BODY.PEEK[] does NOT mark message as seen (RFC822 would)
            typ, msg_data = M.fetch(num, "(BODY.PEEK[])")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
        except Exception as e:
            print(f"   ⚠️  fetch fail: {e}")
            continue

        from_name, from_addr = parseaddr(msg.get("From", ""))
        subj = decode(msg.get("Subject", ""))
        body = extract_body(msg)
        corpus = f"{subj}\n{body}"

        if not from_addr:
            continue
        if is_self_mail(from_addr):
            counts["self"] += 1
            if not dry:
                M.store(num, "+FLAGS", "\\Seen")
            continue

        # Partner fast path — confirmed partners bypass auto-reply, go straight to PM alert
        if is_partner(from_addr):
            counts["partner"] = counts.get("partner", 0) + 1
            msg_id = msg.get("Message-ID", "").strip()
            partner_replies.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "inbox": inbox_label,
                "from": from_addr,
                "from_name": from_name,
                "subject": subj,
                "body_preview": body[:800],
                "message_id": msg_id,
            })
            if dry:
                print(f"   [DRY] PARTNER: {from_addr} — {subj[:60]}")
            else:
                print(f"   🤝 PARTNER reply: {from_addr} — {subj[:60]}")
            continue

        # Hard opt-out fast path (CAN-SPAM)
        if regex_optout(corpus):
            klass = "optout"
        else:
            if include_seen:
                time.sleep(1.5)  # throttle recovery scans — prevents rate-limit blowout on large inboxes
            klass = classify_with_claude(claude_client, subj, from_addr, body)

        counts[klass] = counts.get(klass, 0) + 1
        log_reply(inbox_label, from_addr, subj, klass) if not dry else None

        if klass == "optout":
            # Hard stop — suppress, NO draft, mark seen. They explicitly told us to stop.
            if dry:
                print(f"   [DRY] OPT-OUT: {from_addr} — {subj[:60]}")
            else:
                if append_optout(from_addr):
                    print(f"   🚫 OPT-OUT: {from_addr}")
                M.store(num, "+FLAGS", "\\Seen")
        elif klass == "confirmed":
            # They locked in a specific time — create a real calendar invite + draft confirm reply
            msg_id = msg.get("Message-ID", "").strip()
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "inbox": inbox_label,
                "from": from_addr,
                "from_name": from_name,
                "subject": subj,
                "classification": "confirmed",
                "body_preview": body[:600],
                "message_id": msg_id,
                "_full_body": body,
            }
            new_hot.append(entry)
            if dry:
                print(f"   [DRY] CONFIRMED: {from_addr} — {subj[:60]}")
            else:
                persist = {k: v for k, v in entry.items() if k != "_full_body"}
                append_hot(persist)
                if append_optout(from_addr):
                    print(f"   🗓️  CONFIRMED + 🛑 auto-suppress: {from_addr} — {subj[:60]}")
                else:
                    print(f"   🗓️  CONFIRMED: {from_addr} — {subj[:60]}")
                # Extract the specific time and send a real calendar invite
                confirmed_dt = extract_confirmed_time(claude_client, body, subj)
                cal_link = _book_confirmed_meeting(entry, confirmed_dt, claude_client)
                entry["_calendar_link"] = cal_link or ""
                # If time couldn't be extracted, downgrade to hot so drafter proposes times instead
                if not cal_link:
                    entry["classification"] = "hot"
                    entry["_downgraded_from"] = "confirmed"
                # Leave UNREAD so Steven sees it
        elif klass in ("hot", "lukewarm", "decline"):
            # All three need: suppress from cold pipeline + show Steven + draft a reply
            # (CMO drafter handles tone differently per class — decline = short polite check-back)
            msg_id = msg.get("Message-ID", "").strip()
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "inbox": inbox_label,
                "from": from_addr,
                "from_name": from_name,
                "subject": subj,
                "classification": klass,
                "body_preview": body[:600],
                "message_id": msg_id,  # used as idempotency key (per-message, not per-thread)
                "_full_body": body,  # used by CMO drafter, stripped before persist
            }
            new_hot.append(entry)
            if dry:
                print(f"   [DRY] {klass.upper()}: {from_addr} — {subj[:60]}")
            else:
                persist = {k: v for k, v in entry.items() if k != "_full_body"}
                append_hot(persist)
                # Auto-suppress all three classes — once they've engaged (positively or politely passed),
                # the cold campaign stops pitching. Conversation moves to manual Gmail.
                emoji = {"hot": "🔥", "lukewarm": "🟡", "decline": "🚪"}[klass]
                if append_optout(from_addr):
                    print(f"   {emoji} {klass.upper()} + 🛑 auto-suppress: {from_addr} — {subj[:60]}")
                else:
                    print(f"   {emoji} {klass.upper()}: {from_addr} — {subj[:60]}")
                # Leave UNREAD so Steven sees it in his inbox
        elif klass == "api-error":
            # API down — leave UNREAD so next scan retries this message
            pass
        else:
            # auto-reply / not-a-reply / spam → mark seen, silent.
            # NDR sub-branch: if this is a delivery failure, record the bounce so the
            # engine's domain blacklist + per-recipient bounce log get updated, and the
            # daily send-cap isn't penalized by ghost recipients.
            if klass == "auto-reply" and is_bounce_message(from_addr, subj):
                bounced_to = extract_bounce_recipient(body)
                if bounced_to:
                    marked_new, blacklisted = record_ndr_bounce(inbox_label, bounced_to)
                    if dry:
                        print(f"   [DRY] BOUNCE: {bounced_to}"
                              + (" (NEW)" if marked_new else "")
                              + (f" → BLACKLISTED {bounced_to.rsplit('@',1)[-1]}" if blacklisted else ""))
                    else:
                        print(f"   ↩ BOUNCE: {bounced_to}"
                              + (" (new)" if marked_new else "")
                              + (f" → 🚫 blacklisted {bounced_to.rsplit('@',1)[-1]}" if blacklisted else ""))
            if not dry:
                M.store(num, "+FLAGS", "\\Seen")

    # CMO send pass — generate reply with Claude and send immediately via SMTP
    # Steven is only alerted when a confirmed meeting lands on the calendar.
    sent = []
    if not dry and new_hot:
        print(f"   🤖 CMO send pass — {len(new_hot)} candidates")
        for entry in new_hot:
            if already_drafted(entry):
                print(f"      ⏩ already sent to {entry['from']} — skipping")
                sent.append({**entry, "_send_status": "skipped (already sent)"})
                continue
            try:
                M.select("INBOX")
                result = send_reply(claude_client, entry, entry.get("_full_body", ""), M, user, pw)
                if result["ok"]:
                    mark_drafted(entry)
                    klass = entry.get("classification", "")
                    print(f"      ✉️  sent reply to {entry['from']} [{klass}]")
                    sent.append({**entry, "_send_status": "sent", "_sent_body": result["sent_body"]})
                    # Only alert Steven when a meeting is confirmed on the calendar
                    if klass == "confirmed":
                        send_confirmed_alert(entry, result["sent_body"])
                else:
                    print(f"      ✗ send failed for {entry['from']}: {result.get('error')}")
                    sent.append({**entry, "_send_status": f"FAILED: {result.get('error')}"})
            except Exception as e:
                print(f"      ✗ send exception: {e}")
                sent.append({**entry, "_send_status": f"EXCEPTION: {e}"})

    M.close()
    M.logout()
    print(f"   ✅ [{inbox_label}] {counts}")
    return {"counts": counts, "new_hot": new_hot, "sent": sent, "partner_replies": partner_replies}


def check_anthropic_api(api_key: str) -> str:
    """Ping Anthropic API — returns 'OK' or a short error label."""
    try:
        c = anthropic.Anthropic(api_key=api_key)
        c.messages.create(model=HAIKU_MODEL, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
        return "OK"
    except Exception as e:
        err = str(e)
        if "credit balance" in err:
            return "LOW BALANCE"
        if "rate_limit" in err.lower():
            return "RATE LIMITED"
        return f"ERROR: {err[:60]}"


def send_digest(results: dict, total_hot: list, all_sent: list, partner_replies: list = None, api_status: str = "UNKNOWN") -> None:
    """Background ops log. Always sent when there are partner replies.
    Steven gets a separate confirmed-meeting alert when a calendar invite is booked."""
    if partner_replies is None:
        partner_replies = []
    user = load_env("GMAIL_USER")
    pw = load_env("GMAIL_APP_PASSWORD")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    sent_ok = [d for d in all_sent if d.get("_send_status") == "sent"]
    failed = [d for d in all_sent if d.get("_send_status", "").startswith(("FAILED", "EXCEPTION"))]
    skipped = [d for d in all_sent if d.get("_send_status", "").startswith("skipped")]

    style = (
        "body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#1a1a1a;max-width:680px;margin:0 auto;padding:20px}"
        "h2{margin-top:0}h3{margin-top:32px;border-bottom:2px solid #c9a84c;padding-bottom:6px}"
        ".lead{background:#fafafa;border-left:4px solid #c9a84c;padding:12px 16px;margin:12px 0;border-radius:4px}"
        ".lead .who{font-weight:600;color:#000}.lead .meta{color:#666;font-size:12px;margin-bottom:8px}"
        ".lead .reply{color:#333;font-size:13px;background:#fff;padding:10px;border:1px solid #eee;border-radius:4px;white-space:pre-wrap;font-family:'SF Mono',Menlo,monospace}"
        ".lead .preview{color:#555;font-style:italic;font-size:12px;margin:6px 0}"
        ".badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;text-transform:uppercase}"
        ".hot{background:#fdecec;color:#b00020}.lukewarm{background:#fff4e0;color:#a05a00}"
        ".decline{background:#eef2f5;color:#5a6470}"
        ".cta{background:#fff8e6;border:1px solid #c9a84c;border-radius:6px;padding:14px 16px;margin:20px 0}"
        ".stats{color:#666;font-size:12px}.stats b{color:#000}"
        ".todo{background:#f0f7ff;border-left:4px solid #2563eb;padding:14px 16px;border-radius:4px;margin:20px 0}"
        ".todo ol{margin:8px 0 0;padding-left:20px}"
        "hr{border:none;border-top:1px solid #eee;margin:24px 0}"
        ".footer{color:#999;font-size:11px}"
    )

    lines = [
        f"<style>{style}</style>",
        f"<h2>📊 Outreach ops log · {today}</h2>",
        f'<p class="stats">Fully automated. Replies sent directly. You\'ll get a separate alert only when a meeting is confirmed on the calendar.</p>',
    ]

    # ─── Partner replies (always top, Steven handles these) ──────
    if partner_replies:
        lines.append(f"<h3>🤝 Partner replies — handle these yourself ({len(partner_replies)})</h3>")
        for p in partner_replies:
            preview = (p.get("body_preview") or "").replace("\n", " ")
            lines.append('<div class="lead">')
            lines.append(f'<div class="who">{p.get("from_name") or ""} &lt;{p["from"]}&gt;</div>')
            lines.append(f'<div class="meta">📥 {p["inbox"]} inbox · <i>{p["subject"]}</i></div>')
            lines.append(f'<div class="preview">{preview[:500]}</div>')
            lines.append('</div>')

    # ─── Sent replies ────────────────────────────────────────────
    if sent_ok:
        lines.append(f"<h3>✉️ Replies sent ({len(sent_ok)})</h3><ul>")
        for d in sent_ok:
            klass = d.get("classification", "")
            lines.append(f'<li><span class="badge {klass}">{klass}</span> &nbsp; {d.get("from_name") or d["from"]} — <i>{d["subject"][:60]}</i></li>')
        lines.append("</ul>")

    # ─── Failures (need attention) ───────────────────────────────
    if failed:
        lines.append(f"<h3>⚠️ Send failures ({len(failed)}) — needs manual reply</h3><ul>")
        for d in failed:
            lines.append(f"<li>{d['inbox']} · {d['from']} — <code>{d['_send_status']}</code></li>")
        lines.append("</ul>")

    # ─── Stats ──────────────────────────────────────────────────
    lines.append("<h3>📊 Triage stats</h3>")
    for inbox, r in results.items():
        c = r["counts"]
        api_err_note = f' · <b style="color:#b00020">{c.get("api-error",0)} retrying (API was down)</b>' if c.get("api-error", 0) else ""
        lines.append(
            f'<p class="stats"><b>{inbox}</b>: '
            f'<b>{c.get("confirmed",0)}</b> confirmed · <b>{c.get("hot",0)}</b> hot · <b>{c.get("lukewarm",0)}</b> lukewarm · '
            f'{c.get("decline",0)} decline · {c.get("optout",0)} optout · {c.get("auto-reply",0)} auto-reply · '
            f'{c.get("not-a-reply",0)} not-a-reply{api_err_note}</p>'
        )
    api_color = "#007700" if api_status == "OK" else "#b00020"
    lines.append(f'<p class="stats">🤖 Anthropic API: <b style="color:{api_color}">{api_status}</b></p>')

    # ─── Footer ─────────────────────────────────────────────────
    lines.append('<hr><p class="footer">'
                 '⏰ <code>com.smorelabs.outreach-replies</code> · 10:00 AM + 8:00 PM ET · fully autonomous<br>'
                 '🛑 Engaged senders auto-suppressed from cold pipeline · 🔁 API-error messages retried next window'
                 '</p>')
    body_html = "\n".join(lines)

    # Only send digest when there's something worth knowing
    if not sent_ok and not failed and not partner_replies:
        print(f"\n📭 No activity — digest suppressed")
        return

    msg = MIMEMultipart("alternative")
    partner_note = f"{len(partner_replies)} partner repl{'y' if len(partner_replies)==1 else 'ies'}" if partner_replies else ""
    activity = f"{len(sent_ok)} sent" if sent_ok else ""
    errors = f"{len(failed)} failed" if failed else ""
    subj_parts = " · ".join(p for p in [partner_note, activity, errors] if p) or "all quiet"
    msg["Subject"] = f"📊 Outreach ops · {today} · {subj_parts}"
    msg["From"] = f"PM Agent <{user}>"
    msg["To"] = DIGEST_TO
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.sendmail(user, [DIGEST_TO], msg.as_string())
    print(f"\n📨 Ops log sent to {DIGEST_TO} — {subj_parts}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="Classify but change nothing")
    ap.add_argument("--inbox", choices=list(INBOXES.keys()) + ["all"], default="all")
    ap.add_argument("--no-digest", action="store_true")
    ap.add_argument("--include-seen", action="store_true", help="Recovery mode: scan last 30 days regardless of seen flag")
    args = ap.parse_args()

    api_key = load_env("ANTHROPIC_API_KEY")
    claude = anthropic.Anthropic(api_key=api_key)

    targets = INBOXES if args.inbox == "all" else {args.inbox: INBOXES[args.inbox]}
    results = {}
    total_hot = []
    all_sent = []
    all_partner_replies = []

    for label, (uk, pk) in targets.items():
        try:
            user = load_env(uk)
            pw = load_env(pk)
            r = scan_inbox(label, user, pw, claude, args.dry, args.include_seen)
            results[label] = r
            total_hot.extend(r["new_hot"])
            all_sent.extend(r.get("sent", []))
            all_partner_replies.extend(r.get("partner_replies", []))
        except Exception as e:
            print(f"❌ [{label}] failed: {e}")
            results[label] = {"counts": {"error": 1}, "new_hot": [], "sent": [], "partner_replies": []}

    if not args.dry and not args.no_digest:
        try:
            api_status = check_anthropic_api(api_key)
            send_digest(results, total_hot, all_sent, all_partner_replies, api_status=api_status)
        except Exception as e:
            print(f"⚠️  Digest send failed: {e}")

    DIGEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DIGEST_LOG, "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {json.dumps({k: v['counts'] for k, v in results.items()})} hot={len(total_hot)}\n")


if __name__ == "__main__":
    main()
