"""
Westchester local-SMB outreach sender.
- Reads outreach_westchester/targets/westchester_leads.csv
- Sends cold or followup emails via Gmail SMTP (claudesonnet111@gmail.com)
- Rate limits: 20/day default, 5/hour, 60s delay between sends
- CAN-SPAM: templates carry unsubscribe link + physical address
- Respects opt-out list at outreach_westchester/state/optout.txt

Usage:
    python3 send_emails.py --dry-run        # preview first 5, send nothing
    python3 send_emails.py --limit 5        # send just 5 (still respects daily cap)
    python3 send_emails.py                  # normal run, up to daily cap
"""
import argparse, csv, json, os, re, smtplib, sys, time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT.parent / ".env"
LEADS_CSV = ROOT / "targets" / "westchester_leads_clean.csv"
LOG_FILE = ROOT / "logs" / "westchester_emails.csv"
STATE_FILE = ROOT / "state" / "email_state.json"
OPTOUT_FILE = ROOT / "state" / "optout.txt"

DAILY_LIMIT = 40
HOURLY_LIMIT = 5
DELAY_SECS = 900  # 15 min between sends — gentle on Gmail reputation
FOLLOWUP_AFTER_DAYS = 4  # cold → followup after 4 days, once

sys.path.insert(0, str(ROOT))
from templates import pick_template  # noqa: E402


def load_env_pair(key: str) -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE}")
    m = re.search(rf"^{key}\s*=\s*(.+)$", ENV_FILE.read_text(), re.M)
    if not m:
        sys.exit(f"{key} not in .env")
    return m.group(1).strip().strip('"').strip("'")


GMAIL_USER = load_env_pair("GMAIL_USER")
GMAIL_PASS = load_env_pair("GMAIL_APP_PASSWORD")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"sent": {}, "daily": {}, "hourly": {}}


def save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def load_optout() -> set[str]:
    if not OPTOUT_FILE.exists():
        return set()
    return {line.strip().lower() for line in OPTOUT_FILE.read_text().splitlines() if line.strip()}


def log_send(to: str, stage: str, status: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp_utc", "email", "stage", "status"])
        w.writerow([datetime.now(timezone.utc).isoformat(), to, stage, status])


def within_rate_limit(state: dict) -> tuple[bool, int, int]:
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
    # List-Unsubscribe header → Gmail/Outlook show unsub button natively
    msg["List-Unsubscribe"] = f"<mailto:{GMAIL_USER}?subject=unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)


def pick_stage(email_state: dict) -> str | None:
    if "cold" not in email_state:
        return "cold"
    if "followup" in email_state:
        return None
    last = datetime.fromisoformat(email_state["cold"])
    age_days = (datetime.now(timezone.utc) - last).days
    if age_days >= FOLLOWUP_AFTER_DAYS:
        return "followup"
    return None


def load_leads() -> list[dict]:
    if not LEADS_CSV.exists():
        sys.exit(f"✗ No leads file yet: {LEADS_CSV}\n  Run scrape_leads.py first.")
    with open(LEADS_CSV) as f:
        rows = [r for r in csv.DictReader(f) if r.get("email")]
    # stable sort: by category then name so sends feel balanced
    rows.sort(key=lambda r: (r.get("category", ""), r.get("name", "")))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print previews, send nothing")
    ap.add_argument("--limit", type=int, default=None, help="Cap this run (still respects DAILY_LIMIT)")
    ap.add_argument("--preview", type=int, default=5, help="How many to preview in --dry-run")
    args = ap.parse_args()

    leads = load_leads()
    state = load_state()
    optout = load_optout()
    print(f"📬 {len(leads)} leads with email. Sent-to-date: {len(state.get('sent', {}))}. Opt-outs: {len(optout)}.")

    if args.dry_run:
        print("\n— DRY RUN — previewing first emails, sending nothing —\n")
        shown = 0
        for lead in leads:
            if shown >= args.preview:
                break
            to = lead["email"].lower().strip()
            if to in optout:
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
        print("\n— end dry run —")
        return

    sent = 0
    skipped = 0
    failed = 0

    for lead in leads:
        to = lead["email"].lower().strip()
        if not to or "@" not in to:
            continue
        if to in optout:
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
            # Bail out fast on auth failures — prevents runaway retry loops
            if "5.7.8" in str(e) or "BadCredentials" in str(e) or "535" in str(e):
                print(f"\n⛔ SMTP auth failure. Stopping run. Fix GMAIL_APP_PASSWORD in .env.")
                break
            # Count failures against --limit so a broken pipe doesn't keep trying
            if args.limit is not None and (sent + failed) >= args.limit:
                print(f"⏸  --limit {args.limit} reached (incl. failures). Stop.")
                break
            time.sleep(10)

    ok, daily, hourly = within_rate_limit(state)
    print(f"\n{'='*60}")
    print(f"✅ Session: sent {sent} · skipped {skipped} · failed {failed}")
    print(f"   Today: {daily}/{DAILY_LIMIT} · this hour: {hourly}/{HOURLY_LIMIT}")
    print(f"   Log: {LOG_FILE}")


if __name__ == "__main__":
    main()
