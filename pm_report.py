#!/usr/bin/env python3
"""
Weekly PM Report — Spirit Library
Reads local files, scrapes cocktail news, generates HTML report, sends via Resend.
"""

import json
import os
import subprocess
import sys
import re
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent

def _load_env_from_dotenv() -> None:
    env_path = BASE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

_load_env_from_dotenv()

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TO_EMAIL = "claudesonnet111@gmail.com"

# Cocktail & drinks RSS feeds to scrape
RSS_FEEDS = [
    ("Imbibe Magazine",     "https://imbibemagazine.com/feed/"),
    ("Punch Drink",         "https://punchdrink.com/feed/"),
    ("Liquor.com",          "https://www.liquor.com/rss"),
    ("Difford's Guide",     "https://www.diffordsguide.com/feed"),
]

STYLE = """
body { font-family: Arial, sans-serif; background: #f0f0f0; margin: 0; padding: 20px; }
.wrap { max-width: 680px; margin: auto; background: white; border-radius: 8px; overflow: hidden; }
.header { background: #1a1a2e; color: white; padding: 24px 28px; }
.header h1 { margin: 0; font-size: 22px; }
.header p { margin: 4px 0 0; opacity: 0.7; font-size: 13px; }
.section-head { background: #1a1a2e; color: white; padding: 10px 20px; font-size: 14px; font-weight: bold; margin-top: 0; }
.body { padding: 20px 28px; }
.item { padding: 10px 0; border-bottom: 1px solid #eee; font-size: 14px; }
.item:last-child { border-bottom: none; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; margin-left: 6px; }
.ok { background: #d4edda; color: #155724; }
.fail { background: #f8d7da; color: #721c24; }
.warn { background: #fff3cd; color: #856404; }
.pending { background: #d1ecf1; color: #0c5460; }
.stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0; }
.stat { background: #f8f9fa; border-radius: 6px; padding: 10px 16px; text-align: center; flex: 1; min-width: 80px; }
.stat .num { font-size: 24px; font-weight: bold; color: #1a1a2e; }
.stat .lbl { font-size: 11px; color: #666; margin-top: 2px; }
.priority { counter-reset: item; padding: 0; list-style: none; }
.priority li { counter-increment: item; padding: 10px 0 10px 36px; border-bottom: 1px solid #eee; font-size: 14px; position: relative; }
.priority li:before { content: counter(item); position: absolute; left: 0; top: 10px; background: #1a1a2e; color: white; width: 22px; height: 22px; border-radius: 50%; text-align: center; line-height: 22px; font-size: 12px; font-weight: bold; }
.priority li:last-child { border-bottom: none; }
"""


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return []


