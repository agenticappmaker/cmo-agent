"""
Find Head of Marketing / CMO / VP Marketing for each company we've emailed.
Uses Claude + web search to find name, LinkedIn, and email.
Saves to outreach/targets/executives.json
"""
import anthropic, os, json, re, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

OUTREACH_DIR = Path('outreach')
EXEC_CACHE = OUTREACH_DIR / 'executive_cache.json'

def load_cache():
    if EXEC_CACHE.exists():
        return json.loads(EXEC_CACHE.read_text())
    return {}

def save_cache(cache):
    EXEC_CACHE.write_text(json.dumps(cache, indent=2))

def find_exec(company_name: str, category: str, domain: str = None) -> dict:
    prompt = f"""From your training knowledge, identify the most senior marketing executive (CMO, VP Marketing, Head of Marketing, Global Brand Director, or equivalent) at {company_name}.

Company: {company_name}
Category: {category}
Domain: {domain or 'unknown'}

Use your training knowledge to fill in as much as you can. For email, infer based on the company's known email pattern (e.g. if the domain is hendricks.com and the pattern is firstname.lastname@domain.com, construct the likely email). If you truly don't know a name, use null.

Return ONLY valid JSON, nothing else:
{{
  "company": "{company_name}",
  "exec_name": "Full Name or null",
  "exec_title": "exact title or null",
  "exec_linkedin": "linkedin.com/in/handle or null",
  "exec_email": "constructed or known email or null",
  "email_confidence": "verified/inferred/guessed",
  "email_pattern": "company email pattern e.g. f.last@company.com or null",
  "recent_initiative": "one known marketing campaign or initiative they led, or null",
  "found_via": "training knowledge"
}}"""

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
        return json.loads(match.group())
    raise ValueError(f"No JSON in response: {text[:200]}")

# Load companies from outbox
outbox = json.loads(Path('outreach/outbox.json').read_text())
companies = [e for e in outbox if e['status'] == 'sent']

cache = load_cache()
print(f"\n🔍 Finding marketing executives for {len(companies)} companies...")
print(f"   Already cached: {len(cache)}\n")

done = 0
failed = 0

for i, company in enumerate(companies, 1):
    name = company['name']
    category = company.get('category', '')

    # Infer domain from contact email
    email = company.get('contact_email', '')
    domain = email.split('@')[-1] if '@' in email else None

    if name in cache:
        print(f"  [{i}/{len(companies)}] ⏭  {name} (cached: {cache[name].get('exec_name','?')})")
        continue

    print(f"  [{i}/{len(companies)}] 🔎 {name}...")

    try:
        result = find_exec(name, category, domain)
        result['company_category'] = category
        result['company_email_sent_to'] = email
        result['researched_at'] = datetime.utcnow().isoformat()
        cache[name] = result
        save_cache(cache)
        exec_name = result.get('exec_name', 'unknown')
        exec_email = result.get('exec_email', 'not found')
        print(f"      ✓ {exec_name} — {result.get('exec_title','')} | email: {exec_email}")
        done += 1
        time.sleep(5)
    except Exception as e:
        print(f"      ✗ Error: {e}")
        cache[name] = {"company": name, "error": str(e), "researched_at": datetime.utcnow().isoformat()}
        save_cache(cache)
        failed += 1
        time.sleep(5)

print(f"\n✅ Done: {done} found, {failed} failed")
print(f"Results saved to {EXEC_CACHE}")
