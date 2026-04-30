"""
Find public emails for bartender / cocktail-creator Instagram accounts
by having Claude (with the web_search tool) actually visit their IG bio,
linktree, and website, and return the email listed there.

This is NOT scraping Instagram directly (their TOS forbids it and Meta's
business_discovery endpoint is locked for the Spirit Library CMO app).
Instead we rely on Claude's server-side web_search, which hits public
search engines / public bio pages (linktrees, personal sites) where
creators publish their own email for business inquiries.

Output: outreach/bartender_leads.json — one record per handle, only kept
when Claude returned an email WITH a cited source URL.
Progress is saved INCREMENTALLY after every probe, so interrupting is safe.

Usage:
  python find_bartender_emails_ig.py                # auto-discover + probe
  python find_bartender_emails_ig.py --discover-only  # just expand handle list
  python find_bartender_emails_ig.py h1 h2 h3 ...   # probe specific handles
  TARGET=500 python find_bartender_emails_ig.py     # override target count
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "outreach"
LEADS_FILE = OUT_DIR / "bartender_leads.json"
HANDLES_FILE = OUT_DIR / "bartender_handles.json"  # discovered seed pool

MODEL = "claude-sonnet-4-6"
WORKERS = 2
MAX_USES = 3
TARGET = int(os.environ.get("TARGET", "500"))

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
HANDLE_RE = re.compile(r"@([a-zA-Z0-9._]{2,30})")

FILE_LOCK = threading.Lock()

# Known-real seed — well-vetted accounts including the ones Steven flagged.
CURATED_SEED = [
    # Steven-flagged superstars
    "thirsty_whale", "thirstywhale", "luifern",
    # Classics / legends
    "tipsybartender", "jeffreymorgenthaler", "educatedbarfly", "anders_erickson",
    "the.educated.barfly", "simplesyrupco", "cocktailchemistryguy",
    "deathandcompany", "attaboyny", "employeesonlyny", "pdtnyc",
    "katana_kitten", "doublechickenplease", "liccocktails",
    "milkandhoneynyc", "amor_y_amargo", "drinkmasters", "cocktailkingdom",
    # Press / publications
    "imbibe", "difford_guide", "punch_drink", "cocktailsdistilled",
    "cocktailwonk", "liquor_com", "the_spirits_business",
    # Known creator personalities
    "jim_meehan", "julie_reiner", "audrey_saunders", "monicaberg79",
    "erik_lorincz", "ryanchetiyawardana", "mrlyan", "alexkratena",
    "tonykonecny", "sam_ross_bartender", "jillianvose", "naren_young",
    "joaquinsimo", "sother_teague", "iainmcpherson",
    "robertsimonson", "kevinperonedrinks", "toby_maloney", "camper.english",
    "salvatore_calabrese", "drinksbyelle", "kaleenadrinks",
]


def _retry_call(fn, *args, retries=5, base=10.0, **kwargs):
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except anthropic.RateLimitError:
            if attempt == retries - 1:
                raise
            time.sleep(base * (2 ** attempt))
    return fn(*args, **kwargs)


def _extract_text(resp):
    """Concatenate all text blocks (web_search responses may have multiple)."""
    parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts)


def _first_json(text, opener="{", closer="}"):
    start = text.find(opener)
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


# ============================================================
# Handle discovery — harvest large pools from web_search
# ============================================================

DISCOVERY_QUERIES = [
    "top bartenders to follow on Instagram 2025 list handles",
    "best mixologists Instagram accounts 2024 follow",
    "Instagram bartenders similar to @thirsty_whale @luifern",
    "Imbibe Magazine bartenders Instagram list",
    "World's 50 Best Bars bartender Instagram handles",
    "home bartender Instagram influencers 2025",
    "USBG bartenders Instagram handles",
    "Tales of the Cocktail speaker Instagram",
    "cocktail TikTok creators also on Instagram list",
    "female bartenders Instagram to follow 2025",
    "Asian American bartenders Instagram",
    "Latino mixologists Instagram bartender",
    "London bartenders Instagram handles 2024",
    "Tokyo Japan bartenders Instagram account",
    "tiki bartenders Instagram handles",
    "agave tequila mezcal bartenders Instagram",
    "whiskey cocktail bartenders Instagram 2025",
    "bar-owner Instagram accounts cocktail",
    "craft cocktail content creators Instagram",
    "bartender podcast host Instagram handles",
]


def _one_discovery(query):
    prompt = f"""Use the web_search tool to find public articles / lists for the query below,
