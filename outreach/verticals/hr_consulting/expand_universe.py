"""
One-shot expander: enlarge canary_seeds.json from the original 12 hand-picked
companies to ~330 named US companies across all three HR-lane buckets, so the
monthly Brave drain has enough to chew on (~3 queries per company × 330 = ~990,
hitting ~99% of Brave's free $5/mo credit on each cycle).

Run once locally; the result gets committed. Re-run only if you want to refresh
the universe (companies rebrand, get acquired, etc.).

  python3.12 expand_universe.py            # generate + write
  python3.12 expand_universe.py --dry-run  # show count + sample, no write
"""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path
import anthropic
from dotenv import load_dotenv

load_dotenv(Path.home() / "cmo-agent" / ".env")
CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-haiku-4-5-20251001"

THIS = Path(__file__).resolve().parent
SEEDS = THIS / "canary_seeds.json"

# Lane targets — chosen so total ≈ 330 companies, fitting under Brave's free
# tier when each company costs ~3 Brave queries during discovery.
LANE_TARGETS = {
    "f500_inhouse":      ("Fortune 500 and Fortune 1000 US companies — well-known names with formal CHRO/CPO roles. Skip companies <$1B revenue. Spread across: tech, banking/finance, healthcare, retail, manufacturing, telecom, energy, consumer goods, defense/aerospace, transportation, hospitality.",  200),
    "hr_tech_midmarket": ("US-based Series B–D and recently-IPO'd companies with strong VP People / Head of People functions. Spread across: fintech, devtools, AI/ML, SaaS, cybersecurity, healthtech, marketplaces, consumer apps. Skip foreign HQ.",                                                                                                                       100),
    "hr_consulting_firm":("HR consulting and human-capital advisory firms (Mercer, Aon, WTW, Korn Ferry, McLagan, Russell Reynolds, Heidrick, Spencer Stuart, Egon Zehnder, Deloitte Human Capital, McKinsey People & Organization, BCG People & Organization, Accenture HR, EY People Advisory, KPMG HR, Segal, Buck Consultants, etc.). 30 firms tops.",                30),
}


def generate_batch(lane: str, description: str, n: int, exclude: set[str]) -> list[dict]:
    """Ask Haiku for N companies in this lane, excluding ones already chosen."""
    exclude_txt = ", ".join(sorted(exclude)[:60]) if exclude else "(none)"
    prompt = (
        f"List exactly {n} real, US-based companies that fit this description:\n\n"
        f"  {description}\n\n"
        f"EXCLUDE these already-chosen companies:\n  {exclude_txt}\n\n"
        f"For each, return STRICT JSON (no markdown, no commentary) — a single JSON array:\n"
        f'[{{"company": "Official company name", "domain": "primary website domain, no www"}}]\n\n'
        f"Domains MUST be ones you are highly confident about (e.g., 'microsoft.com', 'jpmorganchase.com'). "
        f"If you are unsure of a company's domain, do not include it. "
        f"Do not return short names like 'IBM' as the company — use the full official name ('IBM Corporation' or 'International Business Machines'). "
        f"Do not duplicate exclude-list entries."
    )
    msg = CLIENT.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.JSONDecoder().raw_decode(text)[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    existing = json.loads(SEEDS.read_text())
    kept = existing["seeds"]                          # preserve hand-picked 12 first
    chosen_names = {s["company"].lower() for s in kept}

    new_rows: list[dict] = []
    for lane, (desc, target) in LANE_TARGETS.items():
        already_in_lane = sum(1 for s in kept if s["lane"] == lane)
        need = target - already_in_lane
        if need <= 0:
            continue
        print(f"\n=== {lane}: need {need} more (already have {already_in_lane}) ===")
        # Batch in chunks of 50 so Haiku doesn't truncate.
        while need > 0:
            chunk = min(50, need)
            try:
                batch = generate_batch(lane, desc, chunk, chosen_names)
            except Exception as e:
                print(f"  ⚠️ batch failed — {e}")
                break
            added = 0
            for c in batch:
                name = (c.get("company") or "").strip()
                domain = (c.get("domain") or "").strip().lower().replace("www.", "")
                if not name or not domain:
                    continue
                if name.lower() in chosen_names:
                    continue
                chosen_names.add(name.lower())
                lane_priority = 1 if lane in ("f500_inhouse", "hr_tech_midmarket") else 2
                new_rows.append({
                    "company": name,
                    "domain": domain,
                    "lane": lane,
                    "lane_priority": lane_priority,
                    "rationale": "Auto-generated by expand_universe.py 2026-06-17 — vetted by Brave discovery at runtime.",
                })
                added += 1
            need -= added
            if added == 0:
                print(f"  · batch returned 0 usable rows, breaking")
                break
            print(f"  · +{added} cos (need {need} more for this lane)")

    total_new = len(new_rows)
    print(f"\n📦 Generated {total_new} new companies (existing kept: {len(kept)})")
    print(f"   Sample: {', '.join(r['company'] for r in new_rows[:5])}")

    if args.dry_run:
        print("\n(dry-run, not writing)")
        return

    existing["seeds"] = kept + new_rows
    existing["_expanded_at"] = "2026-06-17"
    existing["_expansion_note"] = (
        f"First 12 entries are Steven's hand-picked canary from 2026-06-17 AM. "
        f"Remaining {total_new} were generated by expand_universe.py to fill out "
        f"the ~330-company target so the monthly Brave drain hits the free-tier "
        f"ceiling (~990 queries/mo). Brave-driven discovery in scrape_hr.py "
        f"verifies every name + title at runtime; this seed list only commits "
        f"to (company name, domain, lane)."
    )
    SEEDS.write_text(json.dumps(existing, indent=2))
    print(f"\n✅ Wrote {len(existing['seeds'])} total seeds → {SEEDS}")


if __name__ == "__main__":
    main()
