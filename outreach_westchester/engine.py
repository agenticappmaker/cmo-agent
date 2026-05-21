"""Sender-profile-driven outreach engine.

One script, two pipelines, schema-defined behavior:
    python3.12 engine.py --sender claudesonnet111
    python3.12 engine.py --sender spiritlibraryapp
    python3.12 engine.py --sender claudesonnet111 --dry-run --preview 5

Each profile lives at senders/<name>.json and declares identity, audience,
pitch pack, cadence, rate limits, opt-out, bounce hygiene, and approval rules.

Behavior locked in this engine (not configurable per profile):
  - Stage picker: cold → followup → breakup based on cadence.intervals_days
  - Opt-out: state/optout.txt always consulted
  - Bad-domain blacklist: state/bad_domains.txt always consulted
  - Reply auto-pause: if state['sent'][email] has 'replied' key, no further stages
  - NDR replenish: bounced sends DO NOT count against daily cap (state tracks `bounced` separately from `daily`)
  - Demo URL injection: state/demo_urls.json (email → URL) read at send time when demo_gate.enabled
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT.parent / ".env"
SENDERS_DIR = ROOT / "senders"
STATE_DIR = ROOT / "state"
LOGS_DIR = ROOT / "logs"
DEMO_URL_FILE = STATE_DIR / "demo_urls.json"
BAD_DOMAINS_FILE = STATE_DIR / "bad_domains.txt"
OPTOUT_FILE = STATE_DIR / "optout.txt"
GENERIC_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "aol.com", "outlook.com", "icloud.com", "live.com", "msn.com"}


def load_env_pair(key: str) -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE}")
    m = re.search(rf"^{key}\s*=\s*(.+)$", ENV_FILE.read_text(), re.M)
    if not m:
        sys.exit(f"{key} not in {ENV_FILE}")
    return m.group(1).strip().strip('"').strip("'")


def load_profile(name: str) -> dict:
    p = SENDERS_DIR / f"{name}.json"
    if not p.exists():
        sys.exit(f"✗ Profile not found: {p}")
    return json.loads(p.read_text())


def load_set_from_path(path_spec: str) -> set[str]:
    """Load a lowercase email set from a state path.

    Supports:
      - 'state/optout.txt'                  -> one email per line
      - '../outreach/targets/x.json:field'  -> JSON list of dicts, pluck field
    """
    if ":" in path_spec:
        rel, field = path_spec.rsplit(":", 1)
    else:
        rel, field = path_spec, None
    full = (ROOT / rel).resolve()
    if not full.exists():
        return set()
    if field:
        try:
            data = json.loads(full.read_text())
            return {str(x.get(field, "")).lower().strip() for x in data if x.get(field)}
        except Exception:
            return set()
    return {line.strip().lower() for line in full.read_text().splitlines() if line.strip()}


def load_bad_domains() -> set[str]:
    if not BAD_DOMAINS_FILE.exists():
        return set()
    return {line.strip().lower() for line in BAD_DOMAINS_FILE.read_text().splitlines() if line.strip()}


def load_demo_urls() -> dict[str, str]:
    if not DEMO_URL_FILE.exists():
        return {}
    try:
        return {k.lower(): v for k, v in json.loads(DEMO_URL_FILE.read_text()).items()}
    except Exception:
        return {}


# ---------------------- state ----------------------

def state_path(profile: dict) -> Path:
    """Shared state file path. Engine respects profile.state.file so it shares pacing
    + dedup with the legacy senders + the axon auto-sender daemon. Falls back to
    a per-profile file only if not declared (test profiles, new lanes)."""
    declared = profile.get("state", {}).get("file")
    if declared:
        return (ROOT / declared) if not declared.startswith("/") else Path(declared)
    return STATE_DIR / f"{profile['name']}_state.json"


def load_state(profile: dict) -> dict:
    p = state_path(profile)
    if p.exists():
        s = json.loads(p.read_text())
    else:
        s = {}
    s.setdefault("sent", {})
    s.setdefault("daily", {})
    s.setdefault("hourly", {})
    s.setdefault("bounced", {})
    s.setdefault("domain_bounces", {})
    return s


def save_state(profile: dict, s: dict) -> None:
    p = state_path(profile)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, indent=2))


def within_rate_limit(state: dict, profile: dict) -> tuple[bool, int, int]:
    rl = profile["rate_limits"]
    now = datetime.now(timezone.utc)
    d = now.strftime("%Y-%m-%d")
    h = now.strftime("%Y-%m-%d-%H")
    daily = state["daily"].get(d, 0)
    hourly = state["hourly"].get(h, 0)
    return (daily < rl["daily_max"] and hourly < rl["hourly_max"], daily, hourly)


def bump_counts(state: dict, success: bool) -> None:
    now = datetime.now(timezone.utc)
    d = now.strftime("%Y-%m-%d")
    h = now.strftime("%Y-%m-%d-%H")
    if success:
        state["daily"][d] = state["daily"].get(d, 0) + 1
        state["hourly"][h] = state["hourly"].get(h, 0) + 1


# ---------------------- audience ----------------------

def expand_path(p: str) -> Path:
    return Path(os.path.expanduser(p)) if p.startswith("~") or p.startswith("/") else (ROOT / p)


def load_leads(profile: dict) -> list[dict]:
    src = profile["audience"]["source"]
    path = expand_path(src["path"])
    if not path.exists():
        sys.exit(f"✗ Leads source missing: {path}")
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return rows


def apply_filter(rows: list[dict], profile: dict) -> list[dict]:
    f = profile["audience"].get("filter", {})
    grade_rank = f.get("grade_rank", {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1})
    min_grade = grade_rank.get(f.get("min_grade_letter", ""), 0) if f.get("min_grade_letter") else 0
    cats_in = {c.lower() for c in f.get("categories_in", [])}
    local_re = re.compile(f["email_local_regex"]) if f.get("email_local_regex") else None
    skip_emails: set[str] = set()
    for spec in f.get("skip_emails_in_files", []):
        skip_emails |= load_set_from_path(spec)
    skip_emails |= load_set_from_path(profile["opt_out"]["suppression_list"])
    bad_domains = load_bad_domains()

    out: list[dict] = []
    for r in rows:
        em = (r.get("email") or "").lower().strip()
        if f.get("require_email", True) and not em:
            continue
        if "@" not in em:
            continue
        if em in skip_emails:
            continue
        domain = em.rsplit("@", 1)[-1]
        if domain in bad_domains:
            continue
        if local_re and not local_re.match(em.split("@", 1)[0]):
            continue
        if cats_in and (r.get("category") or "").lower() not in cats_in:
            continue
        if min_grade:
            rank = grade_rank.get(r.get("grade_letter", ""), 0)
            if rank < min_grade:
                continue
            r["_rank"] = rank
        r["_email"] = em
        r["_domain"] = domain
        r["_has_website"] = 1 if (r.get("website") or r.get("url") or "").startswith("http") else 0
        r["_is_business_email"] = 0 if domain in GENERIC_DOMAINS else 1
        try:
            r["_grade_score_num"] = float(r.get("grade_score", "0") or 0)
        except ValueError:
            r["_grade_score_num"] = 0.0
        out.append(r)
    return out


def apply_sort(rows: list[dict], profile: dict) -> list[dict]:
    """Multi-key stable sort. Sorts in reverse-priority order so the highest-priority key wins."""
    sort_spec = profile["audience"].get("sort", [])
    if not sort_spec:
        return rows
    def field_key(r: dict, field: str):
        # Special case: CSV grade_score is a string, use the numeric proxy set in apply_filter.
        if field == "grade_score":
            return r.get("_grade_score_num", 0.0)
        return r.get(field, "")
    out = list(rows)
    for spec in reversed(sort_spec):
        out.sort(key=lambda r, f=spec["field"]: field_key(r, f), reverse=bool(spec.get("desc")))
    return out


# ---------------------- stage + template ----------------------

def pick_stage(sent_for_lead: dict, profile: dict) -> str | None:
    cadence = profile["cadence"]
    stages = cadence["stages"]
    if cadence.get("auto_pause_on_reply") and sent_for_lead.get("replied"):
        return None
    if cadence.get("auto_pause_on_optout") and sent_for_lead.get("opted_out"):
        return None
    intervals = cadence.get("intervals_days", {})
    now = datetime.now(timezone.utc)

    if "cold" not in sent_for_lead:
        return "cold"
    if "followup" in stages and "followup" not in sent_for_lead:
        gap = intervals.get("cold_to_followup", 4)
        last = datetime.fromisoformat(sent_for_lead["cold"])
        if (now - last).days >= gap:
            return "followup"
        return None
    if "breakup" in stages and "breakup" not in sent_for_lead:
        gap = intervals.get("followup_to_breakup", 7)
        last = datetime.fromisoformat(sent_for_lead.get("followup", sent_for_lead["cold"]))
        if (now - last).days >= gap:
            return "breakup"
        return None
    return None


def render_subject(profile: dict, lead: dict, stage: str) -> tuple[str, int]:
    subjects = profile["pitch_pack"]["subjects"]
    if stage == "followup":
        return (f"Re: {subjects[0].format(name=lead.get('name','your business'))}", 0)
    if stage == "breakup":
        return ("Last note", 0)
    # cold — rotate by hash of email
    idx = abs(hash(lead["_email"])) % len(subjects)
    return (subjects[idx].format(name=lead.get("name", "your business")), idx)


def render_body(profile: dict, lead: dict, stage: str, demo_url: str | None) -> str:
    if stage == "followup":
        return _render_followup(profile, lead)
    if stage == "breakup":
        return _render_breakup(profile, lead)
    return _render_cold(profile, lead, demo_url)


def _render_cold(profile: dict, lead: dict, demo_url: str | None) -> str:
    tmpl = profile["pitch_pack"]["body_template"]
    p = profile["pitch_pack"]["personalization"]
    ctx = {
        "name": lead.get("name", "your business"),
        "town": lead.get("town", ""),
        "category": lead.get("category", ""),
        "trade": lead.get("trade", lead.get("category", "")),
        "ai_lead": "",
        "demo_block": "",
        "pitch_1_title": "", "pitch_1_oneliner": "",
        "pitch_2_title": "", "pitch_2_oneliner": "",
        "pitch_3_title": "", "pitch_3_oneliner": "",
    }
    if p["type"] == "axon_summary":
        summary = (lead.get(p["summary_field"]) or "").strip()
        ctx["ai_lead"] = summary or p.get("fallback_opener", "").format(**ctx)
        try:
            pitches = json.loads(lead.get(p["pitch_options_field"]) or "[]")
        except Exception:
            pitches = []
        for i, pitch in enumerate(pitches[:3], 1):
            ctx[f"pitch_{i}_title"] = pitch.get("title", "")
            ctx[f"pitch_{i}_oneliner"] = pitch.get("one_liner", "")
    if demo_url:
        ctx["demo_block"] = profile["pitch_pack"]["demo_block_when_present"].format(name=ctx["name"], demo_url=demo_url)
    try:
        return tmpl.format(**ctx)
    except KeyError as e:
        # if a template asks for a key we didn't supply, render with blanks
        ctx[str(e).strip("'")] = ""
        return tmpl.format(**ctx)


def _render_followup(profile: dict, lead: dict) -> str:
    name = lead.get("name", "")
    return (
        f"Hi — following up on the note I sent last week about {name}.\n\n"
        "If the timing's right, reply with which of the three ideas resonated most "
        "and I'll send a one-pager + price. If it's not — totally fine, no follow-up after this one.\n\n"
        f"{profile['identity']['signature']}\n\n"
        f"{profile['opt_out']['footer']}"
    )


def _render_breakup(profile: dict, lead: dict) -> str:
    return (
        "Last note from me on this. If any of these ideas land in the future, you know where to find me — "
        f"otherwise I'll stop here and won't email again.\n\n"
        f"{profile['identity']['signature']}\n\n"
        f"{profile['opt_out']['footer']}"
    )


# ---------------------- demo gate ----------------------

def demo_url_for(lead: dict, profile: dict, demo_urls: dict[str, str]) -> str | None:
    gate = profile.get("demo_gate", {})
    if not gate.get("enabled"):
        return None
    crit = gate.get("criteria", {})
    grade_rank = profile["audience"]["filter"].get("grade_rank", {"A": 5, "B": 4, "C": 3})
    min_grade = grade_rank.get(crit.get("min_grade_letter", ""), 0)
    if min_grade and lead.get("_rank", 0) < min_grade:
        return None
    if crit.get("require_website") and not lead.get("_has_website"):
        return None
    if crit.get("require_fetch_status_ok") and lead.get("fetch_status") != "ok":
        return None
    cats = {c.lower() for c in crit.get("categories_allowed", [])}
    if cats:
        cat = (lead.get("trade") or lead.get("category") or "").lower()
        if cat not in cats:
            return None
    return demo_urls.get(lead["_email"])


# ---------------------- SMTP + log ----------------------

def send_smtp(profile: dict, to: str, subject: str, body: str) -> None:
    ident = profile["identity"]
    user = load_env_pair(ident["smtp_user_env"])
    pw = load_env_pair(ident["smtp_pass_env"])
    msg = MIMEMultipart("mixed")
    msg["From"] = f"{ident['from_name']} <{user}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = user
    msg["List-Unsubscribe"] = f"<mailto:{user}?subject=unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(body, "plain"))
    for img_rel in profile["pitch_pack"].get("proof_assets", {}).get("attached_images", []) or []:
        img_path = Path(os.path.expanduser(img_rel))
        if img_path.exists():
            img = MIMEImage(img_path.read_bytes())
            img.add_header("Content-Disposition", "attachment", filename=img_path.name)
            msg.attach(img)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.send_message(msg)


def log_send(profile: dict, row: dict) -> None:
    log_rel = profile["metrics"]["logging_file"]
    cols = profile["metrics"].get("csv_columns", list(row.keys()))
    log_path = (ROOT / log_rel)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new = not log_path.exists()
    with open(log_path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(cols)
        w.writerow([row.get(c, "") for c in cols])


# ---------------------- bounce + replenish ----------------------

def is_bounce_exception(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(t in s for t in (
        "550", "551", "553", "user unknown", "no such user",
        "mailbox not found", "address not found", "recipient address rejected",
        "does not exist", "user not found", "5.1.1", "5.1.10",
    ))


def record_bounce(state: dict, email: str, domain: str, profile: dict) -> bool:
    """Returns True if domain was blacklisted on this bounce."""
    state["bounced"][email] = datetime.now(timezone.utc).isoformat()
    cnt = state["domain_bounces"].get(domain, 0) + 1
    state["domain_bounces"][domain] = cnt
    threshold = profile.get("bounce_hygiene", {}).get("domain_blacklist_after_n_bounces", 3)
    if cnt >= threshold:
        BAD_DOMAINS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = set()
        if BAD_DOMAINS_FILE.exists():
            existing = {l.strip().lower() for l in BAD_DOMAINS_FILE.read_text().splitlines() if l.strip()}
        if domain not in existing:
            with open(BAD_DOMAINS_FILE, "a") as f:
                f.write(f"{domain}\n")
            return True
    return False


# ---------------------- main ----------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sender", required=True, help="Profile name (e.g. claudesonnet111)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--preview", type=int, default=5)
    args = ap.parse_args()

    profile = load_profile(args.sender)
    if not profile["approval"].get("auto_send", False):
        sys.exit(f"✗ Profile {args.sender} has auto_send=false — use the drafter path instead.")

    raw = load_leads(profile)
    filtered = apply_filter(raw, profile)
    sorted_leads = apply_sort(filtered, profile)
    state = load_state(profile)
    demo_urls = load_demo_urls()

    print(f"📬 [{profile['name']}] {len(raw)} raw → {len(filtered)} after filter → "
          f"sorted by {[s['field'] for s in profile['audience'].get('sort', [])]}")
    print(f"   sent-to-date: {len(state['sent'])} · "
          f"bounced: {len(state['bounced'])} · "
          f"bad domains: {len(load_bad_domains())} · "
          f"demo URLs cached: {len(demo_urls)}")

    if args.dry_run:
        print(f"\n— DRY RUN: top {args.preview} of {len(sorted_leads)} —\n")
        shown = 0
        for lead in sorted_leads:
            if shown >= args.preview:
                break
            stage = pick_stage(state["sent"].get(lead["_email"], {}), profile)
            if not stage:
                continue
            demo = demo_url_for(lead, profile, demo_urls)
            subj, sidx = render_subject(profile, lead, stage)
            body = render_body(profile, lead, stage, demo)
            print("=" * 72)
            if lead.get("grade_letter"):
                print(f"GRADE: {lead['grade_letter']} / {lead.get('grade_score', '?')}")
            print(f"NAME: {lead.get('name', '?')[:50]} · {lead.get('town', '')} · {lead.get('category', lead.get('trade', ''))}")
            print(f"TO: {lead['_email']} · stage={stage} · demo={demo or '—'}")
            print(f"SUBJECT [{sidx}]: {subj}")
            print("-" * 72)
            print(body[:600] + ("..." if len(body) > 600 else ""))
            shown += 1
        print("\n— end dry run —")
        return

    sent = skipped = failed = bounced = 0
    for lead in sorted_leads:
        stage = pick_stage(state["sent"].get(lead["_email"], {}), profile)
        if not stage:
            skipped += 1
            continue
        ok, daily, hourly = within_rate_limit(state, profile)
        if not ok:
            print(f"⏸ rate limit hit: daily={daily}/{profile['rate_limits']['daily_max']} hourly={hourly}/{profile['rate_limits']['hourly_max']}. stop.")
            break
        if args.limit is not None and sent >= args.limit:
            print(f"⏸ --limit {args.limit} hit. stop.")
            break

        demo = demo_url_for(lead, profile, demo_urls)
        subj, sidx = render_subject(profile, lead, stage)
        body = render_body(profile, lead, stage, demo)
        try:
            send_smtp(profile, lead["_email"], subj, body)
            state["sent"].setdefault(lead["_email"], {})[stage] = datetime.now(timezone.utc).isoformat()
            bump_counts(state, success=True)
            save_state(profile, state)
            log_send(profile, {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "email": lead["_email"], "stage": stage, "status": "sent",
                "grade": lead.get("grade_letter", ""), "subject_variant": sidx,
                "demo_url": demo or "",
            })
            badge = f"[{lead.get('grade_letter','-')}]"
            print(f"  ✓ {badge} [{stage:8s}] {lead.get('name','?')[:38]:38s} → {lead['_email']}"
                  + (f"  demo:{demo}" if demo else ""))
            sent += 1
            time.sleep(profile["rate_limits"].get("seconds_between_sends", 900))
        except Exception as e:
            err = str(e)
            log_send(profile, {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "email": lead["_email"], "stage": stage,
                "status": f"failed:{err[:120]}",
                "grade": lead.get("grade_letter", ""), "subject_variant": sidx, "demo_url": demo or "",
            })
            if is_bounce_exception(e):
                blacklisted = record_bounce(state, lead["_email"], lead["_domain"], profile)
                save_state(profile, state)
                print(f"  ⚠ BOUNCE  {lead['_email']} → counts as 0 (replenish). "
                      f"{'BLACKLISTED ' + lead['_domain'] if blacklisted else ''}")
                bounced += 1
                continue
            print(f"  ✗ {lead['_email']}: {err[:160]}")
            failed += 1
            if any(t in err for t in ("5.7.8", "BadCredentials", "535")):
                print("⛔ SMTP auth failure — stop.")
                break
            time.sleep(10)

    print(f"\n✅ [{profile['name']}] sent={sent} bounced={bounced} (replenished) skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
