#!/usr/bin/env python3
"""
email_delivery.py — post-send verification for every outbound email.

Why: sending an email is not the same as it being received. Recipients bounce
(bad address), or auto-reply "out of office". We were reporting sends as
"delivered" without checking. This module closes that loop:

  1. log_send(...)      — every send path appends here (recipient, subject, acct, ts)
  2. verify_recent()    — a few minutes later, scans the SENDING account's inbox
                          for a bounce (mailer-daemon) or OOO/auto-reply tied to
                          that recipient, and classifies each send:
                          delivered_pending | ooo | bounced | autoreply
  3. delivery_status.json + digest block  — surfaces it to the PM email.

Run:  ~/spirit_venv/bin/python ~/cmo-agent/email_delivery.py verify
      (wire into launchd every ~15 min, and/or call after each send.)
"""
import imaplib, email, json, os, re, sys, time
from email.header import make_header, decode_header
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
STATE = ROOT / "state"
STATE.mkdir(exist_ok=True)
SENT_LOG = STATE / "sent_log.jsonl"
STATUS_FILE = STATE / "delivery_status.json"

# account label -> (.env user key, .env app-password key)
ACCOUNTS = {
    "claudesonnet111": ("GMAIL_USER", "GMAIL_APP_PASSWORD"),
    "spiritlibraryapp": ("SPIRIT_GMAIL_USER", "SPIRIT_GMAIL_APP_PASSWORD"),
}

BOUNCE_FROM = re.compile(r"(mailer-daemon|postmaster)@", re.I)
BOUNCE_SUBJ = re.compile(r"(delivery status notification|undeliver|returned mail|failure notice|address not found)", re.I)
OOO_PAT = re.compile(r"(out of office|\bOOO\b|automatic reply|auto-?reply|on vacation|away from|will be out|i am (currently )?(out|away)|back on|返信)", re.I)


def load_env(path=ENV_FILE):
    d = {}
    for line in open(path):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"').strip("'")
    return d


def _login(env, label):
    ukey, pkey = ACCOUNTS[label]
    u, p = env.get(ukey, ""), env.get(pkey, "").replace(" ", "")
    if not u or not p:
        raise RuntimeError(f"{label}: creds missing in .env")
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(u, p)
    return M, u


def send_email(to, subject, body, account="claudesonnet111", cc=None, from_name="Steven Samori"):
    """Send via Gmail SMTP AND log the send so it gets delivery-verified.
    Use this for ALL outbound mail so nothing goes out unchecked."""
    import smtplib, ssl
    from email.mime.text import MIMEText
    from email.utils import formataddr
    env = load_env()
    ukey, pkey = ACCOUNTS[account]
    user, pw = env.get(ukey, ""), env.get(pkey, "").replace(" ", "")
    if not user or not pw:
        raise RuntimeError(f"{account}: creds missing in .env")
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, user))
    msg["To"] = to
    msg["Reply-To"] = user
    rcpts = [to]
    if cc:
        msg["Cc"] = cc
        rcpts.append(cc)
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(user, pw)
        s.sendmail(user, rcpts, msg.as_string())
    log_send(to, subject, account)
    return {"sent": True, "to": to, "account": account}


