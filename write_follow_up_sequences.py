"""
Write follow-up email sequences for every outreach category.
When brands/press/influencers don't reply, these go out at Day 7 and Day 14.
"""
import anthropic, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
OUT = Path('marketing_assets')
APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"

resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=3000,
    messages=[{"role": "user", "content": f"""Write complete follow-up email sequences for Spirit Library outreach campaigns.

For each category below, write:
- FOLLOW-UP 1 (Day 7 after no reply): short, punchy, adds new value, not just "checking in"
- FOLLOW-UP 2 (Day 14): even shorter, one sentence + clear ask, last contact

Categories:

1. SPIRITS BRANDS (Hendrick's, Aviation, Patrón, Fever-Tree)
   - Offer: Cocktail of the Day sponsorship
   - Add new value in FU1: Include a relevant metric or insight (e.g. "Gin is our #2 most-searched spirit this week")

2. DELIVERY PARTNERS (Instacart, DoorDash, Uber Eats)
   - Offer: Shopping cart ingredient ordering integration
   - Add new value in FU1: Frame this as a product story ("this is already how we plan to describe it to press")

3. PRESS / MEDIA (Punch, Eater, VinePair, Imbibe, TechCrunch, Bon Appétit)
   - Offer: App story / editorial coverage
   - Add new value in FU1: Offer an exclusive angle or new data point

4. COCKTAIL INFLUENCERS
   - Offer: Custom cocktail named after them in the app
   - Add new value in FU1: Tell them which of their videos inspired the cocktail name idea

5. BAR / HOSPITALITY (USBG, Tales of the Cocktail)
   - Offer: Share Menus as professional menu tool
   - Add new value in FU1: Offer a live demo/walkthrough

Rules:
- Follow-up 1: 100-150 words max. Specific and value-adding, never "just checking in."
- Follow-up 2: 2-3 sentences max. Create gentle urgency without desperation.
- Both follow-ups must feel like they come from Steven personally, not a marketing department.
- Include subject line for each (Reply continuation: "Re: [original subject]" or new angle)

App Store: {APP_STORE}"""}]
)

(OUT / "follow_up_sequences.txt").write_text(resp.content[0].text)
print("✓ Follow-up sequences → marketing_assets/follow_up_sequences.txt")
print(resp.content[0].text[:400] + "...")
