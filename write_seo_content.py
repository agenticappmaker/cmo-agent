"""
Write SEO landing page content targeting high-volume cocktail searches.
These can be hosted at agenticappmaker.github.io/spiritlibrary/ or a future blog.
"""
import anthropic, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
OUT = Path('marketing_assets/seo')
OUT.mkdir(parents=True, exist_ok=True)

APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"

TOP_SEARCHES = [
    ("how-to-make-negroni", "How to Make a Negroni", "Negroni", "gin, Campari, sweet vermouth"),
    ("old-fashioned-recipe", "Old Fashioned Cocktail Recipe", "Old Fashioned", "bourbon or rye, sugar, Angostura bitters"),
    ("espresso-martini-recipe", "Espresso Martini Recipe", "Espresso Martini", "vodka, espresso, coffee liqueur, simple syrup"),
    ("margarita-recipe", "Classic Margarita Recipe", "Margarita", "tequila, lime juice, triple sec"),
    ("aperol-spritz-recipe", "Aperol Spritz Recipe", "Aperol Spritz", "Aperol, prosecco, soda water, orange slice"),
    ("whiskey-sour-recipe", "Whiskey Sour Recipe", "Whiskey Sour", "bourbon, lemon juice, simple syrup, egg white"),
    ("moscow-mule-recipe", "Moscow Mule Recipe", "Moscow Mule", "vodka, ginger beer, lime juice"),
    ("daiquiri-recipe", "Classic Daiquiri Recipe", "Daiquiri", "rum, lime juice, simple syrup"),
]

def write_page(slug, title, cocktail, ingredients):
    prompt = f"""Write an SEO-optimized landing page for "{title}" that targets people searching for this cocktail recipe.

The page should rank for: {title.lower()}, how to make {cocktail.lower()}, {cocktail.lower()} recipe, {cocktail.lower()} ingredients, best {cocktail.lower()}

Key ingredients: {ingredients}

Spirit Library app: https://apps.apple.com/app/spirit-library/id6746823938 (1,700+ cocktail recipes, free iOS app, My Bar feature)

Write the full page in Markdown with:
1. H1: The exact search term ("{title}")
2. Intro paragraph (2-3 sentences, hooks the reader, includes keywords naturally)
3. H2: "The Classic {cocktail} Recipe"
   - Ingredients list (proper proportions)
   - Step-by-step instructions (5-8 steps)
4. H2: "Pro Tips for the Perfect {cocktail}"
   - 3-4 actionable tips (glassware, technique, variations)
5. H2: "History of the {cocktail}" (100 words, interesting, not dry)
6. H2: "Variations to Try"
   - 3 named variations with 1-sentence descriptions
7. H2: "Find This Recipe in Spirit Library"
   - Natural CTA: mention that Spirit Library has the {cocktail} plus 1,700+ other recipes, includes the My Bar feature, link to App Store
   - NOT salesy — feels like a helpful resource, not an ad

Total length: 600-900 words. Writing style: helpful, knowledgeable, warm. Like a knowledgeable friend who loves cocktails."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    text = resp.content[0].text
    path = OUT / f"{slug}.md"
    path.write_text(text)
    print(f"  ✓ {title} → seo/{slug}.md")
    return text

print(f"\n📝 Writing {len(TOP_SEARCHES)} SEO landing pages...\n")
for slug, title, cocktail, ingredients in TOP_SEARCHES:
    try:
        write_page(slug, title, cocktail, ingredients)
    except Exception as e:
        print(f"  ✗ {title}: {e}")

print(f"\n✅ SEO pages written to marketing_assets/seo/")
print("Next step: Host these at your website or blog for organic Google traffic.")
