"""
Spirit Library partnership outreach sender.
- Sends from spiritlibraryapp@gmail.com (separate reputation from AI outreach)
- Targets ONLY hospitality leads (restaurant, bar, cafe, pub, pizzeria, diner)
- Dedupes against existing nationwide bar list (outreach/targets/bars_nationwide.json)
- Pitch: QR-code coasters → Spirit Library cocktail library + upload-your-own-menu
- Rate limits: 40/day, 5/hour, 15 min between sends (same as AI outreach)
"""
import argparse, csv, json, os, re, smtplib, sys, time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT.parent / ".env"
LEADS_CSV = ROOT / "targets" / "master_leads.csv"   # use full 16k master
LOG_FILE = ROOT / "logs" / "spiritlibrary_emails.csv"
STATE_FILE = ROOT / "state" / "spiritlibrary_email_state.json"
OPTOUT_FILE = ROOT / "state" / "optout.txt"         # shared across both senders
NATIONWIDE_BARS = Path(__file__).resolve().parent.parent / "outreach" / "targets" / "bars_nationwide.json"

DAILY_LIMIT = 40
HOURLY_LIMIT = 5
DELAY_SECS = 900  # 15 min
FOLLOWUP_AFTER_DAYS = 4

# Hospitality-only filter — categories where a cocktail QR coaster actually fits.
# Excluded: bakery, cafe, coffee_shop, fast_food, caterer, food_court, ice_cream
# (pastry shops / coffee-only / to-go don't serve cocktails)
HOSPITALITY_CATEGORIES = {
    "restaurant", "bar", "pub", "nightclub",
    "brewery", "winery", "biergarten",
    "pizzeria", "diner",
}

# Garbage-email filter — reject addresses with <3 chars in the local-part
VALID_LOCAL = re.compile(r"^[a-z0-9][a-z0-9._%+\-]{2,}$")

sys.path.insert(0, str(ROOT))
from templates import spiritlibrary_partner_cold, spiritlibrary_partner_followup  # noqa: E402


def load_env_pair(key: str) -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE}")
    m = re.search(rf"^{key}\s*=\s*(.+)$", ENV_FILE.read_text(), re.M)
    if not m:
        sys.exit(f"{key} not in .env")
    return m.group(1).strip().strip('"').strip("'")


GMAIL_USER = load_env_pair("SPIRIT_GMAIL_USER")
GMAIL_PASS = load_env_pair("SPIRIT_GMAIL_APP_PASSWORD")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"sent": {}, "daily": {}, "hourly": {}}


def save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def load_optout() -> set:
    if not OPTOUT_FILE.exists():
        return set()
    return {line.strip().lower() for line in OPTOUT_FILE.read_text().splitlines() if line.strip()}


def load_nationwide_emails() -> set:
    """Emails already in the nationwide bar campaign — skip to avoid double-hits."""
    if not NATIONWIDE_BARS.exists():
        return set()
    try:
        data = json.loads(NATIONWIDE_BARS.read_text())
        return {str(x.get("contact_email", "")).lower().strip() for x in data if x.get("contact_email")}
    except Exception:
        return set()


