"""
Send partnership/sponsorship emails to spirits brands and delivery partners.
"""
import smtplib, os, json, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

GMAIL_USER = os.environ['GMAIL_USER']
GMAIL_PASS = os.environ['GMAIL_APP_PASSWORD']
APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"

# ── Email templates ───────────────────────────────────────────────────────────

def spirits_brand_email(brand_name, spirit_type, notes):
    return f"""Hi {brand_name} Team,

I'm Steven Samori, founder of Spirit Library — a cocktail recipe app with 1,700+ recipes, now live on the App Store.

We've built something that cocktail enthusiasts genuinely use: a smart home bar manager where users add their bottles and instantly discover every cocktail they can make. {spirit_type} is one of our most-searched spirit categories.

I'm reaching out because we have a sponsorship opportunity called **Cocktail of the Day** — a daily featured cocktail spotlight directly in the app. We're offering founding sponsor pricing to a select handful of brands before we raise rates in Q3.

**What the sponsorship includes:**
- Daily featured cocktail using your spirit, seen by every active user
- Your brand name and bottle featured in the post image
- Linked to your Instagram and purchase options
- Exclusive category lock (no competing {spirit_type} brands while you sponsor)

**Why now:** We're early-stage with a highly engaged cocktail-obsessed audience — the CPM is the lowest it will ever be, and founding sponsors get category exclusivity.

I'd love to share our rate card and user metrics. Would a 15-minute call this week work?

Download Spirit Library: {APP_STORE}

Best,
Steven Samori
Founder, Spirit Library
claudesonnet111@gmail.com"""


def delivery_email(company_name, platform_type):
    return f"""Hi {company_name} Partnerships Team,

I'm Steven Samori, founder of Spirit Library — a cocktail recipe app (1,700+ recipes) live on the App Store.

I'm reaching out about a natural integration opportunity: **Spirit Library's Shopping Cart feature**.

Here's how it works: A user opens a Negroni recipe, sees they're missing Campari, and taps "Order Ingredients." Right now we're building the delivery partner integrations for that flow — and {company_name} is our first choice given your reach and {platform_type}.

**The opportunity:**
- Deep-link integration sending ingredient lists directly to {company_name}
- Co-marketing: "Order cocktail ingredients via {company_name}" in-app
- Featured placement in our app's shopping flow
- Press release announcing the partnership (we have press contacts at Food & Wine, Punch, Eater)

This is a genuine product integration — cocktail enthusiasts are exactly your high-value customer. The average Spirit Library user shops premium ingredients.

Would love to connect with your integrations or partnerships team. 15 minutes?

Download Spirit Library: {APP_STORE}

Best,
Steven Samori
Founder, Spirit Library
claudesonnet111@gmail.com"""


def bar_email(org_name, category, pitch_angle):
    return f"""Hi {org_name} Team,

I'm Steven Samori, founder of Spirit Library — a cocktail app with 1,700+ recipes, now live on iOS.

I wanted to reach out specifically because of your work in {category}. We've built a feature called **Share Menus** that I think is genuinely useful for your world: bar managers and owners can curate a full cocktail menu inside Spirit Library and share it as a live, interactive digital menu with guests — no PDF, no QR code clunker.

**For bars, this means:**
- A live cocktail menu guests can browse on their phones
- 1,700+ recipes your staff can use for training and inspiration
- Custom cocktail creation tool — build and save your signature drinks
- Allergies filter so guests can self-filter to safe cocktails

{pitch_angle}

I'd love to offer your team free access and get your feedback. Would you be open to a quick chat?

Download Spirit Library: {APP_STORE}

Best,
Steven Samori
Founder, Spirit Library
claudesonnet111@gmail.com"""


# ── Contacts ──────────────────────────────────────────────────────────────────

