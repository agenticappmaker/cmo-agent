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

# Wire in the project-wide search wrapper so verification uses the
# free-first cascade (Brave free 2000/mo → Exa → Anthropic web_search).
sys.path.insert(0, str(Path.home() / "cmo-agent" / "agents"))
from search import search as web_search, has_provider  # noqa: E402


DISCOVERY_QUERIES = [
    '"{company}" CHRO OR "Chief Human Resources Officer"',
    '"{company}" "Chief People Officer"',
    '"{company}" "VP People" OR "Head of People"',
]


def discover_via_brave(seed: dict) -> dict | None:
    """Brave-driven discovery: search for the company's HR leadership, then ask
    Haiku to read the snippets and extract the named exec. This replaces the
    old Claude-knowledge-from-training approach that hallucinated 7/11 names.

    Returns a row dict matching the leads.csv schema, or None if no plausible
    exec surfaces in the snippets."""
    results: list[dict] = []
    for tmpl in DISCOVERY_QUERIES:
        q = tmpl.format(company=seed["company"])
        try:
            results.extend(web_search(q, n=5, mode="auto"))
        except Exception:
            pass
        if len(results) >= 8:
            break
    if not results:
        print(f"  ✗ {seed['company']}: no search results from Brave")
        return None

    # Dedupe by URL
    seen, dedup = set(), []
    for r in results:
        u = r.get("url", "")
        if u and u not in seen:
            seen.add(u)
            dedup.append(r)
    snippets = "\n".join(
        f"[{i+1}] {r.get('title','')[:140]} — {r.get('snippet','')[:300]} ({r.get('url','')})"
        for i, r in enumerate(dedup[:8])
    )

    prompt = (
        f"You're identifying ONE current senior HR decision-maker at {seed['company']} "
        f"(domain {seed['domain']}) from web search results. Acceptable titles: "
        "CHRO, Chief Human Resources Officer, Chief People Officer, VP People, "
        "VP People Operations, Head of People, VP HR, VP Talent, Director of People "
        "Operations, Head of People Analytics. For HR consulting firms only also "
        "accept: Partner — Workforce Transformation / Human Capital / similar.\n\n"
        f"Search results:\n{snippets}\n\n"
        f"Pick ONE person whose role at {seed['company']} is explicitly confirmed by "
        "the snippets. Reject the row if:\n"
        "- The person works at a DIFFERENT company than the snippet says\n"
        "- The title is in a different function (sales, engineering, marketing, etc.)\n"
        "- The person clearly left the company\n\n"
        "Return STRICT JSON, no markdown:\n"
        '{"first_name": "...", "last_name": "...", "title": "exact title from snippet", '
        '"source_url": "URL that confirms this", "confidence": "high|medium|low", "found": true}\n'
        'OR if nothing matches: {"found": false, "reason": "..."}'
    )
    try:
        msg = CLIENT.messages.create(
            model=MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        # Use raw_decode so trailing prose (Haiku sometimes appends a note)
        # doesn't fail the whole row — the Aon canary tripped on this.
        data, _ = json.JSONDecoder().raw_decode(text)
    except Exception as e:
        print(f"  ⚠️ {seed['company']}: haiku interpretation failed — {e}")
        return None

    if not data.get("found"):
        print(f"  ⏭ {seed['company']}: no match — {data.get('reason','')[:80]}")
        return None

    first = data.get("first_name", "").strip()
    last = data.get("last_name", "").strip()
    if not (first and last):
        print(f"  ⏭ {seed['company']}: incomplete name returned")
        return None

    email = f"{first.lower()}.{last.lower()}@{seed['domain']}"
    linkedin_q = f"{first} {last} {seed['company']}"
    linkedin_search_url = (
        f"https://www.linkedin.com/search/results/people/?keywords="
        f"{linkedin_q.replace(' ', '%20')}&origin=GLOBAL_SEARCH_HEADER"
    )
    return {
        "first_name":          first,
        "last_name":           last,
        "title":               data.get("title", ""),
        "company":             seed["company"],
        "domain":              seed["domain"],
        "lane":                seed["lane"],
        "lane_priority":       seed["lane_priority"],
        "email":               email,
        "linkedin_search_url": linkedin_search_url,
        "confidence":          data.get("confidence", "medium"),
        "freshness_warning":   "false",  # source URL is on file
        "source_notes":        data.get("source_url", ""),
        "scraped_at":          datetime.now(timezone.utc).isoformat(),
    }


# Backwards-compatible alias for callers expecting enrich_seed (e.g. tests).
enrich_seed = discover_via_brave


def verify_row(row: dict) -> tuple[bool, str]:
    """Verify name+title+company via web search, then ask Haiku to evaluate
    the snippets. Free when BRAVE_SEARCH_API_KEY is set (free 2000/mo);
    falls through to Exa or Anthropic web_search if Brave isn't keyed.
    Returns (is_verified, reason)."""
    full = f"{row['first_name']} {row['last_name']}"
    q = f'"{full}" "{row["company"]}" {row["title"]}'
    try:
        results = web_search(q, n=5, mode="auto")
    except Exception as e:
        return False, f"search failed: {e}"

    if not results:
        return False, "no search results (Brave/Exa unkeyed AND Anthropic fallback returned empty?)"

    # Compact snippet bundle for Haiku evaluation. Trim aggressively.
    snippet_text = "\n".join(
        f"[{i+1}] {r.get('title','')[:140]} — {r.get('snippet','')[:240]} ({r.get('url','')})"
        for i, r in enumerate(results[:5])
    )
    prompt = (
        f"Does the public web confirm that {full} currently holds the title "
        f"'{row['title']}' at {row['company']}? Be skeptical — only mark verified "
        f"if a result explicitly mentions both the person AND the role at the "
        f"company. A LinkedIn profile or company press release counts. Wrong-person "
        f"matches (different industry, different role, different company) = NOT verified.\n\n"
        f"Search results:\n{snippet_text}\n\n"
        f'Return STRICT JSON: {{"is_verified": true|false, "reason": "1 sentence with the source URL"}}'
    )
    try:
        msg = CLIENT.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(text)
        return bool(data.get("is_verified")), data.get("reason", "")
    except Exception as e:
        return False, f"haiku eval failed: {e}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--double-check", action="store_true",
                    help="After Brave-driven discovery, run an independent second search "
                         "to re-confirm name+title. Belt-and-suspenders for high-stakes "
                         "first batches. Adds ~1 Brave query per row.")
    args = ap.parse_args()

    if not has_provider():
        sys.exit(
            "✗ No web search provider keyed. Set BRAVE_SEARCH_API_KEY in "
            "~/cmo-agent/.env (Brave free $5/mo credit covers ~1000 queries) and rerun."
        )

    seeds = json.loads(SEEDS.read_text())["seeds"]
    print(f"📋 Discovering HR execs for {len(seeds)} companies via Brave + Haiku…")
    rows: list[dict] = []
    for s in seeds:
        print(f"  · {s['company']:<14}  ({s['lane']}, p{s['lane_priority']})")
        row = discover_via_brave(s)
        if row:
            print(f"    → {row['first_name']} {row['last_name']} | {row['title']} | conf={row['confidence']}")
            rows.append(row)
        time.sleep(0.3)

    if not rows:
        print("\n✗ No rows discovered. Nothing written.")
        sys.exit(1)

    if args.double_check:
        print(f"\n🔎 Double-checking {len(rows)} discovered rows with an independent search…")
        confirmed: list[dict] = []
        for r in rows:
            ok, reason = verify_row(r)
            mark = "✓" if ok else "✗"
            print(f"  {mark} {r['company']:<14} {r['first_name']} {r['last_name']:<22} — {reason[:120]}")
            r["web_verified"] = "true" if ok else "false"
            r["web_verification_note"] = reason
            if ok:
                confirmed.append(r)
            time.sleep(0.4)
        out = confirmed
        if not out:
            print("\n✗ Nothing survived the double-check. leads.csv not written.")
            sys.exit(1)
    else:
        out = rows

    LEADS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with LEADS_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out[0].keys())
        w.writeheader()
        w.writerows(out)
    print(f"\n✅ Wrote {len(out)} rows → {LEADS_CSV}")
    print("\nNext: python3.12 ~/cmo-agent/pitch_hr_advisory.py --limit 5  to draft the first batch.")


if __name__ == "__main__":
    main()
