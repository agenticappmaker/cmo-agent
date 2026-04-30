"""Grade-priority outreach sender (PIR v1.2-h aware).

Drop-in alternative to send_emails.py. Differences:
  - Source is ~/axon/state/heuristic_grades.csv (graded leads), not westchester_leads_clean.csv
  - Sends DESCENDING by grade_letter then grade_score (A → B → C → ...)
  - Default --min-grade B (skips C/D/F unless overridden)
  - Email body includes ai_leverage_summary as the lead-in
  - Shares state file with send_emails.py → no duplicate sends across both
  - Same Gmail SMTP, rate limits, opt-out, and CAN-SPAM headers as legacy sender

NOT loaded into launchd. Run manually until Steven cuts the legacy 10am job over.

Usage:
    python3.12 send_emails_graded.py --dry-run
    python3.12 send_emails_graded.py --limit 5
    python3.12 send_emails_graded.py --min-grade A          # only A grades
    python3.12 send_emails_graded.py --min-grade B          # default
    python3.12 send_emails_graded.py --tier 1               # Tier-1 zips only
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT.parent / ".env"
GRADED_CSV = Path("/Users/claudecode/axon/state/heuristic_grades.csv")
LOG_FILE = ROOT / "logs" / "westchester_emails.csv"          # shared log
STATE_FILE = ROOT / "state" / "email_state.json"             # shared dedup state
OPTOUT_FILE = ROOT / "state" / "optout.txt"                  # shared opt-out

DAILY_LIMIT = 40
HOURLY_LIMIT = 5
DELAY_SECS = 900
FOLLOWUP_AFTER_DAYS = 4

GRADE_RANK = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

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


def log_send(to: str, stage: str, status: str, grade: str = "") -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp_utc", "email", "stage", "status", "grade"])
        w.writerow([datetime.now(timezone.utc).isoformat(), to, stage, status, grade])


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


def load_graded_leads(min_grade: str, only_tier: int | None) -> list[dict]:
    if not GRADED_CSV.exists():
        sys.exit(f"✗ No graded leads at {GRADED_CSV}\n  "
                 "Run heuristic_grade.py first.")
    threshold = GRADE_RANK.get(min_grade, 4)
    rows: list[dict] = []
    with open(GRADED_CSV) as f:
        for r in csv.DictReader(f):
            if not r.get("email"):
                continue
            if GRADE_RANK.get(r.get("grade_letter", ""), 0) < threshold:
                continue
            if only_tier is not None and str(r.get("geo_tier", "")) != str(only_tier):
                continue
            try:
                r["_score"] = float(r.get("grade_score", "0"))
            except ValueError:
                r["_score"] = 0.0
            r["_rank"] = GRADE_RANK.get(r.get("grade_letter", ""), 0)
            rows.append(r)
    rows.sort(key=lambda r: (-r["_rank"], -r["_score"]))
    return rows


def personalize_body(template_body: str, lead: dict) -> str:
    """Inject the ai_leverage_summary as a personalized opener if present."""
    summary = (lead.get("ai_leverage_summary") or "").strip()
    if not summary:
        return template_body
    # Only inject if the template has a {{ai_lead}} marker; otherwise leave unchanged.
    return template_body.replace("{{ai_lead}}", summary)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview, send nothing")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap this run (still respects DAILY_LIMIT)")
    ap.add_argument("--preview", type=int, default=5)
    ap.add_argument("--min-grade", choices=["A", "B", "C", "D", "F"], default="B",
                    help="Lowest grade to send to (default B)")
    ap.add_argument("--tier", type=int, choices=[0, 1, 2], default=None,
                    help="Restrict to this geo tier")
    args = ap.parse_args()

    leads = load_graded_leads(args.min_grade, args.tier)
    state = load_state()
    optout = load_optout()
    breakdown: dict[str, int] = {}
    for r in leads:
        breakdown[r["grade_letter"]] = breakdown.get(r["grade_letter"], 0) + 1
    print(f"📬 graded pool: {len(leads)} leads ≥ {args.min_grade} "
          f"({breakdown}). Sent-to-date: {len(state.get('sent', {}))}. "
          f"Opt-outs: {len(optout)}.")
    if args.tier is not None:
        print(f"   Tier filter: {args.tier} only")

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
            body = personalize_body(msg["body"], lead)
            print("=" * 72)
            print(f"GRADE:   {lead['grade_letter']} / {lead['grade_score']}")
            print(f"TRADE:   {lead.get('trade', '?')}  TOWN: {lead.get('town', '?')}")
            print(f"TO:      {to}")
            print(f"STAGE:   {stage}")
            print(f"SUBJECT: {msg['subject']}")
            print("-" * 72)
            print(body)
            shown += 1
        print("\n— end dry run —")
        return

    sent = skipped = failed = 0
    for lead in leads:
        to = lead["email"].lower().strip()
        if not to or "@" not in to or to in optout:
            skipped += 1
            continue
        stage = pick_stage(state.get("sent", {}).get(to, {}))
        if not stage:
            skipped += 1
            continue

        ok, daily, hourly = within_rate_limit(state)
        if not ok:
            print(f"⏸  Rate limit hit (daily {daily}/{DAILY_LIMIT}, "
                  f"hourly {hourly}/{HOURLY_LIMIT}). Stop.")
            break
        if args.limit is not None and sent >= args.limit:
            print(f"⏸  --limit {args.limit} reached. Stop.")
            break

        msg = pick_template(lead, stage)
        body = personalize_body(msg["body"], lead)
        try:
            send_smtp(to, msg["subject"], body)
            state.setdefault("sent", {}).setdefault(to, {})[stage] = \
                datetime.now(timezone.utc).isoformat()
            bump_counts(state)
            save_state(state)
            log_send(to, stage, "sent", lead["grade_letter"])
            print(f"  ✓ [{lead['grade_letter']} {lead['grade_score']:>5}] "
                  f"[{stage:8s}] {lead.get('name', '?')[:40]:40s} → {to}")
            sent += 1
            time.sleep(DELAY_SECS)
        except Exception as e:
            log_send(to, stage, f"failed:{e}", lead["grade_letter"])
            print(f"  ✗ {to}: {e}")
            failed += 1
            if "5.7.8" in str(e) or "BadCredentials" in str(e) or "535" in str(e):
                print("\n⛔ SMTP auth failure. Stopping run. "
                      "Fix GMAIL_APP_PASSWORD in .env.")
                break
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