then extract every Instagram handle of a bartender, mixologist, cocktail creator,
bar owner, cocktail writer, or cocktail brand mentioned in those articles.

Query: {query}

Rules:
- Only handles that actually appear in the fetched pages
- Strip the leading @
- Prefer handles you can tell from context are active cocktail-content creators
- Do NOT invent handles

Return ONLY a JSON array of lowercase handles (no @, no markdown):
["handle1","handle2",...]
"""
    try:
        resp = _retry_call(
            client.messages.create,
            model=MODEL,
            max_tokens=1500,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        print(f"  [discover] {query[:60]!r:62s} ERR {str(e)[:80]}")
        return []
    text = _extract_text(resp)
    m = re.search(r"\[[\s\S]*?\]", text)
    handles = []
    if m:
        try:
            handles = [h.lower().lstrip("@") for h in json.loads(m.group(0)) if isinstance(h, str)]
        except Exception:
            handles = []
    # Fallback: regex @handle extraction from raw text
    if not handles:
        handles = [h.lower() for h in HANDLE_RE.findall(text)]
    # Dedupe / filter
    handles = [h for h in handles if 2 <= len(h) <= 30]
    print(f"  [discover] {query[:60]!r:62s} +{len(handles)}")
    return handles


def discover_handles(target):
    """Run discovery queries until we hit `target` unique handles."""
    pool = set(h.lower().lstrip("@") for h in CURATED_SEED)
    # Persisted pool from prior runs
    if HANDLES_FILE.exists():
        try:
            prior = json.loads(HANDLES_FILE.read_text())
            pool.update(h.lower().lstrip("@") for h in prior)
        except Exception:
            pass
    print(f"[discover] starting pool: {len(pool)}")
    # Run queries serially — each burns ~8k tokens with web search
    for q in DISCOVERY_QUERIES:
        if len(pool) >= target:
            break
        pool.update(_one_discovery(q))
        # Persist as we go
        HANDLES_FILE.write_text(json.dumps(sorted(pool), indent=2))
    print(f"[discover] final pool: {len(pool)}")
    return sorted(pool)


# ============================================================
# Known-handle filter + dedupe
# ============================================================

def load_known_handles():
    """Handles already in outreach pipelines or prior lead file — skip."""
    known = set()
    for fname in ("outbox.json", "dm_queue.json", "apollo_replies.json"):
        p = OUT_DIR / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    h = item.get("handle") or item.get("instagram_handle") or item.get("username")
                    if h:
                        known.add(h.lower().lstrip("@"))
    return known


def load_results():
    if LEADS_FILE.exists():
        try:
            return json.loads(LEADS_FILE.read_text())
        except Exception:
            pass
    return []


def save_results(results):
    """Atomic write under file lock."""
    with FILE_LOCK:
        tmp = LEADS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        tmp.replace(LEADS_FILE)


# ============================================================
# Per-handle email probe
# ============================================================

def probe_handle(handle):
    prompt = f"""Find the public business / press / collaboration email for the
Instagram account @{handle} (a cocktail bartender, mixologist, or creator).

Check, using web_search:
1. Instagram bio (via social-link aggregators or cached snippets)
2. Linktree / beacons.ai / stan.store / allmylinks
3. Personal website if one is linked
4. Any press kit or contact page