SPIRITS_CONTACTS = [
    {
        "to": "partnerships@hendricksgin.com",
        "brand": "Hendrick's Gin",
        "spirit": "Gin",
        "notes": "Quirky premium gin brand",
        "subject": "Cocktail of the Day Sponsorship — Spirit Library App (founding rate)"
    },
    {
        "to": "hello@aviationgin.com",
        "brand": "Aviation American Gin",
        "spirit": "Gin",
        "notes": "Celebrity gin brand",
        "subject": "Partnership Opportunity — Spirit Library x Aviation Gin"
    },
    {
        "to": "contactus@patrontequila.com",
        "brand": "Patrón",
        "spirit": "Tequila",
        "notes": "Premium tequila brand",
        "subject": "Cocktail of the Day Sponsorship — Spirit Library App"
    },
    {
        "to": "hello@fever-tree.com",
        "brand": "Fever-Tree",
        "spirit": "mixer",
        "notes": "Premium mixer brand — perfect for ingredient search placement",
        "subject": "Ingredient Search Sponsorship — Spirit Library x Fever-Tree"
    },
]

DELIVERY_CONTACTS = [
    {
        "to": "partnerships@instacart.com",
        "company": "Instacart",
        "platform": "same-day grocery delivery",
        "subject": "Cocktail Ingredient Integration — Spirit Library x Instacart"
    },
    {
        "to": "partnerships@doordash.com",
        "company": "DoorDash",
        "platform": "on-demand delivery",
        "subject": "Cocktail Ingredient Ordering — Spirit Library x DoorDash"
    },
    {
        "to": "restaurant-partnerships@uber.com",
        "company": "Uber Eats",
        "platform": "delivery marketplace",
        "subject": "Cocktail Ingredient Integration — Spirit Library x Uber Eats"
    },
]

BAR_CONTACTS = [
    {
        "to": "info@talesofthecocktail.org",
        "org": "Tales of the Cocktail Foundation",
        "category": "the cocktail festival and education space",
        "pitch": "We'd love to sponsor a session or partner for your next event — Spirit Library's Share Menus would be a great demo for festival attendees building their own menus.",
        "subject": "Partnership Pitch — Spirit Library x Tales of the Cocktail"
    },
    {
        "to": "info@usbg.org",
        "org": "United States Bartenders Guild",
        "category": "bartender education and community",
        "pitch": "Spirit Library's 1,700+ recipe library and custom cocktail creator could be a genuine resource for USBG members and certification programs.",
        "subject": "Member Resource Partnership — Spirit Library x USBG"
    },
]


# ── Sender ────────────────────────────────────────────────────────────────────

def send_email(to, subject, body):
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)
    print(f"  ✓ Sent → {to}")


sent = []
failed = []

print("\n📧 Sending spirits brand emails...")
for c in SPIRITS_CONTACTS:
    try:
        body = spirits_brand_email(c['brand'], c['spirit'], c['notes'])
        send_email(c['to'], c['subject'], body)
        sent.append(c['to'])
        time.sleep(3)
    except Exception as e:
        print(f"  ✗ {c['to']}: {e}")
        failed.append(c['to'])

print("\n📦 Sending delivery partner emails...")
for c in DELIVERY_CONTACTS:
    try:
        body = delivery_email(c['company'], c['platform'])
        send_email(c['to'], c['subject'], body)
        sent.append(c['to'])
        time.sleep(3)
    except Exception as e:
        print(f"  ✗ {c['to']}: {e}")
        failed.append(c['to'])

print("\n🍸 Sending bar/hospitality emails...")
for c in BAR_CONTACTS:
    try:
        body = bar_email(c['org'], c['category'], c['pitch'])
        send_email(c['to'], c['subject'], body)
        sent.append(c['to'])
        time.sleep(3)
    except Exception as e:
        print(f"  ✗ {c['to']}: {e}")
        failed.append(c['to'])

print(f"\n✅ Done. Sent: {len(sent)} | Failed: {len(failed)}")
if failed:
    print(f"Failed: {failed}")
