"""Second pass email search — remaining targets with longer delays."""
import anthropic, os, json, re, time
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

targets = [
    ("Woodford Reserve",  "woodfordreserve.com"),
    ("BevMo!",            "bevmo.com"),
    ("St-Germain",        "stgermain.fr"),
    ("Cointreau",         "cointreau.com"),
    ("Uber Eats",         "ubereats.com"),
    ("Spritz Society",    "spritzsociety.com"),
    ("Woodford Reserve",  "woodfordreserve.com"),
]

# deduplicate
seen = set()
targets = [(n,s) for n,s in targets if n not in seen and not seen.add(n)]

results = {}
for name, site in targets:
    prompt = f"""Find the real partnership or press contact email for {name} ({site}).
Search their contact page, press kit, PR Newswire releases, and LinkedIn.
Return ONLY this JSON: {{"name": "{name}", "best_email": "email or null", "confidence": "high/medium/low", "source": "where found"}}"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
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
            print(f"  ✓ {name:<22} {result['best_email']:<45} [{result['confidence']}]")
        time.sleep(15)
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        time.sleep(20)

print("\n" + json.dumps(results, indent=2))
