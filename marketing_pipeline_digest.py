"""
Daily marketing + outreach pipeline digest → stevensamori@gmail.com

Different from the existing PM→CMO→Steven loop:
  - That one goes to claudesonnet111 (ops inbox), focused on inbound replies needing action
  - THIS one goes to stevensamori (personal inbox), focused on the FULL pipeline view
    across all Smore Labs businesses — yesterday's marketing activity at a glance.

Sections:
  1. TL;DR — single sentence
  2. Outbound — cold sends per campaign + per business
  3. Inbound — replies classified by hot/lukewarm/decline/optout
  4. Open conversations — leads in active state
  5. Social — CMO Agent posts (IG/FB)
  6. This week — aggregates
  7. Action items — drafts in folder, decisions needed
"""
import csv, imaplib, json, os, re, smtplib, sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
DIGEST_TO = "stevensamori@gmail.com"

WX_DIR = ROOT / "outreach_westchester"
LOGS = WX_DIR / "logs"
STATE = WX_DIR / "state"
POSTS = ROOT / "posts"


def env(k):
    return re.search(rf"^{k}\s*=\s*(.+)$", ENV_FILE.read_text(), re.M).group(1).strip().strip('"').strip("'")


def parse_iso(s):
    """Parse ISO timestamp. CMO post history stores UTC times without the +00:00
    marker, so naive results get tagged as UTC to make comparisons work."""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def load_csv(p, since=None):
    if not p.exists():
        return []
    rows = list(csv.DictReader(open(p)))
    if since:
        rows = [r for r in rows if (d := parse_iso(r.get("timestamp_utc", ""))) and d >= since]
    return rows


def count_post_history(brand, since):
    p = POSTS / f"{brand}_history.json"
    if not p.exists():
        return []
    try:
        d = json.load(open(p))
        if not isinstance(d, list):
            return []
        out = []
        for entry in d:
            ts = entry.get("posted_at") or entry.get("generated_at") or entry.get("created_at")
            t = parse_iso(ts) if ts else None
            if t and t >= since:
                out.append(entry)
        return out
    except Exception:
        return []


def gmail_drafts_count(user_key, pw_key):
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com")
        M.login(env(user_key), env(pw_key))
        M.select('"[Gmail]/Drafts"')
        _, data = M.search(None, "ALL")
        n = len(data[0].split())
        M.logout()
        return n
    except Exception:
        return 0


