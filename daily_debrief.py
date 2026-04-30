#!/usr/bin/env python3
"""
Daily Debrief — Smore Labs
Scans git logs, post history, outreach state, Obsidian notes, and app status
to generate a "what got done today" + "punch list" email.
Sent daily at 9pm via Resend.
"""

import json
import csv
import os
import subprocess
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path

def _load_env_from_dotenv() -> None:
    env_path = Path(__file__).parent / ".env"
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

HOME = Path.home()
CMO = HOME / "cmo-agent"
DOCS = HOME / "Documents"
VAULT = DOCS / "Smore Labs ecosystem"

PROJECTS = {
    "Spirit Library": DOCS / "spiritlibrary-mobile",
    "Pair": DOCS / "pair-mobile",
    "Drybar": DOCS / "drybar-mobile",
    "CMO Agent": CMO,
    "CMO Agent (docs)": DOCS / "cmo-agent",
}

STYLE = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a1a; margin: 0; padding: 20px; color: #d4d4d4; }
.wrap { max-width: 680px; margin: auto; background: #242424; border-radius: 8px; overflow: hidden; border: 1px solid #333; }
.header { background: #2a2a2a; color: #e0e0e0; padding: 28px; }
.header h1 { margin: 0; font-size: 22px; color: #e8e8e8; }
.header .date { margin: 6px 0 0; opacity: 0.5; font-size: 13px; }
.header .tagline { margin: 8px 0 0; font-size: 14px; opacity: 0.7; }
.section { border-bottom: 1px solid #333; }
.section:last-child { border-bottom: none; }
.section-head { background: #2e2e2e; color: #a0a0a0; padding: 12px 24px; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.body { padding: 16px 24px; }
.item { padding: 8px 0; border-bottom: 1px solid #303030; font-size: 14px; line-height: 1.5; color: #c0c0c0; }
.item:last-child { border-bottom: none; }
.done { color: #6abf69; }
.todo { color: #c4a35a; }
.blocked { color: #c75c5c; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.tag-done { background: #2a3a2a; color: #6abf69; }
.tag-todo { background: #3a3328; color: #c4a35a; }
.tag-blocked { background: #3a2828; color: #c75c5c; }
.tag-info { background: #283038; color: #7a9ab5; }
.stat-row { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0; }
.stat { background: #2e2e2e; border-radius: 8px; padding: 12px 16px; text-align: center; flex: 1; min-width: 80px; border: 1px solid #383838; }
.stat .num { font-size: 22px; font-weight: 700; color: #e0e0e0; }
.stat .lbl { font-size: 11px; color: #808080; margin-top: 4px; }
.punch { counter-reset: item; padding: 0; list-style: none; margin: 0; }
.punch li { counter-increment: item; padding: 10px 0 10px 40px; border-bottom: 1px solid #303030; font-size: 14px; position: relative; line-height: 1.5; color: #c0c0c0; }
.punch li:before { content: counter(item); position: absolute; left: 0; top: 10px; background: #505050; color: #e0e0e0; width: 24px; height: 24px; border-radius: 50%; text-align: center; line-height: 24px; font-size: 12px; font-weight: 700; }
.punch li:last-child { border-bottom: none; }
.punch li .owner { font-size: 11px; color: #707070; display: block; margin-top: 2px; }
.footer { padding: 16px 24px; text-align: center; font-size: 11px; color: #505050; }
"""


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return []


def git_log_today(repo_path):
    """Get today's git commits for a repo."""
    if not (repo_path / ".git").exists():
        return []
    today = datetime.now().strftime("%Y-%m-%d")
    result = subprocess.run(
        ["git", "-C", str(repo_path), "log", f"--since={today} 00:00", "--format=%h|%s|%an|%ai"],
        capture_output=True, text=True
    )
    commits = []
    for line in result.stdout.strip().split("\n"):
        if "|" in line:
            parts = line.split("|", 3)
            if len(parts) >= 2:
                commits.append({"hash": parts[0], "msg": parts[1], "author": parts[2] if len(parts) > 2 else "", "date": parts[3] if len(parts) > 3 else ""})
    return commits


def get_bar_outreach_stats():
    """Read bar email campaign state."""
    state_file = CMO / "outreach/state/bar_email_state.json"
    if not state_file.exists():
        return {"total": 0, "cold": 0, "f1": 0, "f2": 0, "today": 0}
    state = json.loads(state_file.read_text())
    sent = state.get("sent", {})
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_count = state.get("daily_counts", {}).get(today_str, 0)
    return {
        "total": len(sent),
        "cold": sum(1 for v in sent.values() if "cold" in v),
        "f1": sum(1 for v in sent.values() if "followup_1" in v),
        "f2": sum(1 for v in sent.values() if "followup_2" in v),
        "today": today_count,
    }


def get_bar_email_log_today():
    """Get today's email sends from CSV log."""
    log_file = CMO / "outreach/logs/bar_emails.csv"
    if not log_file.exists():
        return []
    today = datetime.now().strftime("%Y-%m-%d")
    sends = []
    with open(log_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('timestamp', '').startswith(today):
                sends.append(row)
    return sends


def get_post_history_today():
    """Get today's social media posts."""
    history = read_json(CMO / "posts/spirit-library_history.json")
    today = datetime.now().strftime("%Y-%m-%d")
    return [p for p in history if (p.get("published_at") or p.get("created_at") or "").startswith(today)]


def count_mocktails():
    """Count total mocktail recipes."""
    total = 0
    for f in (DOCS / "spiritlibrary-mobile/data").glob("mocktails*.ts"):
        try:
            total += f.read_text().count("id:")
        except:
            pass
    return total


def get_contacts_total():
    """Get total bar contacts across all files."""
    total = 0
    for f in ["bars_nationwide.json", "bars_nationwide_enriched.json", "bars_apollo_imported.json", "bars_apollo_discovery.json"]:
        path = CMO / "outreach/targets" / f
        if path.exists():
            try:
                total += len(json.loads(path.read_text()))
            except:
                pass
    return total if total > 0 else 255


def get_obsidian_master_indexes():
    """Read punch list items from Obsidian Master Indexes."""
    items = []
    for idx_path in VAULT.rglob("🧠 Master Index.md"):
        try:
            text = idx_path.read_text()
            project = idx_path.parent.name
            # Find unchecked items
            for match in re.finditer(r"- \[ \] (.+)", text):
                items.append({"project": project, "task": match.group(1).strip()})
        except:
            pass
    return items


def build_accomplishments_section(commits_by_project, posts_today, emails_today, outreach_stats):
    """Build the 'What Got Done Today' section."""
    rows = ""

    # Git commits
    for project, commits in commits_by_project.items():
        for c in commits:
            rows += f'<div class="item"><span class="done">✓</span> <strong>{project}</strong>: {c["msg"]} <span class="tag tag-done">shipped</span></div>'

    # Social posts
    for p in posts_today:
        platform = p.get("platform", "").capitalize()
        caption = (p.get("caption") or "")[:80]
        rows += f'<div class="item"><span class="done">✓</span> <strong>CMO</strong>: Posted to {platform} — {caption} <span class="tag tag-done">published</span></div>'

    # Outreach emails
    if emails_today:
        cold = sum(1 for e in emails_today if e.get("stage") == "cold")
        f1 = sum(1 for e in emails_today if e.get("stage") == "followup_1")
        f2 = sum(1 for e in emails_today if e.get("stage") == "followup_2")
        parts = []
        if cold: parts.append(f"{cold} cold")
        if f1: parts.append(f"{f1} follow-up #1")
        if f2: parts.append(f"{f2} follow-up #2")
        rows += f'<div class="item"><span class="done">✓</span> <strong>Bar Outreach</strong>: Sent {", ".join(parts)} emails ({len(emails_today)} total today) <span class="tag tag-done">sent</span></div>'

    if not rows:
        rows = '<div class="item" style="color:#484f58;">Quiet day — no commits, posts, or emails logged.</div>'

    return rows


def build_punch_list(obsidian_tasks, outreach_stats):
    """Build the punch list with items Steven needs to do."""
    items = []

    # Dynamic items based on current state
    if outreach_stats["total"] < 255:
        items.append(("Bar Outreach", f"Campaign in progress: {outreach_stats['total']}/255 contacts emailed. Auto-running via n8n.", False))

    # Apollo CSV export
    apollo_dir = CMO / "outreach/apollo_exports"
    if not list(apollo_dir.glob("*.csv")) if apollo_dir.exists() else True:
        items.append(("Bar Outreach", "Export Apollo CSV batches (5 searches) → save to ~/cmo-agent/outreach/apollo_exports/ → run apollo_import_csv.py", True))

    # Obsidian punch list items (things that need Steven)
    for task in obsidian_tasks:
        items.append((task["project"], task["task"], True))

    # Standing items
    items.append(("All", "Check Gmail for outreach replies — respond within 24hrs", True))

    punch_html = ""
    for project, task, needs_steven in items:
        owner = "Needs you" if needs_steven else "Automated"
        owner_class = "todo" if needs_steven else "done"
        tag_class = "tag-todo" if needs_steven else "tag-info"
        punch_html += f'<li><strong>{project}</strong>: {task}<span class="owner {owner_class}">{owner}</span></li>'

    return punch_html


def generate_ai_summary(accomplishments_text, punch_items_text):
    """Use Claude to generate a one-paragraph debrief summary."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": f"""Write a 2-3 sentence daily debrief summary for the founder of Smore Labs (Spirit Library cocktail app, CMO Agent, Pair wine app).

Today's accomplishments:
{accomplishments_text}

Open punch list:
{punch_items_text}

Be direct, casual, no fluff. Mention the most impactful thing done today and the most urgent punch list item. Sign off with a motivational one-liner."""}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"Debrief generation failed: {e}"


def generate_html():
    today = datetime.now()
    today_str = today.strftime("%A, %B %d, %Y")

    # Gather all data
    commits_by_project = {}
    for name, path in PROJECTS.items():
        commits = git_log_today(path)
        if commits:
            commits_by_project[name] = commits

    posts_today = get_post_history_today()
    emails_today = get_bar_email_log_today()
    outreach_stats = get_bar_outreach_stats()
    mocktail_count = count_mocktails()
    contacts_total = get_contacts_total()
    obsidian_tasks = get_obsidian_master_indexes()

    # Build sections
    accomplishments = build_accomplishments_section(commits_by_project, posts_today, emails_today, outreach_stats)
    punch_list = build_punch_list(obsidian_tasks, outreach_stats)

    # AI summary
    acc_text = f"{sum(len(c) for c in commits_by_project.values())} commits across {len(commits_by_project)} projects, {len(posts_today)} social posts, {len(emails_today)} outreach emails"
    punch_text = f"{len(obsidian_tasks)} open Obsidian tasks, bar outreach at {outreach_stats['total']}/255"
    summary = generate_ai_summary(acc_text, punch_text)

    total_commits = sum(len(c) for c in commits_by_project.values())

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{STYLE}</style></head>
<body>
<div class="wrap">

  <div class="header">
    <h1>Daily Debrief — Smore Labs</h1>
    <div class="date">{today_str}</div>
    <div class="tagline">{summary}</div>
  </div>

  <div class="section">
    <div class="section-head">Today's Numbers</div>
    <div class="body">
      <div class="stat-row">
        <div class="stat"><div class="num">{total_commits}</div><div class="lbl">Commits</div></div>
        <div class="stat"><div class="num">{len(posts_today)}</div><div class="lbl">Posts</div></div>
        <div class="stat"><div class="num">{len(emails_today)}</div><div class="lbl">Emails Sent</div></div>
        <div class="stat"><div class="num">{outreach_stats['total']}/255</div><div class="lbl">Bar Campaign</div></div>
        <div class="stat"><div class="num">{mocktail_count}</div><div class="lbl">Mocktails</div></div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-head">What Got Done Today</div>
    <div class="body">{accomplishments}</div>
  </div>

  <div class="section">
    <div class="section-head">Bar Outreach Campaign</div>
    <div class="body">
      <div class="stat-row">
        <div class="stat"><div class="num">{outreach_stats['cold']}</div><div class="lbl">Cold Sent</div></div>
        <div class="stat"><div class="num">{outreach_stats['f1']}</div><div class="lbl">Follow-up #1</div></div>
        <div class="stat"><div class="num">{outreach_stats['f2']}</div><div class="lbl">Follow-up #2</div></div>
        <div class="stat"><div class="num">{contacts_total}</div><div class="lbl">Total Contacts</div></div>
        <div class="stat"><div class="num">{outreach_stats['today']}</div><div class="lbl">Sent Today</div></div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-head">Punch List — What Still Needs You</div>
    <div class="body">
      <ol class="punch">{punch_list}</ol>
    </div>
  </div>

  <div class="footer">
    Smore Labs Daily Debrief · {today_str} · Auto-generated
  </div>

</div>
</body>
</html>"""

    return html


def send_email(html):
    today = datetime.now().strftime("%B %d")
    payload = json.dumps({
        "from": "Smore Labs <onboarding@resend.dev>",
        "to": [TO_EMAIL],
        "subject": f"Daily Debrief — {today}",
        "html": html
    })

    tmp = Path("/tmp/debrief_payload.json")
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
        print(f"✓ Debrief sent. ID: {resp.get('id')}")
    else:
        print(f"✗ Send failed: {result.stdout} {result.stderr}")


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Generating daily debrief...")
    html = generate_html()
    # Save locally for preview
    Path("/tmp/daily_debrief.html").write_text(html)
    print(f"  Preview: /tmp/daily_debrief.html")
    print("Sending email...")
    send_email(html)


if __name__ == "__main__":
    main()
