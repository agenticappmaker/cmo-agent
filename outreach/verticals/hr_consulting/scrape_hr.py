"""
HR vertical scraper — enriches canary_seeds.json (companies only) with a
likely HR decision-maker per company + email guess + LinkedIn search URL.

Why Claude-seed + web-enrich and not a true LinkedIn scraper:
  - Per Steven's 2026-06-17 choice (option 4 = "cheap version, public info"),
    we identify the person via Claude knowledge then verify via web search.
  - LinkedIn public search is rate-limited + cookie-walled; doing it at any
    real volume needs Sales Nav (DEFERRED per free-first rule). For the
    initial canary batch, Claude-knowledge-seed is faster and good enough.
  - Every row carries a `confidence` field and `freshness_warning` so Steven
    can see when the identification is shaky.

Output schema (leads.csv) matches what engine.py + pitch_hr_advisory.py
expect:
  first_name, last_name, title, company, domain, lane, lane_priority,
  email, linkedin_search_url, confidence, freshness_warning, source_notes,
  scraped_at

Cost guard: free-first rule — uses Claude Haiku, not Sonnet/Opus.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path.home() / "cmo-agent" / ".env")

THIS = Path(__file__).resolve().parent
SEEDS = THIS / "canary_seeds.json"
LEADS_CSV = THIS / "leads.csv"               # only written when --verify is on
UNVERIFIED_CSV = THIS / "leads_unverified.csv"  # written by the no-verify path

CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-haiku-4-5-20251001"
VERIFY_MODEL = "claude-sonnet-4-6"  # web_search tool needs Sonnet+


def _prompt(seed: dict) -> str:
    return f"""You are helping build a cold-outreach lead list for an AI consulting service.

Target company: {seed['company']}  (domain: {seed['domain']})
Lane: {seed['lane']}  (lane_priority {seed['lane_priority']})

Identify ONE senior HR decision-maker at this company who:
- Is currently in role (or was as of your training cutoff — flag uncertainty)
- Holds one of: CHRO, Chief People Officer, VP People, VP People Operations,
  Head of People, VP HR, VP Talent, Director of People Operations,
  Head of People Analytics. For hr_consulting_firm lane only, also accept:
  Partner / Practice Lead — Workforce Transformation, Human Capital, or
  similar.

Return STRICT JSON only (no markdown, no commentary), with this shape:

{{
  "first_name": "...",
  "last_name": "...",
  "title": "exact public title",
  "email_pattern_guess": "firstname.lastname | firstinitial+lastname | firstname+lastinitial | first.last+number",
  "email": "synthesized email at {seed['domain']}",
  "linkedin_search_url": "https://www.linkedin.com/search/results/people/?keywords=...&origin=GLOBAL_SEARCH_HEADER (use first+last+company)",
  "confidence": "high | medium | low",
  "freshness_warning": "true if you're unsure they're still in role; false if confident",
  "source_notes": "1 sentence on where you'd verify this (e.g. 'public LinkedIn profile', 'recent press release', 'company leadership page')"
}}

If you cannot identify a plausible person with at least medium confidence,
return: {{"skip": true, "reason": "..."}}
"""


def enrich_seed(seed: dict) -> dict | None:
    """Ask Claude for one likely HR contact at this company. Returns row dict
    matching the leads.csv schema, or None if Claude says skip."""
    try:
        msg = CLIENT.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": _prompt(seed)}],
        )
        text = msg.content[0].text.strip()
        # Strip code fences if Claude added them despite instructions.
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
        data = json.loads(text)
    except Exception as e:
        print(f"  ⚠️ {seed['company']}: enrichment failed — {e}")
        return None
    if data.get("skip"):
        print(f"  ⏭ {seed['company']}: skipped — {data.get('reason', '')}")
        return None
    return {
        "first_name":          data.get("first_name", ""),
        "last_name":           data.get("last_name", ""),
        "title":               data.get("title", ""),
        "company":             seed["company"],
        "domain":              seed["domain"],
        "lane":                seed["lane"],
        "lane_priority":       seed["lane_priority"],
        "email":               data.get("email", ""),
        "linkedin_search_url": data.get("linkedin_search_url", ""),
        "confidence":          data.get("confidence", "low"),
        "freshness_warning":   str(data.get("freshness_warning", True)).lower(),
        "source_notes":        data.get("source_notes", ""),
        "scraped_at":          datetime.now(timezone.utc).isoformat(),
    }


def verify_row(row: dict) -> tuple[bool, str]:
    """Use Claude Sonnet's web_search tool to verify name+title+company is real
    and current. Returns (is_verified, reason)."""
    q = f"{row['first_name']} {row['last_name']} {row['title']} {row['company']}"
    prompt = (
        f"Verify whether '{row['first_name']} {row['last_name']}' currently holds the title "
        f"'{row['title']}' at {row['company']}. Search the web. Return STRICT JSON: "
        f'{{"is_verified": true|false, "reason": "1 sentence with the source URL or what you found"}}'
    )
    try:
        msg = CLIENT.messages.create(
            model=VERIFY_MODEL,
            max_tokens=512,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
            messages=[{"role": "user", "content": prompt}],
        )
        # Find the final text block (after tool calls)
        text = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text = block.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(text)
        return bool(data.get("is_verified")), data.get("reason", "")
    except Exception as e:
        return False, f"verification failed: {e}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="Verify each name+title via web search before writing to leads.csv. "
                         "Costs ~$0.01/lead in Anthropic credits. Without this flag, output "
                         "lands in leads_unverified.csv and the drafter refuses to read it.")
    args = ap.parse_args()

    seeds = json.loads(SEEDS.read_text())["seeds"]
    print(f"📋 Enriching {len(seeds)} canary seeds via Claude Haiku…")
    rows: list[dict] = []
    for s in seeds:
        print(f"  · {s['company']:<14}  ({s['lane']}, p{s['lane_priority']})")
        row = enrich_seed(s)
        if row:
            rows.append(row)
        time.sleep(0.3)

    if not rows:
        print("✗ No rows enriched. Nothing written.")
        sys.exit(1)

    if args.verify:
        print(f"\n🔎 Verifying {len(rows)} rows via Claude Sonnet web_search…")
        verified: list[dict] = []
        for r in rows:
            ok, reason = verify_row(r)
            mark = "✓" if ok else "✗"
            print(f"  {mark} {r['company']:<14} {r['first_name']} {r['last_name']:<22} — {reason[:120]}")
            r["web_verified"] = "true" if ok else "false"
            r["web_verification_note"] = reason
            if ok:
                verified.append(r)
            time.sleep(0.5)
        target = LEADS_CSV
        out = verified
        if not out:
            print("\n✗ No rows survived verification. leads.csv not written.")
            sys.exit(1)
    else:
        target = UNVERIFIED_CSV
        out = rows

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out[0].keys())
        w.writeheader()
        w.writerows(out)
    print(f"\n✅ Wrote {len(out)} rows → {target}")
    if not args.verify:
        print("⚠️  Drafter refuses to read leads_unverified.csv. "
              "Rerun with --verify to produce leads.csv, OR hand-verify and rename.")
    else:
        print("\nNext: python3.12 ~/cmo-agent/pitch_hr_advisory.py --limit 5  to draft the first batch.")


if __name__ == "__main__":
    main()