def log_send(to: str, stage: str, status: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp_utc", "email", "stage", "status"])
        w.writerow([datetime.now(timezone.utc).isoformat(), to, stage, status])


def within_rate_limit(state: dict):
    now = datetime.now(timezone.utc)
    d = now.strftime("%Y-%m-%d")
    h = now.strftime("%Y-%m-%d-%H")
    daily = state.get("daily", {}).get(d, 0)
    hourly = state.get("hourly", {}).get(h, 0)
    return (daily < DAILY_LIMIT and hourly < HOURLY_LIMIT, daily, hourly)


def bump_counts(state: dict) -> None:
    now = datetime.now(timezone.utc)
    d = now.strftime("%Y-%m-%d")
    h = now.strftime("%Y-%m-%d-%H")
    state.setdefault("daily", {})[d] = state.get("daily", {}).get(d, 0) + 1
    state.setdefault("hourly", {})[h] = state.get("hourly", {}).get(h, 0) + 1


def send_smtp(to: str, subject: str, body: str) -> None:
    msg = MIMEMultipart()
    msg["From"] = f"Steven Samori <{GMAIL_USER}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = GMAIL_USER
    msg["List-Unsubscribe"] = f"<mailto:{GMAIL_USER}?subject=unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)


def pick_stage(email_state):
    if "cold" not in email_state:
        return "cold"
    if "followup" in email_state:
        return None
    last = datetime.fromisoformat(email_state["cold"])
    age_days = (datetime.now(timezone.utc) - last).days
    if age_days >= FOLLOWUP_AFTER_DAYS:
        return "followup"
    return None


def pick_template(contact: dict, stage: str):
    if stage == "cold":
        return spiritlibrary_partner_cold(contact)
    return spiritlibrary_partner_followup(contact)


def load_leads():
    if not LEADS_CSV.exists():
        sys.exit(f"✗ Missing {LEADS_CSV}")
    with open(LEADS_CSV) as f:
        rows = [r for r in csv.DictReader(f) if r.get("email")]
    # Hospitality only — cocktail-appropriate categories
    rows = [r for r in rows if r.get("category", "").lower() in HOSPITALITY_CATEGORIES]
    # Drop junk emails (short/weird local-parts)
    def clean_email_ok(row):
        em = row.get("email", "").lower().strip()
        if "@" not in em:
            return False
        local = em.split("@", 1)[0]
        return bool(VALID_LOCAL.match(local))
    rows = [r for r in rows if clean_email_ok(r)]
    # Stable order: category then name
    rows.sort(key=lambda r: (r.get("category", ""), r.get("name", "")))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--preview", type=int, default=3)
    args = ap.parse_args()

    leads = load_leads()
    state = load_state()
    optout = load_optout()
    skip_nationwide = load_nationwide_emails()
    print(
        f"📬 {len(leads)} hospitality leads. "
        f"Sent-to-date: {len(state.get('sent', {}))}. "
        f"Opt-outs: {len(optout)}. "
        f"Skip (nationwide dedupe): {len(skip_nationwide)}."
    )

    if args.dry_run:
        print("\n— DRY RUN —\n")
        shown = 0
        for lead in leads:
            if shown >= args.preview:
                break
            to = lead["email"].lower().strip()
            if to in optout or to in skip_nationwide:
                continue
            stage = pick_stage(state.get("sent", {}).get(to, {}))
            if not stage:
                continue
            msg = pick_template(lead, stage)
            print("=" * 72)
            print(f"TO:      {to}")
            print(f"STAGE:   {stage}")
            print(f"SUBJECT: {msg['subject']}")
            print("-" * 72)
            print(msg["body"])
            shown += 1
        return

    sent = skipped = failed = 0
    for lead in leads:
        to = lead["email"].lower().strip()
        if not to or "@" not in to:
            continue
        if to in optout or to in skip_nationwide:
            skipped += 1
            continue
        stage = pick_stage(state.get("sent", {}).get(to, {}))
        if not stage:
            skipped += 1
            continue

        ok, daily, hourly = within_rate_limit(state)
        if not ok:
            print(f"⏸  Rate limit hit (daily {daily}/{DAILY_LIMIT}, hourly {hourly}/{HOURLY_LIMIT}). Stop.")
            break
        if args.limit is not None and sent >= args.limit:
            print(f"⏸  --limit {args.limit} reached. Stop.")
            break

        msg = pick_template(lead, stage)
        try:
            send_smtp(to, msg["subject"], msg["body"])
            state.setdefault("sent", {}).setdefault(to, {})[stage] = datetime.now(timezone.utc).isoformat()
            bump_counts(state)
            save_state(state)
            log_send(to, stage, "sent")
            print(f"  ✓ [{stage:8s}] {lead.get('name','?')[:40]:40s} → {to}")
            sent += 1
            time.sleep(DELAY_SECS)
        except Exception as e:
            log_send(to, stage, f"failed:{e}")
            print(f"  ✗ {to}: {e}")
            failed += 1
            if "5.7.8" in str(e) or "BadCredentials" in str(e) or "535" in str(e):
                print(f"\n⛔ SMTP auth failure. Fix SPIRIT_GMAIL_APP_PASSWORD in .env.")
                break
            if args.limit is not None and (sent + failed) >= args.limit:
                break
            time.sleep(10)

    ok, daily, hourly = within_rate_limit(state)
    print(f"\n✅ Session: sent {sent} · skipped {skipped} · failed {failed}")
    print(f"   Today: {daily}/{DAILY_LIMIT} · this hour: {hourly}/{HOURLY_LIMIT}")


if __name__ == "__main__":
    main()
