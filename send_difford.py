"""Send partnership email to Difford's Guide."""
import smtplib, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
load_dotenv()

GMAIL_USER = os.environ['GMAIL_USER']
GMAIL_PASS = os.environ['GMAIL_APP_PASSWORD']

body = """Hi Simon,

I'm Steven Samori, founder of Spirit Library — a new iOS cocktail app with 1,700+ recipes, now live on the App Store.

Difford's Guide is one of the most respected resources in the cocktail world, and I wanted to reach out directly because I think there's a natural overlap between your audience and what Spirit Library offers.

We've built a smart home bar app — users add their bottles and instantly discover every cocktail they can make, filtered by flavor, occasion, and now allergens. We also have a Share Menus feature that lets hosts curate and share a cocktail menu with guests before events.

A few thoughts on how we might work together:

1. **App review / editorial coverage** — if you review cocktail apps or have a "tools we use" type feature, we'd love to be considered. Happy to provide a demo walkthrough and full feature brief.

2. **Recipe partnership** — some of your signature recipes featured inside Spirit Library (credited, linked, with your brand). We'd cross-promote the collaboration to our growing user base.

3. **Cocktail of the Day sponsorship** — we feature one cocktail per day to all active users. A Difford's Guide featured day (or week) would be a natural fit.

You've built something remarkable at Difford's Guide. I built Spirit Library because I wanted a smarter version of the apps that already exist. I think your readers would appreciate it.

Download: https://apps.apple.com/app/spirit-library/id6746823938

Would love to find 15 minutes to chat.

Best,
Steven Samori
Founder, Spirit Library
claudesonnet111@gmail.com"""

msg = MIMEMultipart()
msg['From'] = GMAIL_USER
msg['To'] = "simon@diffordsguide.com"
msg['Subject'] = "Spirit Library x Difford's Guide — Partnership / Feature Opportunity"
msg.attach(MIMEText(body, 'plain'))

with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
    s.login(GMAIL_USER, GMAIL_PASS)
    s.send_message(msg)

print("✓ Sent to simon@diffordsguide.com")