Return ONLY one JSON object, no prose, no markdown fences:
{{
  "handle": "{handle}",
  "email": "<email string or null>",
  "source_url": "<URL where email was actually visible or null>",
  "bio_summary": "<1-sentence summary of what they post>",
  "follower_estimate": "<e.g. '120k' or null>",
  "confidence": "high|medium|low"
}}

CRITICAL:
- Only set email non-null if you actually saw it on a page fetched via web_search.
- Never fabricate or guess an email.
- If no email is publicly available, set email=null AND source_url=null.
"""
    try:
        resp = _retry_call(
            client.messages.create,
            model=MODEL,
            max_tokens=1000,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_USES}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        return {"handle": handle, "email": None, "error": str(e)[:200]}

    text = _extract_text(resp)
    blob = _first_json(text, "{", "}")
    if not blob:
        return {"handle": handle, "email": None, "error": "no json"}
    try:
        data = json.loads(blob)
    except Exception as e:
        return {"handle": handle, "email": None, "error": f"parse: {e}"}
    data["handle"] = handle
    em = (data.get("email") or "").strip().lower()
    if em and EMAIL_RE.fullmatch(em):
        data["email"] = em
    else:
        data["email"] = None
    return data


# ============================================================
# Main
# ============================================================

def main():
    OUT_DIR.mkdir(exist_ok=True)

    # Option flags
    discover_only = "--discover-only" in sys.argv
    cli_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cli_handles = [a.lower().lstrip("@") for a in cli_args]

    known = load_known_handles()
    results = load_results()
    # handles already probed (with or without email) — skip re-probing
    probed = {r.get("handle") for r in results if r.get("handle")}
    print(f"[setup] {len(known)} handles already in outreach pipelines")
    print(f"[setup] {len(probed)} handles already probed (in leads file)")

    # Build target list
    if cli_handles:
        targets = cli_handles
        print(f"[seed] CLI: {len(targets)} handles")
    else:
        pool = discover_handles(target=TARGET + 100)  # extra buffer
        targets = [h for h in pool if h not in known and h not in probed]
        targets = targets[:TARGET]
        print(f"[seed] {len(targets)} handles to probe this run (target={TARGET})")

    if discover_only:
        print("[done] --discover-only; skipping email probes")
        return

    # Probe
    start = time.time()
    new_with_email = 0
    new_probed = 0

    def _handle_one(h):
        nonlocal new_with_email, new_probed
        rec = probe_handle(h)
        rec["source"] = "claude_web_search"
        rec["category"] = "cocktail_creator_ig"
        # Only keep records that have an email + source (higher quality)
        email = rec.get("email")
        src = rec.get("source_url")
        if email and src:
            with FILE_LOCK:
                # Merge: replace if handle already present
                for i, existing in enumerate(results):
                    if existing.get("handle") == rec["handle"]:
                        results[i] = rec
                        break
                else:
                    results.append(rec)
                new_with_email += 1
                new_probed += 1
            save_results(results)
            return (h, email, src, True)
        else:
            new_probed += 1
            return (h, None, None, False)

    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(_handle_one, h): h for h in targets}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            h, email, src, ok = fut.result()
            if ok:
                print(f"  [{i:3d}/{len(targets)}] {h:25s}  ✉ {email}  ← {src[:55]}")
            else:
                print(f"  [{i:3d}/{len(targets)}] {h:25s}  —")

    elapsed = time.time() - start
    total_emails = sum(1 for r in results if r.get("email"))
    print()
    print(f"[summary] new probes this run:          {new_probed}")
    print(f"[summary] new emails this run:          {new_with_email}")
    print(f"[summary] total leads in {LEADS_FILE.name}: {len(results)} (with email: {total_emails})")
    print(f"[summary] elapsed: {elapsed/60:.1f} min")


if __name__ == "__main__":
    main()