def log_send(to, subject, account="claudesonnet111", when=None):
    """Append a send record. Every send path should call this."""
    rec = {
        "to": to.lower().strip(),
        "subject": subject,
        "account": account,
        "ts": (when or datetime.now(timezone.utc)).isoformat(),
        "verified": False,
    }
    with open(SENT_LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _read_sent():
    if not SENT_LOG.exists():
        return []
    return [json.loads(l) for l in open(SENT_LOG) if l.strip()]


def _body_of(msg):
    if msg.is_multipart():
        for p in msg.walk():
            if p.get_content_type() == "text/plain":
                try:
                    return p.get_payload(decode=True).decode("utf-8", "ignore")
                except Exception:
                    return ""
    try:
        return msg.get_payload(decode=True).decode("utf-8", "ignore")
    except Exception:
        return ""


def _classify(recipient, since_dt, M):
    """Look for a bounce or auto-reply tied to `recipient` since send time."""
    local = recipient.split("@")[0]
    domain = recipient.split("@")[-1]
    M.select("INBOX", readonly=True)
    # Gmail IMAP date search is day-granular; filter precisely in Python.
    since_str = since_dt.strftime("%d-%b-%Y")
    result = {"status": "delivered_pending", "detail": ""}
    for crit in [b'(FROM "mailer-daemon")', b'(FROM "postmaster")',
                 f'(FROM "{domain}")'.encode(), f'(BODY "{recipient}")'.encode()]:
        typ, data = M.search(None, b'(SINCE "%s")' % since_str.encode(), crit)
        if typ != "OK" or not data[0]:
            continue
        for i in data[0].split()[-10:]:
            typ, md = M.fetch(i, "(RFC822)")
            if typ != "OK":
                continue
            msg = email.message_from_bytes(md[0][1])
            # msg must be newer than the send
            try:
                mdate = email.utils.parsedate_to_datetime(msg.get("Date"))
                if mdate and mdate < since_dt - timedelta(minutes=1):
                    continue
            except Exception:
                pass
            subj = str(make_header(decode_header(msg.get("Subject", ""))))
            frm = msg.get("From", "")
            body = _body_of(msg)
            auto = msg.get("Auto-Submitted", "") or msg.get("X-Autoreply", "")
            blob = f"{subj}\n{body}"
            if BOUNCE_FROM.search(frm) and (recipient in body or local in body or BOUNCE_SUBJ.search(subj)):
                return {"status": "bounced", "detail": subj[:140]}
            if (recipient in frm.lower()) and (OOO_PAT.search(blob) or "auto" in auto.lower()):
                # pull a return date if present
                m = re.search(r"(back|return\w*)[^.\n]{0,40}", blob, re.I)
                return {"status": "ooo", "detail": (m.group(0).strip()[:140] if m else subj[:140])}
    return result


def verify_recent(hours=72):
    env = load_env()
    sent = _read_sent()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    conns = {}
    changed = False
    results = []
    for rec in sent:
        try:
            ts = datetime.fromisoformat(rec["ts"])
        except Exception:
            continue
        if ts < cutoff:
            continue
        acct = rec.get("account", "claudesonnet111")
        if acct not in conns:
            try:
                conns[acct] = _login(env, acct)
            except Exception as e:
                conns[acct] = (None, str(e))
        M, _u = conns[acct]
        if M is None:
            rec.setdefault("status", "unchecked")
            results.append(rec)
            continue
        verdict = _classify(rec["to"], ts, M)
        if verdict["status"] != rec.get("status"):
            changed = True
        rec["status"] = verdict["status"]
        rec["detail"] = verdict["detail"]
        rec["verified"] = verdict["status"] != "delivered_pending"
        results.append(rec)
    for M, _u in conns.values():
        try:
            if M:
                M.logout()
        except Exception:
            pass
    # persist enriched log + a compact status file the digest reads
    with open(SENT_LOG, "w") as f:
        for rec in sent:
            f.write(json.dumps(rec) + "\n")
    summary = {"generated": datetime.now(timezone.utc).isoformat(),
               "window_hours": hours,
               "sends": results}
    STATUS_FILE.write_text(json.dumps(summary, indent=2))
    return summary


def digest_block(html=True):
    """Return an HTML block for the PM digest. Safe if no data."""
    if not STATUS_FILE.exists():
        return ""
    data = json.loads(STATUS_FILE.read_text())
    sends = data.get("sends", [])
    if not sends:
        return ""
    icon = {"bounced": "⛔", "ooo": "🌴", "delivered_pending": "✅", "autoreply": "↩️", "unchecked": "❔"}
    rows = ""
    problems = [s for s in sends if s.get("status") in ("bounced", "ooo")]
    for s in sorted(sends, key=lambda x: x.get("ts", ""), reverse=True)[:12]:
        st = s.get("status", "unchecked")
        rows += (f"<tr><td>{icon.get(st,'')} {st}</td>"
                 f"<td>{s.get('to','')}</td>"
                 f"<td>{(s.get('subject','') or '')[:44]}</td>"
                 f"<td style='color:#888'>{(s.get('detail','') or '')[:60]}</td></tr>")
    head = "📧 Email Delivery"
    if problems:
        head += f" — ⚠ {len(problems)} need attention"
    return (f"<h2>{head}</h2><table cellpadding='4' style='font-size:13px'>"
            f"<tr style='color:#888'><td>Status</td><td>To</td><td>Subject</td><td>Detail</td></tr>"
            f"{rows}</table>")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd == "verify":
        s = verify_recent()
        probs = [x for x in s["sends"] if x.get("status") in ("bounced", "ooo")]
        print(f"Checked {len(s['sends'])} recent send(s). "
              f"{len(probs)} need attention:")
        for x in s["sends"]:
            print(f"  [{x.get('status')}] {x['to']} — {x.get('detail','')[:60]}")
    elif cmd == "block":
        print(digest_block())
    else:
        print("usage: email_delivery.py [verify|block]")
