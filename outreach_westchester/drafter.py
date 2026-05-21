"""Sender-profile-driven DRAFT generator.

Symmetric counterpart to engine.py for `auto_send: false` profiles. Same
profile schema, same `--sender <name>` CLI, but instead of SMTP-ing the
pitches it writes them to Gmail Drafts + JSON outboxes for Steven to review.

Usage:
    python3 drafter.py --sender press                  # draft 5 (profile default)
    python3 drafter.py --sender influencer --limit 3   # draft 3
    python3 drafter.py --sender press --status         # show queued draft counts
    python3 drafter.py --sender all                    # draft from every drafter profile

The profile JSON's `integration.queue_writer` field tells drafter which
underlying pitch_*.py script to invoke. Drafter applies the cadence + dedup
rules from the profile (90-day re-pitch window, daily caps) and surfaces
counts to the daily PM digest pipeline.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SENDERS_DIR = ROOT / "senders"
CMO_ROOT = ROOT.parent  # ~/cmo-agent

# Map of which pitch_*.py script implements each draft-only profile.
# This mirrors the auto-send engine's "load_leads via profile.audience.source"
# but for our markdown-sourced, human-reviewed lanes.
PROFILE_TO_DRAFTER = {
    "press":      CMO_ROOT / "pitch_press.py",
    "influencer": CMO_ROOT / "pitch_influencers.py",
    # Future: distillery, bev_director once those promote from one-shot scripts
    # to full profiles.
}


def load_profile(name: str) -> dict:
    p = SENDERS_DIR / f"{name}.json"
    if not p.exists():
        sys.exit(f"✗ Profile not found: {p}")
    return json.loads(p.read_text())


def assert_draft_profile(profile: dict) -> None:
    if profile["approval"].get("auto_send", False):
        sys.exit(
            f"✗ Profile {profile['name']} has auto_send=true — "
            f"use engine.py instead (engine.py --sender {profile['name']})."
        )


def list_draft_profiles() -> list[str]:
    out = []
    for p in sorted(SENDERS_DIR.glob("*.json")):
        try:
            cfg = json.loads(p.read_text())
            if not cfg.get("approval", {}).get("auto_send", False):
                out.append(cfg["name"])
        except Exception:
            continue
    return out


def queue_path_for(profile: dict) -> Path:
    """Where this profile's drafts get queued."""
    qw = profile.get("integration", {}).get("queue_writer", "")
    # Profiles point at outreach/<name>_drafts.json convention
    if profile["name"] == "press":
        return CMO_ROOT / "outreach" / "press_drafts.json"
    if profile["name"] == "influencer":
        return CMO_ROOT / "outreach" / "influencer_drafts.json"
    # Fallback — let the profile declare an explicit path
    declared = profile.get("integration", {}).get("draft_review_path")
    if declared:
        return CMO_ROOT / declared if not declared.startswith("/") else Path(declared)
    sys.exit(f"✗ Profile {profile['name']} has no queue path resolved")


def count_drafted_recently(profile: dict, within_days: int = 90) -> int:
    """Count drafts created within the dedup window."""
    qp = queue_path_for(profile)
    if not qp.exists():
        return 0
    try:
        items = json.loads(qp.read_text())
    except Exception:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    n = 0
    for x in items:
        ts = x.get("drafted_at") or x.get("queued_at") or x.get("created_at")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > cutoff:
                n += 1
        except Exception:
            continue
    return n


def daily_cap_for(profile: dict) -> int:
    """Pull the daily draft cap from the profile."""
    rl = profile.get("rate_limits", {})
    return rl.get("daily_max") or rl.get("daily_max_email") or 5


def count_drafted_today(profile: dict) -> int:
    qp = queue_path_for(profile)
    if not qp.exists():
        return 0
    try:
        items = json.loads(qp.read_text())
    except Exception:
        return 0
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sum(
        1 for x in items
        if today_iso in (x.get("drafted_at") or x.get("queued_at") or "")
    )


