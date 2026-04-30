"""Deep email search for missing/weak contact addresses."""
import anthropic, os, json, re, time
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

targets = [
    ("Q Mixers",             "qmixers.com",           "Info@QMixers.com"),
    ("Total Wine & More",    "totalwine.com",          "partnerships@totalwine.com"),
    ("Don Julio",            "donjulio.com",           None),
    ("Grey Goose Vodka",     "greygoose.com",          None),
    ("Tanqueray",            "tanqueray.com",          None),
    ("Woodford Reserve",     "woodfordreserve.com",    None),
    ("BevMo!",               "bevmo.com",              None),
    ("Absolut Vodka",        "absolut.com",            None),
    ("Bombay Sapphire",      "bombaysapphire.com",     None),
    ("Aperol",               "aperol.com",             None),
    ("St-Germain",           "stgermain.fr",           None),
    ("Cointreau",            "cointreau.com",          None),
    ("Uber Eats",            "ubereats.com",           "restaurants@uber.com"),
    ("Spritz Society",       "spritzsociety.com",      None),
]

results = {}

for name, site, current in targets:
    prompt = f"""Find the real partnership or business development contact email for {name} (website: {site}).

Search for:
1. Their official contact page at {site}/contact or {site}/about
2. Press kit or media inquiry email
3. Any publicly listed partnerships@, press@, business@, or hello@ email
4. LinkedIn for their partnerships/BD team contact

Current best guess (may be wrong): {current or 'none'}

Reply with ONLY this JSON, no other text:
{{"name": "{name}", "best_email": "email address or null", "confidence": "high/medium/low", "source": "brief note on where found"}}"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text") and block.text.strip():
                text = block.text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            results[name] = result
            print(f"  ✓ {name:<25} {result['best_email']:<45} [{result['confidence']}] — {result['source'][:60]}")
        else:
            print(f"  ? {name:<25} no JSON in response")
        time.sleep(6)
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        time.sleep(12)

print("\n\nFINAL RESULTS:")
print(json.dumps(results, indent=2))
