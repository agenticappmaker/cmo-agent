"""
Send partnership outreach emails for Spirit Library.
Uses the same pattern as send_bar_emails.py.
"""
import smtplib, os, json, time, csv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

GMAIL_USER = "spiritlibraryapp@gmail.com"
GMAIL_PASS = "hviq yshz bvhz funv"
WEBSITE = "https://spiritlibrary.app"
APP_STORE = "https://apps.apple.com/us/app/spirit-library/id6761500950"

CONTACTS_FILE = Path('outreach/targets/new_partners.json')
LOG_FILE = Path('outreach/logs/partner_emails.csv')
DELAY_BETWEEN_EMAILS = 45

CATEGORY_OFFERS = {
    "Premium Spirits Brand": "featured recipes showcasing your products, ingredient search placement, and Cocktail of the Day sponsorship",
    "Mixer/Ingredient Brand": "ingredient search placement (users searching your products see every cocktail that uses them), shopping list integration, and branded recipe collections",
    "Bar Tool Company": "tool recommendations within recipes, gear guides, and co-branded content for home bartenders",
    "Cocktail Subscription Box": "recipe pairing content (pair your monthly box with our 1,500+ recipe database), cross-promotion to our user base",
    "Cocktail Influencer": "co-created custom cocktail recipes featured in-app, shared menu collaborations, and cross-promotion",
    "Food/Drink Media": "editorial partnership, app review, recipe content collaboration, and exclusive cocktail data/trends",
    "Bartending School/Program": "free training tool for students (1,500+ recipes + substitution guide), curriculum integration, bulk account setup",
}


def build_email(partner):
    name = partner.get("name", "")
    category = partner.get("category", "")
    pitch = partner.get("pitch_angle", "")
    value = partner.get("value_prop", "")
    offer = CATEGORY_OFFERS.get(category, "a partnership that benefits both our audiences")

    # Extract first name or use team
    first = name.split()[0] if name and not any(x in name.lower() for x in ["inc", "llc", "co.", "brand"]) else f"{name} team"

    subject = f"Partnership Opportunity — Spirit Library Cocktail App"

    body = f"""Hi {first},

I'm Steven Samori, founder of Spirit Library — a free cocktail recipe app with 1,500+ recipes, smart ingredient matching, and a built-in substitution guide. We recently launched on the App Store and are growing quickly.

{pitch}

You can check out the app and everything it offers at {WEBSITE}

I'd love to explore how we could work together — specifically {offer}.

Would you be open to a quick chat this week?

Best,
Steven Samori
Smore Labs
{WEBSITE}
{APP_STORE}"""

    return {"subject": subject, "body": body}


def already_sent(email):
    if not LOG_FILE.exists():
        return False
    with open(LOG_FILE) as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 3 and row[2].strip().lower() == email.strip().lower():
                return True
    return False


def log_send(name, email, status):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().isoformat(), name, email, status])


def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.send_message(msg)


def main():
    partners = json.loads(CONTACTS_FILE.read_text())
    with_email = [p for p in partners if p.get("email")]

    print(f"Partnership outreach — {len(with_email)} contacts with emails")
    print(f"{'─' * 50}")

    sent = 0
    skipped = 0

    for p in with_email:
        email = p["email"]
        name = p["name"]

        if already_sent(email):
            print(f"  SKIP (already sent): {name} <{email}>")
            skipped += 1
            continue

        try:
            msg = build_email(p)
            send_email(email, msg["subject"], msg["body"])
            log_send(name, email, "sent")
            sent += 1
            print(f"  ✓ Sent to {name} <{email}> ({sent}/{len(with_email) - skipped})")
            time.sleep(DELAY_BETWEEN_EMAILS)
        except Exception as e:
            log_send(name, email, f"error: {e}")
            print(f"  ✗ Failed: {name} <{email}> — {e}")

    print(f"\n{'─' * 50}")
    print(f"Done. {sent} sent, {skipped} skipped (already sent).")


if __name__ == "__main__":
    main()
