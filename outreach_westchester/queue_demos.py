"""Compute tomorrow's demo-qualifying lead queue for a sender profile.

Reads the same profile JSON the engine uses, applies the demo_gate.criteria, and writes
the resulting lead list to state/demo_queue.json. A Claude session (or a launchd-triggered
headless `claude -p ...` job) then iterates the queue, spawns case-study-cloner per lead,
and writes the produced URLs into state/demo_urls.json keyed by lead email.

Engine.py reads state/demo_urls.json at send time and injects the URL into the cold body
when one exists for that lead.

Usage:
    python3.12 queue_demos.py --sender claudesonnet111
    python3.12 queue_demos.py --sender claudesonnet111 --count          # just print how many qualify
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import engine  # reuse load_profile / load_leads / apply_filter / apply_sort


def qualifies_for_demo(lead: dict, profile: dict) -> bool:
    gate = profile.get("demo_gate", {})
    if not gate.get("enabled"):
        return False
    crit = gate.get("criteria", {})
    grade_rank = profile["audience"]["filter"].get("grade_rank", {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1})
    min_grade = grade_rank.get(crit.get("min_grade_letter", ""), 0)
    if min_grade and lead.get("_rank", 0) < min_grade:
        return False
    if crit.get("require_website") and not lead.get("_has_website"):
        return False
    if crit.get("require_fetch_status_ok") and lead.get("fetch_status") != "ok":
        return False
    cats = {c.lower() for c in crit.get("categories_allowed", [])}
    if cats:
        cat = (lead.get("trade") or lead.get("category") or "").lower()
        if cat not in cats:
            return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sender", required=True)
    ap.add_argument("--out", default=None, help="Override output path")
    ap.add_argument("--count", action="store_true", help="Print count only, don't write")
    args = ap.parse_args()

    profile = engine.load_profile(args.sender)
    raw = engine.load_leads(profile)
    filtered = engine.apply_filter(raw, profile)
    sorted_leads = engine.apply_sort(filtered, profile)

    # Skip leads already sent any stage (the engine won't queue them again either)
    state = engine.load_state(profile)
    already_sent = set(state["sent"].keys())
    bounced = set(state["bounced"].keys())

    # Skip leads that already have a cached demo URL
    cached = engine.load_demo_urls()

    queue: list[dict] = []
    for lead in sorted_leads:
        if lead["_email"] in already_sent or lead["_email"] in bounced or lead["_email"] in cached:
            continue
        if not qualifies_for_demo(lead, profile):
            continue
        try:
            pitches = json.loads(lead.get("pitch_options") or "[]")
        except Exception:
            pitches = []
        queue.append({
            "email": lead["_email"],
            "name": lead.get("name", ""),
            "website": lead.get("website") or lead.get("url") or "",
            "category": lead.get("category", lead.get("trade", "")),
            "town": lead.get("town", ""),
            "grade_letter": lead.get("grade_letter", ""),
            "grade_score": lead.get("grade_score", ""),
            "ai_leverage_summary": lead.get("ai_leverage_summary", ""),
            "gaps": lead.get("gaps", ""),
            "pitch_options": pitches[:3],
        })

    if args.count:
        print(f"[{args.sender}] {len(queue)} leads qualify for case-study-cloner")
        return

    out = Path(args.out) if args.out else ROOT / "state" / f"demo_queue_{args.sender}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sender": args.sender,
        "count": len(queue),
        "queue": queue,
    }, indent=2))
    print(f"✓ wrote {len(queue)} leads → {out}")
    print(f"\nNext step (Claude session):")
    print(f"  read {out}")
    print(f"  for each entry: spawn case-study-cloner agent with the lead's name/website/pitch_options")
    print(f"  collect URL → append to state/demo_urls.json as {{\"<email>\": \"<url>\"}}")


if __name__ == "__main__":
    main()
