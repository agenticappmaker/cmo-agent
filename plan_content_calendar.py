"""
Plan a 2-week content calendar for Spirit Library social posts.
Alternates recipe spotlights and app feature showcases.
Saves to posts/spirit-library_calendar.json
"""
import anthropic, os, json
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

used_path = Path('posts/spirit-library_used_cocktails.json')
used = json.loads(used_path.read_text()) if used_path.exists() else []

# Build 14-day calendar starting tomorrow
start = datetime.now() + timedelta(days=1)
days = [(start + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(14)]

prompt = f"""You are the CMO for Spirit Library, a cocktail recipe iOS app.

Plan a 14-day social media content calendar. RULES:
- Day 1, 3, 5, 7, 9, 11, 13 (odd) = 9am post = COCKTAIL RECIPE spotlight
- Day 2, 4, 6, 8, 10, 12, 14 (even) = 7pm post = APP FEATURE showcase
- Each day has ONE post
- Never repeat a cocktail. Already used: {', '.join(used)}
- Feature posts must each highlight a DIFFERENT app feature
- Vary the cocktail spirits (don't do 3 whiskey cocktails in a row)
- Plan for seasonal relevance (it's early April — spring, warmer weather, lighter drinks trending)
- Make it feel like a real editorial calendar, not random

App features to rotate through: My Bar ingredient search, Flavor Search filters, Create Your Own Cocktail, Share Menus, Cocktail of the Day sponsorship, Shopping Cart coming soon, Occasions filter (Date Night/Brunch/Summer etc), Substitutions tab

Dates: {', '.join(days)}

Return as a JSON array:
[
  {{
    "date": "YYYY-MM-DD",
    "post_number": 1,
    "post_type": "recipe or feature",
    "time": "09:00 or 19:00",
    "subject": "cocktail name OR feature name",
    "hook": "the opening line or visual concept",
    "spirit_type": "for recipes: Gin/Bourbon/Tequila etc, for features: null",
    "pillar": "content pillar",
    "notes": "any specific creative direction"
  }}
]"""

resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=3000,
    messages=[{"role": "user", "content": prompt}]
)

text = resp.content[0].text.strip()
if text.startswith("```"):
    text = text.split("```")[1]
    if text.startswith("json"): text = text[4:].strip()

import re
match = re.search(r'\[[\s\S]*\]', text)
calendar = json.loads(match.group()) if match else []

# Save
cal_path = Path('posts/spirit-library_calendar.json')
cal_path.write_text(json.dumps(calendar, indent=2))

print(f"\n📅 14-DAY CONTENT CALENDAR\n{'='*60}")
for day in calendar:
    emoji = "🍸" if day['post_type'] == 'recipe' else "📱"
    print(f"{emoji} {day['date']} {day['time']} [{day['post_type'].upper()}] {day['subject']}")
    print(f"   Hook: {day['hook'][:80]}")
    print()

print(f"✅ Saved to {cal_path}")
