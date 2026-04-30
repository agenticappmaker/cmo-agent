"""
Find cocktail micro-influencers with emails for Spirit Library outreach.
Uses Claude's training knowledge — focused on real, findable creators.
"""
import anthropic, os, json, re, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
OUT = Path('outreach/targets/influencers_v2.json')

creators = [
    ("Cocktail Chemistry", "YouTube", "chemistry-driven cocktail tutorials, 1M+ subs"),
    ("How To Drink", "YouTube", "Greg Titian, cocktail history and technique, 1M+ subs"),
    ("Anders Erickson", "YouTube/Instagram", "home bartending tutorials, 300k+"),
    ("Educated Barfly", "YouTube", "Merlin Verrier, advanced cocktail techniques"),
    ("Spruce Eats Cocktails", "Web/Social", "cocktail recipe site, huge SEO traffic"),
    ("Steve the Bartender", "YouTube/Instagram", "Steve Roennfeldt, bartending tips 800k+"),
    ("Vlad SlickBartender", "YouTube", "cocktail tricks and tutorials 200k+"),
    ("John Porta (iamjohnporta)", "Instagram", "NYC cocktail culture, 100k+"),
    ("Jeffrey Morgenthaler", "Instagram/Substack", "industry legend, Clyde Common bar director"),
    ("Camille Wilson (The Cocktail Snob)", "Instagram", "Black cocktail culture, 50k+"),
    ("A Bar Above (Christine Sismondo)", "YouTube", "home bartending education 150k+"),
    ("Punch Drink (editorial)", "Instagram/Web", "cocktail media brand, 100k+"),
    ("The Educated Barfly Merlin Verrier", "Instagram", "technique-focused, 80k+"),
    ("Nick Korbee (Egg Shop NYC)", "Instagram", "chef/bartender hybrid, NYC scene"),
    ("Lynnette Marrero", "Instagram", "Speed Rack co-founder, NYC bar legend"),
    ("Jim Meehan", "Substack", "PDT founder, cocktail author, industry tastemaker"),
    ("Natasha David", "Instagram", "Nitecap NYC, Women Who Whiskey, 30k+"),
    ("Alicia Kennedy (food writer)", "Substack", "food/drink culture, 20k subscribers"),
    ("Difford's Guide", "Instagram/Web", "UK cocktail encyclopedia, massive reach"),
    ("Thirsty Magazine", "Instagram", "modern cocktail culture mag, 40k+"),
]

results = []
print(f"\n🍹 Finding cocktail influencer contacts ({len(creators)} targets)...\n")

for i, (name, platform, context) in enumerate(creators, 1):
    prompt = f"""From your training knowledge, provide contact details for {name} ({platform}).

Context: {context}

I want to pitch them on Spirit Library (iOS cocktail app, 1,700+ recipes, AI-powered My Bar) for:
1. A custom cocktail created in their name inside the app
2. Potential paid collaboration

From training knowledge:
1. Their real name (if handle given)
2. Their email or best contact method
3. Their audience size and primary platform
4. Their known collaboration style or past brand deals
5. One personalized angle for Spirit Library

Return ONLY this JSON:
{{
  "name": "{name}",
  "real_name": "...",
  "platform": "{platform}",
  "contact_email": "email or null",
  "contact_method": "email/DM/form",
  "instagram_handle": "@handle or null",
  "youtube_channel": "URL or null",
  "audience_size": "...",
  "collaboration_style": "what they typically do with brands",
  "pitch_angle": "one personalized sentence for Spirit Library",
  "tier": "nano/micro/mid/macro"
}}"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            result = json.loads(match.group())
            result['researched_at'] = datetime.utcnow().isoformat()
            results.append(result)
            print(f"  [{i}/{len(creators)}] ✓ {name}: {result.get('contact_email') or result.get('contact_method','?')} | {result.get('audience_size','?')}")
        else:
            print(f"  [{i}/{len(creators)}] ? {name}: no structured data")
        time.sleep(3)
    except Exception as e:
        print(f"  [{i}/{len(creators)}] ✗ {e}")
        time.sleep(3)

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(results, indent=2))
print(f"\n✅ {len(results)} influencer contacts → {OUT}")
