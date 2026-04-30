"""
Find bar owners, bar managers, and hospitality industry contacts
for the Spirit Library Share Menus + professional use case pitch.
Targets: notable cocktail bars, bar industry orgs, sommelier associations.
"""
import anthropic, os, json, re, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

BAR_FILE = Path('outreach/targets/bars_hospitality.json')

targets = [
    ("United States Bartenders Guild (USBG)", "usbg.org", "bartender association", "45,000+ bartender members nationally"),
    ("Bar Convent Brooklyn", "barconventbrooklyn.com", "industry trade show", "annual NYC bar trade show, thousands of attendees"),
    ("Tales of the Cocktail Foundation", "talesofthecocktail.org", "industry org", "annual NOLA cocktail festival + year-round programs"),
    ("Employees Only NYC", "employeesonlynyc.com", "iconic cocktail bar", "legendary bar known for innovative cocktails"),
    ("Death & Co", "deathandcompany.com", "cocktail bar group", "multi-city cocktail bar group, Death & Co cookbook"),
    ("Attaboy NYC", "attaboy.us", "cocktail bar", "influential NYC cocktail bar, no-menu ordering style"),
    ("Trick Dog San Francisco", "trickdogbar.com", "cocktail bar", "SF bar known for creative rotating menus"),
    ("The NoMad Bar", "thenomadhotel.com", "hotel bar", "award-winning hotel bar, NYC"),
    ("American Bartenders Association", "americanbartenders.org", "association", "national bartender training and certification"),
    ("The Bar Show (UK)", "thebarshow.co.uk", "trade show", "major UK bar industry trade event"),
    ("Nightclub & Bar Media Group", "ncbshow.com", "trade media/show", "largest US bar industry trade show and media"),
    ("Flair Bartenders Association", "flair.de", "association", "international flair bartending association"),
    ("Bon Vivants / Trick Dog group", "bonvivants.com", "bar consulting", "SF-based bar consulting and management group"),
    ("Kimpton Hotels & Restaurants", "ihg.com/kimpton", "hotel/bar group", "boutique hotel chain with notable cocktail programs"),
    ("Soho House", "sohohouse.com", "members club", "global members clubs with bars in major cities"),
]

results = []
print(f"\n🍸 Finding bar industry contacts for Share Menus pitch...\n")

for i, (name, domain, category, context) in enumerate(targets, 1):
    prompt = f"""From your training knowledge, identify the best contact at {name} ({domain}) for a partnership pitch about Spirit Library.

Context: {context}

Spirit Library pitch for bars/hospitality: Our "Share Menus" feature lets bar managers and owners curate full cocktail menus and share them digitally with guests — a modern, interactive cocktail menu. The app also has 1,700+ recipes bars can use for staff training and inspiration.

From training knowledge, provide:
1. The most relevant decision-maker (bar director, F&B director, partnerships lead, executive director for orgs)
2. Their known email or best contact method (infer email pattern if needed)
3. A known recent initiative or cocktail program detail

Return ONLY this JSON:
{{
  "organization": "{name}",
  "contact_name": "...",
  "contact_title": "...",
  "contact_email": "email or null",
  "contact_method": "email/form/instagram",
  "recent_initiative": "specific recent thing they did",
  "pitch_angle": "one sentence tailored to what they do",
  "category": "{category}"
}}"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            
            messages=[{"role": "user", "content": prompt}]
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text") and block.text.strip():
                text = block.text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            result = json.loads(match.group())
            result['researched_at'] = datetime.utcnow().isoformat()
            results.append(result)
            print(f"  [{i}/{len(targets)}] ✓ {name}: {result.get('contact_name','?')} — {result.get('contact_email','no email')}")
        else:
            print(f"  [{i}/{len(targets)}] ? {name}: no data")
        time.sleep(5)
    except Exception as e:
        print(f"  [{i}/{len(targets)}] ✗ {e}")
        time.sleep(5)

BAR_FILE.parent.mkdir(exist_ok=True)
BAR_FILE.write_text(json.dumps(results, indent=2))
print(f"\n✅ Found {len(results)} bar/hospitality contacts → {BAR_FILE}")