def main():
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    today_str = now.astimezone().strftime("%A %B %d, %Y")

    # ─── Outbound: cold sends in last 24h ─────────────────────────
    sl_24h = load_csv(LOGS / "spiritlibrary_emails.csv", yesterday)
    wx_24h = load_csv(LOGS / "westchester_emails.csv", yesterday)
    sl_7d = load_csv(LOGS / "spiritlibrary_emails.csv", week_ago)
    wx_7d = load_csv(LOGS / "westchester_emails.csv", week_ago)

    sl_24h_ok = sum(1 for r in sl_24h if r.get("status") == "sent")
    wx_24h_ok = sum(1 for r in wx_24h if r.get("status") == "sent")
    sl_24h_stages = Counter(r["stage"] for r in sl_24h if r.get("status") == "sent")
    wx_24h_stages = Counter(r["stage"] for r in wx_24h if r.get("status") == "sent")

    # ─── Inbound: replies in last 24h ─────────────────────────────
    replies_24h = load_csv(LOGS / "replies.csv", yesterday)
    by_class = Counter(r["classification"] for r in replies_24h)
    by_inbox = Counter(r["inbox"] for r in replies_24h)
    interesting_24h = [r for r in replies_24h if r["classification"] in ("hot", "lukewarm")]

    # ─── Open conversations / pipeline ────────────────────────────
    hot_state = []
    if (STATE / "hot_replies.json").exists():
        try:
            hot_state = json.load(open(STATE / "hot_replies.json"))
        except Exception:
            pass
    # Suppression list size = active conversation + opt-out total
    optouts = []
    if (STATE / "optout.txt").exists():
        optouts = [l.strip() for l in (STATE / "optout.txt").read_text().splitlines() if l.strip()]

    # ─── Drafts waiting for Steven to send ────────────────────────
    drafts_spirit = gmail_drafts_count("SPIRIT_GMAIL_USER", "SPIRIT_GMAIL_APP_PASSWORD")
    drafts_wx = gmail_drafts_count("GMAIL_USER", "GMAIL_APP_PASSWORD")

    # ─── System health: are the upstream feeds still writing? ─────
    # If a feed goes stale the digest will silently show the same numbers
    # day after day, which is exactly the "PM email never changes" bug.
    def _feed_age_hours(path: Path):
        if not path.exists():
            return None
        return (now.timestamp() - path.stat().st_mtime) / 3600.0

    feeds = [
        ("replies.csv",            LOGS / "replies.csv",                36, "reply triage"),
        ("spiritlibrary_emails.csv", LOGS / "spiritlibrary_emails.csv", 48, "spirit cold sends"),
        ("westchester_emails.csv", LOGS / "westchester_emails.csv",     72, "westchester sends"),
        ("hot_replies.json",       STATE / "hot_replies.json",         336, "active-conversation panel"),
        ("closer_log.json",        STATE / "closer_log.json",          168, "reply-closer agent"),
    ]
    health_rows = []
    for name, path, threshold_h, label in feeds:
        age = _feed_age_hours(path)
        if age is None:
            health_rows.append((name, label, "missing", None))
        elif age > threshold_h:
            health_rows.append((name, label, "stale", age))
    # Did the triage script crash since the last digest? Compare stderr size to
    # a stored baseline so a growing stderr file = new failures.
    triage_stderr = WX_DIR / "logs" / "process_replies.stderr.log"
    baseline_file = STATE / "digest_baselines.json"
    baselines = {}
    if baseline_file.exists():
        try:
            baselines = json.load(open(baseline_file))
        except Exception:
            pass
    triage_crashes = False
    if triage_stderr.exists():
        cur_size = triage_stderr.stat().st_size
        prev_size = baselines.get("triage_stderr_size", 0)
        if cur_size > prev_size + 100:  # 100b buffer for trivial logs
            triage_crashes = True
        baselines["triage_stderr_size"] = cur_size
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            baseline_file.write_text(json.dumps(baselines, indent=2))
        except Exception:
            pass

    # ─── CMO social posts in last 24h ─────────────────────────────
    sl_posts_24h = count_post_history("spirit-library", yesterday)
    pair_posts_24h = count_post_history("pair", yesterday)

    # ─── HTML build ───────────────────────────────────────────────
    style = (
        "body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#1a1a1a;max-width:680px;margin:0 auto;padding:20px;line-height:1.5}"
        "h1{margin:0 0 8px;font-size:22px}h2{margin-top:28px;border-bottom:2px solid #c9a84c;padding-bottom:6px;font-size:16px}"
        ".tldr{background:#fff8e6;border:1px solid #c9a84c;border-radius:6px;padding:14px 16px;margin:14px 0;font-size:15px}"
        ".grid{display:table;width:100%;border-collapse:collapse;margin:8px 0}"
        ".row{display:table-row}"
        ".cell{display:table-cell;padding:8px 12px;border-bottom:1px solid #eee;font-size:14px;vertical-align:top}"
        ".cell.label{color:#666;width:40%}.cell.val{font-weight:600}"
        ".big{font-size:32px;font-weight:700;color:#c9a84c;line-height:1}"
        ".muted{color:#888;font-size:12px}"
        ".action{background:#fdecec;border-left:4px solid #b00020;padding:12px 16px;margin:12px 0;border-radius:4px}"
        "table{border-collapse:collapse;width:100%;margin:8px 0}"
        "th,td{padding:6px 10px;text-align:left;border-bottom:1px solid #eee;font-size:13px}"
        "th{background:#fafafa;font-weight:600}"
        ".biz{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;background:#eef;color:#005}"
        "hr{border:none;border-top:1px solid #eee;margin:24px 0}"
    )

    lines = [f"<style>{style}</style>"]
    lines.append(f"<h1>📊 Marketing & Outreach Daily — {today_str}</h1>")
    lines.append('<div class="muted">Across Spirit Library · Westchester AI Consulting · CMO posting · all active client work</div>')

    # ─── TL;DR ─────────────────────────────────────────────────────
    tldr_parts = []
    total_out = sl_24h_ok + wx_24h_ok
    if total_out: tldr_parts.append(f"sent <b>{total_out}</b> cold emails")
    total_in = len(replies_24h)
    if total_in: tldr_parts.append(f"<b>{total_in}</b> replies came in")
    total_interesting = len(interesting_24h)
    if total_interesting: tldr_parts.append(f"<b>{total_interesting}</b> looked interested 🔥")
    total_posts = len(sl_posts_24h) + len(pair_posts_24h)
    if total_posts: tldr_parts.append(f"posted <b>{total_posts}</b> times to social")
    open_drafts = drafts_spirit + drafts_wx
    if open_drafts: tldr_parts.append(f"<b>{open_drafts}</b> drafts waiting for you to send")
    tldr = "Yesterday: " + (", ".join(tldr_parts) if tldr_parts else "no new outbound or inbound activity") + "."
    lines.append(f'<div class="tldr">⚡ <b>TL;DR:</b> {tldr}</div>')

    # ─── SYSTEM HEALTH (only renders when something is broken) ────
    # Surfaces upstream feed staleness BEFORE Steven notices the digest
    # looks identical to yesterday's — answers the "why is content the
    # same every day" failure mode.
    if health_rows or triage_crashes:
        lines.append('<div class="action" style="background:#fff4e0;border-left-color:#c9a84c"><b>⚠ Feed health — some upstream data is stale</b><ul>')
        if triage_crashes:
            lines.append('<li><b>Reply triage crashed</b> since last digest — check <code>outreach_westchester/logs/process_replies.stderr.log</code>. Replies are not being classified.</li>')
        for name, label, status, age in health_rows:
            if status == "missing":
                lines.append(f"<li><b>{name}</b> is missing — <i>{label}</i> never wrote any data.</li>")
            else:
                days = age / 24.0
                lines.append(f"<li><b>{name}</b> hasn't updated in <b>{days:.1f} days</b> — <i>{label}</i> is likely broken. Digest numbers from this source will keep repeating until you fix it.</li>")
        lines.append("</ul></div>")

    # ─── NEEDS HANDOFF: hot/lukewarm aging without a Steven reply ─
    # The whole point of this digest is to surface stuck conversations
    # before the lead notices Steven hasn't replied.
    drafted_keys_file = WX_DIR / "state" / "drafts_created.json"
    drafted_keys = set()
    if drafted_keys_file.exists():
        try:
            drafted_keys = set(json.load(open(drafted_keys_file)))
        except Exception:
            pass

    handoff_rows = []
    seen_handoff = set()
    for h in sorted(hot_state, key=lambda x: x.get("timestamp", ""), reverse=True):
        if h.get("classification") not in ("hot", "lukewarm"):
            continue
        addr = h.get("from", "").lower()
        if addr in seen_handoff:
            continue
        seen_handoff.add(addr)
        try:
            age_d = (datetime.now(timezone.utc) - datetime.fromisoformat(h.get("timestamp", ""))).days
        except Exception:
            continue
        mid = h.get("message_id", "")
        inbox_h = h.get("inbox", "")
        dk = f"{inbox_h}|{mid}" if mid else f"{inbox_h}|{addr}|{h.get('subject','')[:50].lower()}"
        has_draft = dk in drafted_keys
        if age_d >= 3 and not has_draft:
            handoff_rows.append((h, age_d, "no draft after 3+ days"))
        elif age_d >= 7 and has_draft:
            handoff_rows.append((h, age_d, "drafted but still open after a week"))

    if handoff_rows:
        lines.append('<div class="action"><b>🚨 Needs your handoff — leads waiting on YOU</b><ol>')
        for h, age_d, reason in handoff_rows[:8]:
            klass = h.get("classification", "?")
            emoji = {"hot": "🔥", "lukewarm": "🟡"}.get(klass, "")
            lines.append(
                f"<li>{emoji} <b>{h.get('from_name','')[:30] or addr}</b> "
                f"(<code style='font-size:11px'>{h['from'][:40]}</code>) — "
                f"<b style='color:#b00020'>{age_d}d ago</b>, {reason}. "
                f"Subject: <i>{h.get('subject','')[:60]}</i></li>"
            )
        lines.append("</ol></div>")

    # ─── ACTION ITEMS (top of email so it's the first thing he sees) ───
    actions = []
    if open_drafts:
        actions.append(f"<b>{open_drafts}</b> draft(s) waiting in Gmail Drafts (spirit: {drafts_spirit} · westchester: {drafts_wx}) — open and send")
    if interesting_24h:
        actions.append(f"<b>{len(interesting_24h)}</b> hot/lukewarm replies came in yesterday — see Outreach Reply Triage email to claudesonnet111@gmail.com for the auto-drafted responses")
    if actions:
        lines.append('<div class="action"><b>📋 Today\'s priorities</b><ol>')
        for a in actions: lines.append(f"<li>{a}</li>")
        lines.append("</ol></div>")

    # ─── Outbound ─────────────────────────────────────────────────
    lines.append("<h2>📤 Outbound (last 24h)</h2>")
    lines.append("<table>")
    lines.append("<tr><th>Campaign</th><th>Sent</th><th>Cold</th><th>Followup</th><th>7-day total</th></tr>")
    lines.append(f"<tr><td><span class='biz'>Spirit Library</span> bars/restaurants/brands</td><td><b>{sl_24h_ok}</b></td><td>{sl_24h_stages.get('cold',0)}</td><td>{sl_24h_stages.get('followup',0)}</td><td>{sum(1 for r in sl_7d if r.get('status')=='sent')}</td></tr>")
    lines.append(f"<tr><td><span class='biz'>Westchester</span> AI consulting</td><td><b>{wx_24h_ok}</b></td><td>{wx_24h_stages.get('cold',0)}</td><td>{wx_24h_stages.get('followup',0)}</td><td>{sum(1 for r in wx_7d if r.get('status')=='sent')}</td></tr>")
    lines.append("</table>")

    # ─── Inbound ──────────────────────────────────────────────────
    lines.append("<h2>📥 Inbound (last 24h)</h2>")
    if replies_24h:
        lines.append("<table><tr><th>Class</th><th>Count</th><th>What it means</th></tr>")
        rows_def = [
            ("hot", "🔥", "Wants to talk / needs your reply"),
            ("lukewarm", "🟡", "Discovery questions / soft interest"),
            ("decline", "🚪", "Polite no — auto-suppressed, no reply needed"),
            ("optout", "🚫", "Hard stop — auto-suppressed"),
            ("auto-reply", "🤖", "OOO / bounce / mailer-daemon"),
            ("not-a-reply", "⚪", "Newsletters / unrelated"),
            ("spam", "🗑", "Junk"),
        ]
        for k, emoji, desc in rows_def:
            n = by_class.get(k, 0)
            if n:
                lines.append(f"<tr><td>{emoji} {k}</td><td><b>{n}</b></td><td class='muted'>{desc}</td></tr>")
        lines.append("</table>")
    else:
        lines.append("<p class='muted'>No new replies yesterday.</p>")

    if interesting_24h:
        lines.append("<h3>🔥 Interesting replies (full digest in claudesonnet111 inbox)</h3><ul>")
        for r in interesting_24h[:10]:
            lines.append(f"<li><b>[{r['classification']}]</b> {r['inbox']} · <code>{r['email']}</code> — <i>{r['subject'][:80]}</i></li>")
        lines.append("</ul>")

    # ─── Pipeline ─────────────────────────────────────────────────
    lines.append("<h2>🤝 Active conversations</h2>")
    # Only show hot + lukewarm (declines are closed). Sort newest first. Cap at 30 days.
    active = [
        h for h in hot_state
        if h.get("classification") in ("hot", "lukewarm")
    ]
    # Dedupe by email — keep latest entry per address
    seen_emails = {}
    for h in sorted(active, key=lambda x: x.get("timestamp", ""), reverse=True):
        addr = h.get("from", "").lower()
        if addr not in seen_emails:
            seen_emails[addr] = h
    active = list(seen_emails.values())
    # Sort hot first, then lukewarm, then by recency
    active.sort(key=lambda x: (0 if x.get("classification") == "hot" else 1, x.get("timestamp", "")))

    drafted_keys_file = WX_DIR / "state" / "drafts_created.json"
    drafted_keys = set()
    if drafted_keys_file.exists():
        try:
            drafted_keys = set(json.load(open(drafted_keys_file)))
        except Exception:
            pass

    if active:
        lines.append(f"<p><b>{len(active)}</b> open &nbsp;·&nbsp; {len(optouts)} suppressed from cold pipeline</p>")
        lines.append("<table><tr><th>Status</th><th>Lead</th><th>Days ago</th><th>Draft</th><th>Subject</th></tr>")
        for h in active:
            klass = h.get("classification", "?")
            emoji = {"hot": "🔥", "lukewarm": "🟡"}.get(klass, "")
            ts = h.get("timestamp", "")
            try:
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).days
            except Exception:
                age_days = "?"
            age_str = f"<b style='color:#b00020'>{age_days}d</b>" if isinstance(age_days, int) and age_days >= 7 else f"{age_days}d"
            # Check if a draft was created for this lead
            mid = h.get("message_id", "")
            inbox = h.get("inbox", "")
            dk = f"{inbox}|{mid}" if mid else f"{inbox}|{h.get('from','').lower()}|{h.get('subject','')[:50].lower()}"
            draft_badge = "✓ drafted" if dk in drafted_keys else "<span style='color:#b00020'>⚠ no draft</span>"
            lines.append(
                f"<tr><td>{emoji} {klass}</td>"
                f"<td>{h.get('from_name','')[:22]}<br><code style='font-size:11px'>{h['from'][:32]}</code></td>"
                f"<td style='text-align:center'>{age_str}</td>"
                f"<td style='font-size:12px'>{draft_badge}</td>"
                f"<td style='font-size:12px'>{h.get('subject','')[:50]}</td></tr>"
            )
        lines.append("</table>")
    else:
        lines.append("<p class='muted'>No open conversations.</p>")

    # ─── New outreach agents (shipped 2026-05-21) ─────────────────
    # Press / influencer / distillery / bev-director / reply-closer / vertical playbook
    OUTREACH_DIR = Path.home() / "cmo-agent" / "outreach"
    today_iso = datetime.now().strftime("%Y-%m-%d")

    def _agent_counts(path: Path):
        if not path.exists():
            return 0, 0
        try:
            items = json.load(open(path))
        except Exception:
            return 0, 0
        total = len(items)
        today = sum(1 for x in items if today_iso in (x.get("drafted_at") or x.get("queued_at") or x.get("processed_at") or ""))
        return total, today

    press_total, press_today = _agent_counts(OUTREACH_DIR / "press_drafts.json")
    infl_total, infl_today = _agent_counts(OUTREACH_DIR / "influencer_drafts.json")
    distil_total, distil_today = _agent_counts(OUTREACH_DIR / "distillery_outbox.json")
    bevdir_total, bevdir_today = _agent_counts(OUTREACH_DIR / "bevdir_outbox.json")
    dm_total, _ = _agent_counts(OUTREACH_DIR / "dm_queue.json")
    closer_total, closer_today = _agent_counts(WX_DIR / "state" / "closer_log.json")

    has_any_agent_activity = any([press_total, infl_total, distil_total, bevdir_total, dm_total, closer_total])
    if has_any_agent_activity:
        lines.append("<h2>🤖 New outreach agents</h2>")
        lines.append("<table>")
        lines.append("<tr><th>Pipeline</th><th>Pending</th><th>+Today</th><th>Path</th></tr>")
        rows = [
            ("Press drafts (Apollo)",      press_total,  press_today,  "outreach/press_drafts.json"),
            ("Influencer email drafts",    infl_total,   infl_today,   "outreach/influencer_drafts.json"),
            ("Influencer IG DMs queued",   dm_total,     0,            "outreach/dm_queue.json"),
            ("Distillery drafts (KOVAL)",  distil_total, distil_today, "outreach/distillery_outbox.json"),
            ("Bev Director drafts",        bevdir_total, bevdir_today, "outreach/bevdir_outbox.json"),
            ("Reply-closer artifacts",     closer_total, closer_today, "state/closer_log.json"),
        ]
        for label, total, today_n, path in rows:
            today_cell = f"<b style='color:#0a6'>+{today_n}</b>" if today_n else "<span class='muted'>—</span>"
            lines.append(f"<tr><td>{label}</td><td><b>{total}</b></td><td>{today_cell}</td><td class='muted' style='font-size:11px'>{path}</td></tr>")
        lines.append("</table>")
        # Vertical playbook status
        vertical_dir = OUTREACH_DIR / "verticals"
        if vertical_dir.exists():
            v_rows = []
            for vd in sorted(vertical_dir.iterdir()):
                if not vd.is_dir():
                    continue
                leads = vd / "leads.csv"
                seeds = vd / "canary_seeds.json"
                canary = vd / "canary_results.json"
                phase = "scoping"
                lead_n = 0
                if leads.exists():
                    lead_n = sum(1 for _ in leads.open()) - 1
                    phase = "lead-list ready" if seeds.exists() else "scoping"
                if canary.exists():
                    phase = "canary running"
                v_rows.append(f"<li><b>{vd.name}</b>: {phase} ({lead_n} leads)</li>")
            if v_rows:
                lines.append("<p style='margin-top:10px'><b>Vertical playbook</b></p><ul>" + "".join(v_rows) + "</ul>")
        lines.append("<p class='muted' style='font-size:12px'>Trigger more: <code>~/cmo-agent/morning_pitch_sequence.sh [N]</code> · drafts only — review + send</p>")

    # ─── Social ───────────────────────────────────────────────────
    lines.append("<h2>📱 Social posts (last 24h)</h2>")
    lines.append(f"<p>Spirit Library IG/FB: <b>{len(sl_posts_24h)}</b> &nbsp; · &nbsp; Pair: <b>{len(pair_posts_24h)}</b></p>")
    if sl_posts_24h:
        lines.append("<table><tr><th>Type</th><th>Caption</th></tr>")
        for p in sl_posts_24h[-5:]:
            cap = (p.get("caption", "") or "")[:80].replace("\n", " ")
            lines.append(f"<tr><td>{p.get('post_type','?')}</td><td>{cap}…</td></tr>")
        lines.append("</table>")

    # ─── Footer ───────────────────────────────────────────────────
    lines.append("<hr>")
    lines.append('<p class="muted">🤖 Generated by <code>~/cmo-agent/marketing_pipeline_digest.py</code><br>')
    lines.append("⏰ launchd: <code>com.smorelabs.marketing-digest</code> · daily 07:00 ET<br>")
    lines.append("This digest goes to <b>stevensamori@gmail.com</b> only. Reply triage, daily debrief, and ops alerts continue to <b>claudesonnet111@gmail.com</b>.</p>")

    body_html = "\n".join(lines)

    # ─── Send ─────────────────────────────────────────────────────
    user, pw = env("GMAIL_USER"), env("GMAIL_APP_PASSWORD")
    msg = MIMEMultipart("alternative")
    headline = f"📊 Marketing daily — {sl_24h_ok+wx_24h_ok} sent, {len(interesting_24h)} hot, {open_drafts} drafts waiting"
    msg["Subject"] = headline
    msg["From"] = f"Marketing Pipeline <{user}>"
    msg["To"] = DIGEST_TO
    msg.attach(MIMEText(body_html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.sendmail(user, [DIGEST_TO], msg.as_string())
    print(f"📨 Sent to {DIGEST_TO} — {headline}")


if __name__ == "__main__":
    main()