def show_status(profile_name: str) -> None:
    profile = load_profile(profile_name)
    qp = queue_path_for(profile)
    n_total = 0
    if qp.exists():
        try:
            n_total = len(json.loads(qp.read_text()))
        except Exception:
            pass
    n_today = count_drafted_today(profile)
    n_90d = count_drafted_recently(profile, 90)
    daily_cap = daily_cap_for(profile)
    auto_send = profile["approval"].get("auto_send", False)
    print(f"📋 [{profile_name}] approval.auto_send={auto_send}")
    print(f"    queue file: {qp}")
    print(f"    total drafts queued:  {n_total}")
    print(f"    drafted today:        {n_today}/{daily_cap}")
    print(f"    drafted in last 90d:  {n_90d}")
    appr = profile.get("approval", {})
    rev = (
        appr.get("review_destination")
        or appr.get("review_destination_email")
        or "?"
    )
    print(f"    review destination:   {rev}")


def draft_for(profile_name: str, limit: int | None = None) -> int:
    profile = load_profile(profile_name)
    assert_draft_profile(profile)

    drafter_script = PROFILE_TO_DRAFTER.get(profile_name)
    if not drafter_script or not drafter_script.exists():
        sys.exit(f"✗ No underlying drafter script wired for profile {profile_name}")

    daily_cap = daily_cap_for(profile)
    drafted_today = count_drafted_today(profile)
    remaining = max(0, daily_cap - drafted_today)
    if limit is None:
        limit = remaining
    else:
        limit = min(limit, remaining)

    if limit <= 0:
        print(f"⏸ [{profile_name}] daily cap hit ({drafted_today}/{daily_cap}). No drafts queued this run.")
        return 0

    appr = profile.get("approval", {})
    rev = (
        appr.get("review_destination")
        or appr.get("review_destination_email")
        or "?"
    )
    print(f"📝 [{profile_name}] drafting {limit} pitches "
          f"(today: {drafted_today}/{daily_cap}, cap remaining: {remaining})")
    print(f"    via {drafter_script.relative_to(CMO_ROOT)}")
    print(f"    review destination: {rev}")
    print()

    # Run the underlying pitch_*.py script — it accepts an integer limit as argv[1].
    venv_python = Path.home() / "spirit_venv" / "bin" / "python"
    py = str(venv_python) if venv_python.exists() else sys.executable
    try:
        result = subprocess.run(
            [py, str(drafter_script), str(limit)],
            cwd=str(CMO_ROOT),
            capture_output=False,
            check=False,
        )
        if result.returncode != 0:
            print(f"\n✗ [{profile_name}] drafter exited {result.returncode}", file=sys.stderr)
            return 0
    except Exception as e:
        print(f"\n✗ [{profile_name}] failed: {e}", file=sys.stderr)
        return 0

    new_today = count_drafted_today(profile)
    added = new_today - drafted_today
    print(f"\n✓ [{profile_name}] +{added} drafted this run. Today total: {new_today}/{daily_cap}")
    return added


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sender", required=True,
                    help="Profile name (e.g. press, influencer) — or 'all' to draft every drafter profile.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Max drafts to create this run. Defaults to profile's daily_max minus what's already drafted today.")
    ap.add_argument("--status", action="store_true",
                    help="Show queue counts and profile config without drafting.")
    args = ap.parse_args()

    if args.sender == "all":
        targets = list_draft_profiles()
        if args.status:
            for t in targets:
                show_status(t)
                print()
            return
        print(f"🚀 drafter.py --sender all → running {len(targets)} profile(s): {targets}\n")
        total = 0
        for t in targets:
            total += draft_for(t, args.limit)
            print()
        print(f"━━━ Sequence done. {total} drafts created across {len(targets)} profile(s). ━━━")
        return

    if args.status:
        show_status(args.sender)
        return
    draft_for(args.sender, args.limit)


if __name__ == "__main__":
    main()
