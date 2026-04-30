"""Get remaining emails from Claude knowledge (no web search)."""
import anthropic, os, json
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

prompt = """Based on your training knowledge, give me the best public partnership or press contact email for each brand:

1. Woodford Reserve (woodfordreserve.com) — Brown-Forman brand
2. BevMo! (bevmo.com) — California alcohol retailer, owned by Total Wine since 2020
3. St-Germain (stgermain.fr) — Bacardi-owned elderflower liqueur
4. Cointreau (cointreau.com) — Remy Cointreau-owned triple sec
5. Uber Eats partnerships (ubereats.com) — alcohol and grocery delivery partnerships team
6. Spritz Society (spritzsociety.com) — RTD wine cocktail brand

Use what you know about their PR agencies, press offices, corporate parents, and publicly listed contacts.

Respond ONLY as a JSON array with no markdown:
[{"name": "Woodford Reserve", "best_email": "...", "confidence": "high/medium/low", "note": "..."}]"""

resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=800,
    messages=[{"role": "user", "content": prompt}]
)

text = resp.content[0].text.strip()
if text.startswith("```"):
    text = text.split("```")[1]
    if text.startswith("json"):
        text = text[4:].strip()

results = json.loads(text)
for r in results:
    print(f"  {r['name']:<22} {r['best_email']:<40} [{r['confidence']}]")
    print(f"  {'':22} {r['note']}")
    print()

print(json.dumps(results, indent=2))
