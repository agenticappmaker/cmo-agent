"""
Generate and send highly personalized emails to marketing executives.
References their specific role, recent initiatives, and LinkedIn activity.
"""
import anthropic, os, json, re, smtplib, time
from datetime import datetime
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

OUTREACH_DIR = Path('outreach')
EXEC_CACHE = OUTREACH_DIR / 'executive_cache.json'
EXEC_OUTBOX = OUTREACH_DIR / 'exec_outbox.json'
EXEC_SENT_LOG = OUTREACH_DIR / 'exec_sent_log.json'

FROM_NAME = "Steven Samori | Spirit Library"

APP_PITCH = """Spirit Library iOS app — 1,700+ cocktail recipes:
• MY BAR: search by ingredient + flavor profile (Smoky, Citrus, Bitter, Floral, etc.)
• CREATE YOUR OWN: custom recipe builder, save + share
• SHARE MENUS: curate and share full cocktail menus
• COCKTAIL OF THE DAY: daily sponsored spotlight
• SHOPPING CART (coming soon): buy ingredients via Instacart/DoorDash/Uber Eats"""

def load_json(path):
    return json.loads(path.read_text()) if path.exists() else []

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def generate_exec_email(exec_data: dict, original_pitch: dict) -> dict:
    name = exec_data.get('exec_name', '')
    title = exec_data.get('exec_title', '')
    company = exec_data.get('company', '')
    initiative = exec_data.get('recent_initiative', '')
    category = exec_data.get('company_category', '')
    original_hook = original_pitch.get('key_hook', '')

    first_name = name.split()[0] if name and name != 'unknown' else 'there'

    prompt = f"""Write a personalized partnership email directly to {name}, {title} at {company}.

{APP_PITCH}

ABOUT THIS PERSON:
- Name: {name}
- Title: {title}
- Company: {company}
- Recent initiative they led: {initiative}
- Original company pitch hook: {original_hook}

Write an email that:
1. Opens by addressing {first_name} directly and referencing their SPECIFIC recent initiative ("{initiative}") — one sentence showing you know their work
2. Introduces Spirit Library in 2 sentences max, tied to what THEY specifically work on
3. Proposes one concrete partnership idea relevant to their role and what they've been doing
4. Asks for 15 minutes — their call, their agenda
5. Total: 150-220 words. Tight. Executive-level. No fluff.
6. Sign: Steven Samori, Founder, Spirit Library

Respond ONLY as JSON:
{{"subject": "...", "body": "...", "hook_used": "the specific thing referenced about their work"}}"""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"): text = text[4:].strip()
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON: {text[:200]}")

def send_email(to_email, subject, body):
    gmail_user = os.environ['GMAIL_USER'].strip()
    gmail_pwd = os.environ['GMAIL_APP_PASSWORD'].strip()
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{FROM_NAME} <{gmail_user}>"
    msg['To'] = to_email
    msg['Reply-To'] = gmail_user
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(gmail_user, gmail_pwd)
        s.sendmail(gmail_user, to_email, msg.as_string())

def run(dry_run=False, delay=12):
    cache = json.loads(EXEC_CACHE.read_text()) if EXEC_CACHE.exists() else {}
    outbox_data = json.loads(Path('outreach/outbox.json').read_text())
    original_pitches = {e['name']: e for e in outbox_data}

    exec_outbox = load_json(EXEC_OUTBOX)
    exec_sent_log = load_json(EXEC_SENT_LOG)
    already_sent = {e['company'] for e in exec_sent_log}

    # Only process execs we found with an email
    targets = [
        v for v in cache.values()
        if 'error' not in v
        and v.get('exec_email')
        and v.get('exec_name') not in (None, 'unknown', '')
        and v['company'] not in already_sent
    ]

    no_email = [v for v in cache.values() if 'error' not in v and not v.get('exec_email')]
    errors = [v for v in cache.values() if 'error' in v]

    print(f"\n📊 Executive outreach summary:")
    print(f"   Ready to email:  {len(targets)}")
    print(f"   No email found:  {len(no_email)}")
    print(f"   Research errors: {len(errors)}")
    print(f"   Already sent:    {len(already_sent)}")

    if no_email:
        print(f"\n⚠️  No email found for:")
        for v in no_email:
            print(f"   - {v.get('exec_name','?')} @ {v['company']}")

    if not targets:
        print("\nNothing to send.")
        return

    print(f"\n{'🧪 DRY RUN — ' if dry_run else ''}{'Drafting + sending' if not dry_run else 'Would send'} {len(targets)} executive emails...\n")

    sent = 0
    failed = 0

    for i, exec_data in enumerate(targets, 1):
        company = exec_data['company']
        exec_name = exec_data.get('exec_name', '')
        exec_email = exec_data.get('exec_email', '')
        original = original_pitches.get(company, {})

        print(f"[{i}/{len(targets)}] {exec_name} — {exec_data.get('exec_title','')} @ {company}")
        print(f"  Email: {exec_email}")

        try:
            pitch = generate_exec_email(exec_data, original)
            print(f"  Subject: {pitch['subject']}")
            print(f"  Hook: {pitch.get('hook_used','')[:80]}")

            entry = {
                "company": company,
                "exec_name": exec_name,
                "exec_title": exec_data.get('exec_title',''),
                "exec_email": exec_email,
                "subject": pitch['subject'],
                "body": pitch['body'],
                "hook_used": pitch.get('hook_used',''),
                "sent_at": None
            }

            if dry_run:
                print(f"\n--- PREVIEW ---\n{pitch['body'][:300]}...\n--- END ---\n")
            else:
                send_email(exec_email, pitch['subject'], pitch['body'])
                entry['sent_at'] = datetime.utcnow().isoformat()
                exec_sent_log.append(entry)
                save_json(EXEC_SENT_LOG, exec_sent_log)
                print(f"  ✓ Sent!")
                sent += 1
                if i < len(targets):
                    print(f"  ⏳ {delay}s...")
                    time.sleep(delay)

        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed += 1

        print()

    if not dry_run:
        print(f"✅ Executive outreach complete: {sent} sent, {failed} failed")

if __name__ == '__main__':
    import sys
    dry_run = '--dry-run' in sys.argv
    run(dry_run=dry_run)
