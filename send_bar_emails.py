"""
Send bar outreach emails for Spirit Library.
Pitch: free custom menu builder, staff training tool, behind-the-bar reference.
Follow-up sequence: Day 0 (cold), Day 3, Day 7.
Rate limits: max 50/day, 10/hour.
"""
import smtplib, os, json, time, csv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

GMAIL_USER = os.environ['GMAIL_USER']
GMAIL_PASS = os.environ['GMAIL_APP_PASSWORD']
APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"

# Prefer merged Apollo+Claude list, fall back to original
CONTACTS_FILE = Path('outreach/targets/bars_all_contacts.json') if Path('outreach/targets/bars_all_contacts.json').exists() else Path('outreach/targets/bars_nationwide.json')
LOG_FILE = Path('outreach/logs/bar_emails.csv')
STATE_FILE = Path('outreach/state/bar_email_state.json')

DAILY_LIMIT = 50
HOURLY_LIMIT = 10
DELAY_BETWEEN_EMAILS = 45  # seconds — stay well under rate limits


# ── Email Templates ──────────────────────────────────────────────────────────

def cold_email(contact):
    name = contact.get('contact_name')
    bar = contact.get('bar_name', 'your bar')
    greeting = f"Hi {name.split()[0]}," if name else f"Hi {bar} team,"

    return {
        "subject": f"Free tool for your bar team — Spirit Library",
        "body": f"""{greeting}

I'm Steven Samori, and I built Spirit Library — a free cocktail app with 1,700+ recipes that a lot of bar teams have started using behind the bar.

The reason I'm reaching out: Spirit Library lets you build out your own custom cocktail menu right in the app. Your team can use it to train new bartenders on recipes and techniques, keep it behind the bar as a quick reference when anyone blanks on a build, and even share your menu digitally with guests.

It's completely free — no subscription, no catch. There are 1,700+ classic and modern recipes already loaded, and your team can add your house cocktails on top of that.

Would love to get it in front of your bar team. Here's the App Store link if you want to take a look: {APP_STORE}

Happy to jump on a quick call or just answer any questions over email.

Best,
Steven Samori
Founder, Spirit Library
spiritlibrary.app"""
    }


def followup_1(contact):
    name = contact.get('contact_name')
    bar = contact.get('bar_name', 'your bar')
    greeting = f"Hi {name.split()[0]}," if name else f"Hi {bar} team,"

    return {
        "subject": f"Re: Free tool for your bar team — Spirit Library",
        "body": f"""{greeting}

Just following up on Spirit Library — wanted to make sure this didn't get buried.

The custom menu builder is the part bar teams tell me they use most. You can build your full house menu, organize it however you want, and share it with your whole staff so everyone has the same reference. No more binders or PDFs.

It's free to download, no account required to browse the 1,700+ recipes. Your team can be up and running in 5 minutes.

{APP_STORE}

— Steven"""
    }


def followup_2(contact):
    name = contact.get('contact_name')
    bar = contact.get('bar_name', 'your bar')
    greeting = f"Hi {name.split()[0]}," if name else f"Hi {bar} team,"

    return {
        "subject": f"Re: Free tool for your bar team — Spirit Library",
        "body": f"""{greeting}

Last note on this — if the timing isn't right or you're all set on tools, totally understand.

The app is live at {APP_STORE} if you ever want to check it out on your own time. It's free, no strings. A few bar teams have told me the substitution guide alone (140+ ingredients, 25+ categories) is worth having behind the bar during service.

Either way, cheers and good luck with everything at {bar}.

— Steven"""
    }


TEMPLATES = {
    "cold": cold_email,
    "followup_1": followup_1,
    "followup_2": followup_2,
}

SEQUENCE = [
    ("cold", 0),
    ("followup_1", 3),
    ("followup_2", 7),
]


# ── State Management ─────────────────────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"sent": {}, "daily_counts": {}, "hourly_counts": {}}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_send(email, stage, status):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    exists = LOG_FILE.exists()
    with open(LOG_FILE, 'a', newline='') as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(['timestamp', 'email', 'stage', 'status'])
        w.writerow([datetime.utcnow().isoformat(), email, stage, status])


