"""
Scan Gmail inbox for replies to the Westchester outreach and:
- Detect 'unsubscribe' / 'remove' / 'stop' / 'take me off' → add sender to state/optout.txt
- Detect interest signals ('yes', 'interested', 'tell me more', 'call me') → flag in state/hot_replies.json
- Mark processed messages as read so we don't re-process
CAN-SPAM requires honoring opt-outs within 10 days; running this daily covers that.

Usage:
    python3 process_replies.py          # scan unread, update opt-out list
    python3 process_replies.py --dry    # show what it would do
"""
import argparse, imaplib, email, json, re, sys
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parseaddr
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT.parent / ".env"
OPTOUT = ROOT / "state" / "optout.txt"
HOT_REPLIES = ROOT / "state" / "hot_replies.json"
REPLY_LOG = ROOT / "logs" / "replies.csv"

OPTOUT_PATTERNS = [
    r"\bunsubscribe\b", r"\bremove me\b", r"\btake me off\b",
    r"\bstop emailing\b", r"\bdo not email\b", r"\bopt.?out\b",
    r"^\s*stop\s*$", r"^\s*remove\s*$",
]
INTEREST_PATTERNS = [
    r"\binterested\b", r"\btell me more\b", r"\bcall me\b",
    r"\bbook.{0,10}call\b", r"\bschedule\b", r"\blet'?s talk\b",
    r"\byes\b.{0,30}(interested|sounds good|please)",
]


def load_env_pair(key: str) -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE}")
    m = re.search(rf"^{key}\s*=\s*(.+)$", ENV_FILE.read_text(), re.M)
    if not m:
        sys.exit(f"{key} not in .env")
    return m.group(1).strip().strip('"').strip("'")


def decode(s) -> str:
    if not s:
        return ""
    try:
        parts = decode_header(s)
        out = []
        for txt, enc in parts:
            if isinstance(txt, bytes):
                out.append(txt.decode(enc or "utf-8", errors="ignore"))
            else:
                out.append(txt)
        return "".join(out)
    except Exception:
        return str(s)


def extract_body(msg) -> str:
    if msg.is_multipart():
        parts = []
        for p in msg.walk():
            ctype = p.get_content_type()
            disp = str(p.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                try:
                    parts.append(p.get_payload(decode=True).decode(errors="ignore"))
                except Exception:
                    pass
        return "\n".join(parts)
    try:
        return msg.get_payload(decode=True).decode(errors="ignore")
    except Exception:
        return str(msg.get_payload())


def classify(text: str) -> str:
    low = text.lower()
    for p in OPTOUT_PATTERNS:
        if re.search(p, low, re.M):
            return "optout"
    for p in INTEREST_PATTERNS:
        if re.search(p, low):
            return "interest"
    return "other"


def append_optout(address: str) -> bool:
    OPTOUT.parent.mkdir(parents=True, exist_ok=True)
    current = set()
    if OPTOUT.exists():
        current = {line.strip().lower() for line in OPTOUT.read_text().splitlines() if line.strip()}
    addr = address.lower().strip()
    if not addr or addr in current:
        return False
    with open(OPTOUT, "a") as f:
        f.write(addr + "\n")
    return True


def append_hot(entry: dict) -> None:
    HOT_REPLIES.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(HOT_REPLIES.read_text()) if HOT_REPLIES.exists() else []
    data.append(entry)
    HOT_REPLIES.write_text(json.dumps(data, indent=2))


def log_reply(addr: str, subj: str, klass: str) -> None:
    REPLY_LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not REPLY_LOG.exists()
    with open(REPLY_LOG, "a") as f:
        if new:
            f.write("timestamp_utc,email,subject,classification\n")
        subj_escaped = subj.replace('"', "'")
        f.write(f'{datetime.now(timezone.utc).isoformat()},{addr},"{subj_escaped}",{klass}\n')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    user = load_env_pair("GMAIL_USER")
    pw = load_env_pair("GMAIL_APP_PASSWORD")

    print(f"📥 Connecting to {user}...")
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(user, pw)
    M.select("INBOX")

    # Only look at unread messages
    typ, data = M.search(None, "UNSEEN")
    ids = data[0].split()
    print(f"   {len(ids)} unread messages")

    optout_added = 0
    hot_found = 0
    other = 0

    for num in ids:
        typ, msg_data = M.fetch(num, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        from_name, from_addr = parseaddr(msg.get("From", ""))
        subj = decode(msg.get("Subject", ""))
        body = extract_body(msg)
        corpus = f"{subj}\n{body}"
        klass = classify(corpus)

        if klass == "optout":
            if args.dry:
                print(f"  [DRY] OPT-OUT: {from_addr} — {subj[:60]}")
            else:
                if append_optout(from_addr):
                    optout_added += 1
                    print(f"  🚫 OPT-OUT: {from_addr}")
                log_reply(from_addr, subj, "optout")
                M.store(num, "+FLAGS", "\\Seen")
        elif klass == "interest":
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from": from_addr,
                "from_name": from_name,
                "subject": subj,
                "body_preview": body[:400],
            }
            if args.dry:
                print(f"  [DRY] HOT LEAD: {from_addr} — {subj[:60]}")
            else:
                append_hot(entry)
                hot_found += 1
                print(f"  🔥 HOT LEAD: {from_addr} — {subj[:60]}")
                log_reply(from_addr, subj, "interest")
                # Don't mark as read — leave in inbox so Steven actually sees it
        else:
            other += 1
            # Don't mark as read — could be personal email

    M.close()
    M.logout()
    print(f"\n✅ Done. Opt-outs added: {optout_added}. Hot leads: {hot_found}. Other/skipped: {other}.")


if __name__ == "__main__":
    main()