def fetch_rss(url, timeout=10):
    """Fetch an RSS feed via curl and return raw XML text."""
    result = subprocess.run(
        ["curl", "-s", "-L", "--max-time", str(timeout), "-A",
         "Mozilla/5.0 (compatible; SpiritLibraryBot/1.0)", url],
        capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else ""


def parse_rss_titles(xml, max_items=5):
    """Extract titles and descriptions from RSS XML without external libraries."""
    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", xml, re.DOTALL)
    descs  = re.findall(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", xml, re.DOTALL)
    # Flatten tuples, strip HTML tags, skip feed-level title (first entry)
    clean = lambda s: re.sub(r"<[^>]+>", "", s).strip()
    titles = [clean(a or b) for a, b in titles if (a or b).strip()][1:max_items+1]
    descs  = [clean(a or b)[:200] for a, b in descs if (a or b).strip()][1:max_items+1]
    return list(zip(titles, descs))


def gather_cocktail_intelligence():
    """Scrape RSS feeds + (if keyed) Brave/Exa search, then ask Claude to
    summarize trends + suggest features."""
    print("  Fetching cocktail news feeds...")
    raw_items = []
    for source, url in RSS_FEEDS:
        xml = fetch_rss(url)
        if xml:
            items = parse_rss_titles(xml, max_items=4)
            for title, desc in items:
                if title:
                    raw_items.append(f"[{source}] {title}: {desc}")

    # Supplement RSS with neural search when Brave/Exa keyed. Free-first:
    # Brave 2000/mo budget covers daily runs.
    try:
        from agents.search import search as web_search, has_provider
        if has_provider():
            for q in ("cocktail trends 2026", "new spirit launches this week", "bartender innovation"):
                for r in web_search(q, n=3, mode="auto"):
                    if r.get("title"):
                        raw_items.append(f"[{r['provider']}] {r['title']}: {r.get('snippet', '')[:200]}")
    except ImportError:
        pass

    if not raw_items:
        return {"cocktails": [], "features": []}

    # Build a compact prompt for Claude haiku (cheapest, fastest)
    feed_text = "\n".join(raw_items[:20])
    prompt = f"""You are a product strategist for Spirit Library, a cocktail recipe iOS app with 1,700+ recipes.

Here are this week's cocktail news headlines:
{feed_text}

Return a JSON object with exactly this structure (no markdown, just raw JSON):
{{
  "cocktails": [
    {{"name": "...", "why": "1-2 sentences on why it's trending and fits Spirit Library"}},
    ... (6-8 items)
  ],
  "features": [
    {{"feature": "...", "rationale": "1-2 sentences on why users would love this"}},
    ... (4-5 ideas)
  ]
}}

For cocktails: identify specific trending drinks, new ingredients, or seasonal flavors worth adding to the app.
For features: suggest genuinely useful app features inspired by current cocktail culture trends (e.g. seasonal collections, mood-based filters, ingredient spotlight, etc). Be specific and creative."""

    sys.path.insert(0, str(BASE / "venv/lib/python3.9/site-packages"))
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        # Strip markdown code fences if present
        text = re.sub(r"^```json\s*|^```\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        result = json.loads(text)
        return {
            "cocktails": result.get("cocktails", []),
            "features":  result.get("features", [])
        }
    except Exception as e:
        print(f"  Intelligence fetch failed: {e}")
        return {"cocktails": [], "features": []}


def gather_data():
    return {
        "history":        read_json(BASE / "posts/spirit-library_history.json"),
        "queue":          read_json(BASE / "posts/queue.json"),
        "influencers":    read_json(BASE / "outreach/targets/influencers.json"),
        "brands":         read_json(BASE / "outreach/targets/brands.json"),
        "delivery":       read_json(BASE / "outreach/targets/delivery.json"),
        "bars":           read_json(BASE / "outreach/targets/bars_hospitality.json"),
        "press":          read_json(BASE / "outreach/targets/press.json"),
        "podcasts":       read_json(BASE / "outreach/targets/podcasts.json"),
        "outbox":         read_json(BASE / "outreach/outbox.json"),
        "sent_log":       read_json(BASE / "outreach/sent_log.json"),
        "research_cache": read_json(BASE / "outreach/research_cache.json"),
    }


def tag(label, style):
    return f'<span class="tag {style}">{label}</span>'


def build_intelligence_sections(intel):
    """Build HTML for cocktail intelligence and feature ideas sections."""
    cocktail_rows = ""
    for item in intel.get("cocktails", []):
        name = item.get("name", "")
        why  = item.get("why", "")
        cocktail_rows += f'<div class="item">🍹 <strong>{name}</strong><br><span style="color:#555;font-size:13px">{why}</span></div>'
    if not cocktail_rows:
        cocktail_rows = '<div class="item" style="color:#999">No cocktail data fetched this week.</div>'

    feature_rows = ""
    for item in intel.get("features", []):
        feat = item.get("feature", "")
        rationale = item.get("rationale", "")
        feature_rows += f'<div class="item">💡 <strong>{feat}</strong><br><span style="color:#555;font-size:13px">{rationale}</span></div>'
    if not feature_rows:
        feature_rows = '<div class="item" style="color:#999">No feature data fetched this week.</div>'

    cocktail_section = f"""
  <div class="section-head">🌍 Cocktail Intelligence — What's Trending</div>
  <div class="body">{cocktail_rows}</div>"""

    feature_section = f"""
  <div class="section-head">💡 Feature Ideas for Spirit Library</div>
  <div class="body">{feature_rows}</div>"""

    return cocktail_section, feature_section


def generate_html(data, intel=None):
    today = datetime.now().strftime("%B %d, %Y")
    if intel is None:
        intel = {"cocktails": [], "features": []}

    history = data["history"] if isinstance(data["history"], list) else []
    published = [p for p in history if p.get("status") == "published"]
    failed    = [p for p in history if p.get("status") == "failed"]
    queue     = data["queue"] if isinstance(data["queue"], list) else []
    queued    = [p for p in queue if p.get("status") not in ("published", "failed")]

    outbox        = data["outbox"] if isinstance(data["outbox"], list) else []
    sent_outbox   = [e for e in outbox if e.get("status") == "sent"]
    pending_outbox = [e for e in outbox if e.get("status") != "sent"]
    sent_log      = data["sent_log"] if isinstance(data["sent_log"], list) else []

    def cnt(k): return len(data[k]) if isinstance(data[k], list) else 0
    total_targets = cnt("influencers") + cnt("brands") + cnt("delivery") + cnt("bars") + cnt("press") + cnt("podcasts")
    researched = len(data["research_cache"]) if isinstance(data["research_cache"], (list, dict)) else 0
    research_pct = int(researched / total_targets * 100) if total_targets else 0

    # ── Section 1: CMO Posts ──────────────────────────────────────
    posts_rows = ""
    for p in published[-5:]:
        platform = p.get("platform", "").capitalize()
        caption = p.get("caption", "")[:100] + ("…" if len(p.get("caption", "")) > 100 else "")
        date = (p.get("published_at") or p.get("created_at") or "")[:10]
        posts_rows += f'<div class="item">✓ <strong>{platform}</strong> — {caption} {tag("published", "ok")} <span style="color:#999;font-size:12px">{date}</span></div>'

    for p in failed:
        platform = p.get("platform", "").capitalize()
        err = (p.get("error") or "unknown error")[:80]
        posts_rows += f'<div class="item">✗ <strong>{platform}</strong> — {err} {tag("failed", "fail")}</div>'

    if not posts_rows:
        posts_rows = '<div class="item" style="color:#999">No posts recorded yet.</div>'

    # Platform status
    platform_status = """
    <div class="item">📸 <strong>Instagram</strong> — Publishing WORKING {ok}</div>
    <div class="item">🐦 <strong>Twitter/X</strong> — FAILED: 402 Payment Required (out of API credits) {fail}</div>
    <div class="item">🎵 <strong>TikTok</strong> — Blocked until App Store URL is live {warn}</div>
    """.format(ok=tag("working", "ok"), fail=tag("failed", "fail"), warn=tag("blocked", "warn"))

    queued_note = f'<div class="item" style="color:#555">Posts in queue: <strong>{len(queued)}</strong></div>'

    # ── Section 2: Outreach ───────────────────────────────────────
    target_stats = f"""
    <div class="stat-row">
      <div class="stat"><div class="num">{total_targets}</div><div class="lbl">Total Targets</div></div>
      <div class="stat"><div class="num">{cnt("influencers")}</div><div class="lbl">Influencers</div></div>
      <div class="stat"><div class="num">{cnt("brands")}</div><div class="lbl">Brands</div></div>
      <div class="stat"><div class="num">{cnt("delivery")}</div><div class="lbl">Delivery/Retail</div></div>
      <div class="stat"><div class="num">{cnt("bars")}</div><div class="lbl">Bars</div></div>
      <div class="stat"><div class="num">{cnt("press")}</div><div class="lbl">Press</div></div>
      <div class="stat"><div class="num">{cnt("podcasts")}</div><div class="lbl">Podcasts</div></div>
    </div>
    <div class="item">🔬 Research complete: <strong>{researched}/{total_targets}</strong> profiles ({research_pct}%)</div>
    """

    sent_rows = ""
    for e in sent_outbox:
        name = e.get("name", "Unknown")
        subj = e.get("subject", "")[:70]
        hook = e.get("key_hook", "")[:100]
        sent_at = (e.get("sent_at") or "")[:10]
        sent_rows += f'<div class="item">✉ <strong>{name}</strong> {tag("sent", "ok")} <span style="color:#999;font-size:12px">{sent_at}</span><br><span style="color:#555;font-size:13px">{subj}</span><br><span style="color:#777;font-size:12px">{hook}</span></div>'

    if not sent_rows:
        sent_rows = '<div class="item" style="color:#999">No emails sent yet.</div>'

    pending_rows = ""
    for e in pending_outbox[:6]:
        name = e.get("name", "Unknown")
        subj = e.get("subject", "")[:70]
        pending_rows += f'<div class="item">📋 <strong>{name}</strong> {tag("pending", "pending")}<br><span style="color:#555;font-size:13px">{subj}</span></div>'

    if not pending_rows:
        pending_rows = '<div class="item" style="color:#999">No pending emails.</div>'

    # ── Section 3: App Status ─────────────────────────────────────
    app_checklist = """
    <div class="item">✅ Privacy Policy + Terms links in app</div>
    <div class="item">✅ Age gate implemented</div>
    <div class="item">✅ Sign in with Apple implemented in app code</div>
    <div class="item">✅ EAS env vars set for production</div>
    <div class="item">✅ Apple Developer Program enrolled</div>
    <div class="item">❌ Sign in with Apple — configure in Supabase (needs Services ID + .p8 key) {fail}</div>
    <div class="item">❌ Screenshots — need iOS 17 runtime downloaded in Xcode {fail}</div>
    <div class="item">❌ Test reviewer account not created {fail}</div>
    <div class="item">❌ Build not yet attached in App Store Connect {fail}</div>
    <div class="item">❌ Android: Google Play Developer account ($25) not set up {warn}</div>
    """.format(fail=tag("blocked", "fail"), warn=tag("todo", "warn"))

    # ── Section 4: Priority Actions ───────────────────────────────
    priorities = []
    if failed:
        priorities.append("Fix Twitter API — account needs credits or upgrade to a paid tier to resume posting")
    if len(sent_outbox) > 0:
        priorities.append(f"Follow up on {len(sent_outbox)} sent outreach emails — check for replies and respond within 48hrs")
    if pending_outbox:
        priorities.append(f"Send {len(pending_outbox)} pending outreach emails sitting in the outbox")
    priorities.append("Download iOS 17 runtime in Xcode → take App Store screenshots → unblock submission")
    priorities.append("Configure Sign in with Apple in Supabase (Services ID + .p8 key from Apple Developer portal)")
    if researched < total_targets:
        priorities.append(f"Continue outreach research — {total_targets - researched} targets still need profiles built")

    priority_items = "".join(f"<li>{p}</li>" for p in priorities[:5])
    cocktail_section, feature_section = build_intelligence_sections(intel)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{STYLE}</style></head>
<body>
<div class="wrap">

  <div class="header">
    <h1>Weekly PM Report — Spirit Library</h1>
    <p>{today}</p>
  </div>

  {cocktail_section}

  {feature_section}

  <div class="section-head">📱 CMO Agent — Marketing Update</div>
  <div class="body">
    <strong style="font-size:13px;color:#666">PLATFORM STATUS</strong>
    {platform_status}
    {queued_note}
    <br>
    <strong style="font-size:13px;color:#666">RECENT POSTS ({len(published)} published total)</strong>
    {posts_rows}
  </div>

  <div class="section-head">📣 Outreach Dashboard</div>
  <div class="body">
    {target_stats}
    <br>
    <strong style="font-size:13px;color:#666">EMAILS SENT ({len(sent_outbox)})</strong>
    {sent_rows}
    <br>
    <strong style="font-size:13px;color:#666">PENDING IN OUTBOX ({len(pending_outbox)})</strong>
    {pending_rows}
  </div>

  <div class="section-head">🍸 Spirit Library — App Store Status</div>
  <div class="body">
    {app_checklist}
  </div>

  <div class="section-head">🎯 This Week's Priority Actions</div>
  <div class="body">
    <ol class="priority">{priority_items}</ol>
  </div>

  <div style="padding:16px 28px;background:#f8f9fa;font-size:12px;color:#999;text-align:center;">
    Spirit Library PM Report · Generated {today}
  </div>

</div>
</body>
</html>"""

    return html


def send_email(html):
    today = datetime.now().strftime("%B %d, %Y")
    payload = json.dumps({
        "from": "Spirit Library PM <onboarding@resend.dev>",
        "to": [TO_EMAIL],
        "subject": f"Weekly PM Report — Spirit Library — {today}",
        "html": html
    })

    # Write payload to temp file to avoid shell escaping issues
    tmp = Path("/tmp/resend_payload.json")
    tmp.write_text(payload)

    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "https://api.resend.com/emails",
        "-H", f"Authorization: Bearer {RESEND_API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", f"@{tmp}"
    ], capture_output=True, text=True)

    if result.returncode == 0 and '"id"' in result.stdout:
        resp = json.loads(result.stdout)
        print(f"✓ Email sent. ID: {resp.get('id')}")
    else:
        print(f"✗ Send failed: {result.stdout} {result.stderr}")


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Starting PM report...")
    data = gather_data()
    print("Fetching cocktail intelligence...")
    intel = gather_cocktail_intelligence()
    print(f"  Found {len(intel['cocktails'])} cocktail trends, {len(intel['features'])} feature ideas")
    print("Generating report...")
    html = generate_html(data, intel)
    print("Sending email...")
    send_email(html)


if __name__ == "__main__":
    main()
