"""
Find food/drink/tech journalists and editors who cover cocktail apps,
spirits industry, and food tech — for press coverage of Spirit Library.
"""
import anthropic, os, json, re, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

PRESS_FILE = Path('outreach/targets/press.json')

publications = [
    ("TechCrunch", "techcrunch.com", "tech/startup", "food tech, consumer apps, startup launches"),
    ("VentureBeat", "venturebeat.com", "tech", "AI, consumer apps, startup funding"),
    ("Food & Wine", "foodandwine.com", "food/drink", "cocktail apps, spirits, home bartending"),
    ("Eater", "eater.com", "food/drink", "bar culture, spirits, cocktail trends"),
    ("Punch Drink", "punchdrink.com", "spirits media", "cocktail culture, spirits industry"),
    ("Imbibe Magazine", "imbibemagazine.com", "cocktail media", "cocktail apps, spirits, bar trends"),
    ("Thrillist", "thrillist.com", "lifestyle/food", "cocktail apps, drinking culture, food tech"),
    ("Vinepair", "vinepair.com", "drinks media", "cocktail apps, spirits, wine, bartending"),
    ("Beverage Dynamics", "beveragedynamics.com", "trade", "spirits industry, beverage apps, retail"),
    ("Bar Business Magazine", "barbizmag.com", "trade", "bar technology, cocktail apps, bar management"),
    ("Spirits Business", "thespiritsbusiness.com", "trade", "spirits industry, apps, technology"),
    ("The Manual", "themanual.com", "men's lifestyle", "cocktail apps, home bar, spirits"),
    ("Gear Patrol", "gearpatrol.com", "lifestyle", "cocktail tools, home bar apps"),
    ("Product Hunt", "producthunt.com", "tech", "app launches, consumer products"),
    ("AppAdvice", "appadvice.com", "app reviews", "iOS app reviews and coverage"),
]

results = []
print(f"\n🔍 Finding journalists/editors at {len(publications)} publications...\n")

for i, (pub, domain, category, beat) in enumerate(publications, 1):
    prompt = f"""From your training knowledge, identify the specific journalist, editor, or writer at {pub} ({domain}) who covers {beat}.

I need to pitch them Spirit Library — an iOS cocktail recipe app with 1,700+ recipes, ingredient-based search, and a cocktail creation tool.

Use your training knowledge to provide:
1. Their name and exact title
2. A relevant article they are known for covering (cocktail apps, spirits tech, food/drink)
3. Their known email address or Twitter/social handle (or infer the email from the publication's pattern)
4. Their preferred pitch method

Return ONLY this JSON:
{{
  "publication": "{pub}",
  "journalist_name": "Full Name",
  "journalist_title": "title/beat",
  "journalist_email": "email or null",
  "journalist_twitter": "@handle or null",
  "recent_relevant_article": "title/description of a recent relevant article they wrote",
  "pitch_angle": "one-sentence angle specific to what they cover and Spirit Library",
  "outreach_type": "email or dm",
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
            name = result.get('journalist_name', '?')
            email = result.get('journalist_email', 'no email')
            print(f"  [{i}/{len(publications)}] ✓ {pub}: {name} — {email}")
        else:
            print(f"  [{i}/{len(publications)}] ? {pub}: no structured data found")
        time.sleep(5)
    except Exception as e:
        print(f"  [{i}/{len(publications)}] ✗ {pub}: {e}")
        time.sleep(5)

PRESS_FILE.parent.mkdir(exist_ok=True)
PRESS_FILE.write_text(json.dumps(results, indent=2))
print(f"\n✅ Found {len(results)} press contacts → {PRESS_FILE}")
