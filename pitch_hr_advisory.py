"""
HR advisory drafter — symmetric to pitch_press.py / pitch_influencers.py.

Reads enriched leads from outreach/verticals/hr_consulting/leads.csv,
applies opt-out + dedup filters, builds cold drafts via the vertical's
templates module, and writes to outreach/hr_advisory_drafts.json for
Steven to review.

Draft-review path only — engine.py (auto-send) is gated until Steven
flips senders/hr_advisory.json `approval.auto_send` to true after he
reads the first batch. Per Steven 2026-06-17.

Usage:
    python3.12 pitch_hr_advisory.py                # draft default limit (5)
    python3.12 pitch_hr_advisory.py --limit 3
    python3.12 pitch_hr_advisory.py --status       # show queued draft counts

Output:
    ~/cmo-agent/outreach/hr_advisory_drafts.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEADS_CSV = ROOT / "outreach" / "verticals" / "hr_consulting" / "leads.csv"
TEMPLATES_DIR = ROOT / "outreach" / "verticals" / "hr_consulting"
DRAFTS = ROOT / "outreach" / "hr_advisory_drafts.json"
OPTOUT = ROOT / "outreach_westchester" / "state" / "optout.txt"

DEFAULT_LIMIT = 5

sys.path.insert(0, str(TEMPLATES_DIR))
from templates import hr_advisory_cold, SUBJECT_VARIANTS  # noqa: E402


def _load_optouts() -> set[str]:
    if not OPTOUT.exists():
        return set()
    return {l.strip().lower() for l in OPTOUT.read_text().splitlines() if l.strip()}


def _load_drafts() -> list[dict]:
    if not DRAFTS.exists():
        return []
    try:
        return json.loads(DRAFTS.read_text())
    except json.JSONDecodeError:
        return []


def _save_drafts(drafts: list[dict]) -> None:
    DRAFTS.parent.mkdir(parents=True, exist_ok=True)
    DRAFTS.write_text(json.dumps(drafts, indent=2))


def load_leads() -> list[dict]:
    if not LEADS_CSV.exists():
        sys.exit(
            f"✗ {LEADS_CSV} not found. Run scrape_hr.py first:\n"
            f"   python3.12 {LEADS_CSV.parent / 'scrape_hr.py'}"
        )
    with LEADS_CSV.open() as f:
        rows = list(csv.DictReader(f))
    # Sort: lane_priority asc (1 = primary buyers), then scraped_at desc
    rows.sort(key=lambda r: (int(r.get("lane_priority", 99)), r.get("scraped_at", "")), reverse=False)
    return rows


def cmd_status() -> None:
    drafts = _load_drafts()
    queued = [d for d in drafts if d.get("status") == "drafted"]
    sent = [d for d in drafts if d.get("status") == "sent"]
    print(f"hr_advisory_drafts.json — {len(queued)} queued, {len(sent)} sent")
    for d in queued[-10:]:
        print(f"  · {d['email']:<40} {d['company']:<14} ({d.get('lane','?')})")


def cmd_draft(limit: int) -> None:
    leads = load_leads()
    optouts = _load_optouts()
    drafts = _load_drafts()
    already = {d["email"].lower() for d in drafts}
    fresh = 0
    for row in leads:
        if fresh >= limit:
            break
        email = (row.get("email") or "").lower()
        if not email:
            continue
        if email in optouts:
            print(f"  ⏭ opt-out: {email}")
            continue
        if email in already:
            print(f"  ⏭ already drafted: {email}")
            continue
        sv_idx = len(drafts) % len(SUBJECT_VARIANTS)
        pitch = hr_advisory_cold(
            first_name=row.get("first_name", ""),
            company=row.get("company", ""),
            subject_variant=SUBJECT_VARIANTS[sv_idx],
        )
        drafts.append({
            "email":               email,
            "first_name":          row.get("first_name", ""),
            "last_name":           row.get("last_name", ""),
            "title":               row.get("title", ""),
            "company":             row.get("company", ""),
            "domain":              row.get("domain", ""),
            "lane":                row.get("lane", ""),
            "lane_priority":       int(row.get("lane_priority", 99)),
            "confidence":          row.get("confidence", "low"),
            "freshness_warning":   row.get("freshness_warning", "true"),
            "linkedin_search_url": row.get("linkedin_search_url", ""),
            "subject":             pitch["subject"],
            "body":                pitch["body"],
            "stage":               "cold",
            "status":              "drafted",
            "drafted_at":          datetime.now(timezone.utc).isoformat(),
        })
        fresh += 1
        print(f"  ✎ {email:<40} {row.get('company','?'):<14} ({row.get('confidence','?')})")
    _save_drafts(drafts)
    print(f"\n✅ {fresh} new drafts → {DRAFTS}")
    print("\nReview: open outreach/hr_advisory_drafts.json")
    print("Approve a draft: set its status from 'drafted' → 'approved' (engine.py only sends 'approved')")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.status:
        cmd_status()
    else:
        cmd_draft(args.limit)


if __name__ == "__main__":
    main()