def check_rate_limits(state):
    today = datetime.utcnow().strftime('%Y-%m-%d')
    hour = datetime.utcnow().strftime('%Y-%m-%d-%H')
    daily = state.get('daily_counts', {}).get(today, 0)
    hourly = state.get('hourly_counts', {}).get(hour, 0)
    return daily < DAILY_LIMIT and hourly < HOURLY_LIMIT, daily, hourly


def increment_counts(state):
    today = datetime.utcnow().strftime('%Y-%m-%d')
    hour = datetime.utcnow().strftime('%Y-%m-%d-%H')
    if 'daily_counts' not in state:
        state['daily_counts'] = {}
    if 'hourly_counts' not in state:
        state['hourly_counts'] = {}
    state['daily_counts'][today] = state['daily_counts'].get(today, 0) + 1
    state['hourly_counts'][hour] = state['hourly_counts'].get(hour, 0) + 1


# ── Sender ───────────────────────────────────────────────────────────────────

def send_email(to, subject, body):
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)


# ── Main Loop ────────────────────────────────────────────────────────────────

def run():
    if not CONTACTS_FILE.exists():
        print(f"✗ Contacts file not found: {CONTACTS_FILE}")
        print("  Run find_bars_nationwide.py first.")
        return

    contacts = json.loads(CONTACTS_FILE.read_text())
    contacts_with_email = [c for c in contacts if c.get('apollo_email') or c.get('contact_email')]
    print(f"\n🍸 Bar outreach: {len(contacts_with_email)} contacts with email (of {len(contacts)} total)\n")

    state = load_state()
    sent_count = 0
    skipped = 0
    failed = 0

    for contact in contacts_with_email:
        email = (contact.get('apollo_email') or contact['contact_email']).lower().strip()
        email_state = state.get('sent', {}).get(email, {})

        # Determine which stage to send
        stage_to_send = None
        for stage_name, day_offset in SEQUENCE:
            if stage_name in email_state:
                continue  # already sent this stage
            # Check if enough days have passed since last send
            if email_state:
                last_sent = max(email_state.values())
                last_date = datetime.fromisoformat(last_sent)
                days_since = (datetime.utcnow() - last_date).days
                if days_since < day_offset:
                    break  # not time yet
            stage_to_send = stage_name
            break

        if not stage_to_send:
            skipped += 1
            continue

        # Check rate limits
        ok, daily, hourly = check_rate_limits(state)
        if not ok:
            print(f"\n⚠ Rate limit reached (daily: {daily}/{DAILY_LIMIT}, hourly: {hourly}/{HOURLY_LIMIT}). Stopping.")
            print(f"  Run again later to continue.")
            break

        # Build and send
        template_fn = TEMPLATES[stage_to_send]
        email_content = template_fn(contact)

        try:
            send_email(email, email_content['subject'], email_content['body'])
            # Update state
            if 'sent' not in state:
                state['sent'] = {}
            if email not in state['sent']:
                state['sent'][email] = {}
            state['sent'][email][stage_to_send] = datetime.utcnow().isoformat()
            increment_counts(state)
            save_state(state)
            log_send(email, stage_to_send, 'sent')

            bar = contact.get('bar_name', '?')
            print(f"  ✓ [{stage_to_send}] {bar} → {email}")
            sent_count += 1
            time.sleep(DELAY_BETWEEN_EMAILS)

        except Exception as e:
            print(f"  ✗ {email}: {e}")
            log_send(email, stage_to_send, f'failed: {e}')
            failed += 1
            time.sleep(10)

    # Summary
    ok, daily, hourly = check_rate_limits(state)
    total_ever = len(state.get('sent', {}))
    print(f"\n{'='*60}")
    print(f"✅ Session: sent {sent_count} | skipped {skipped} | failed {failed}")
    print(f"   Total contacts emailed (all time): {total_ever}")
    print(f"   Today's sends: {daily + sent_count} / {DAILY_LIMIT}")
    print(f"   Log: {LOG_FILE}")
    print(f"{'='*60}")


if __name__ == '__main__':
    run()
