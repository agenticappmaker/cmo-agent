#!/usr/bin/env python3.12
"""
Queue the 6-post KOVAL Kocktail Kollab campaign.

One post every 2 weeks starting 2026-06-01 (next Monday after partnership
recipes shipped). All 6 KOVAL signature recipes go out over ~10 weeks.

Images are KOVAL-supplied product photography — no AI imagery. Captions
quote Andrew Karasek's recipe sheet verbatim, tag @kovaldistillery, and
use #KovalKollab on every post so reposts cluster.

Idempotent — running again with the same posts already queued is a no-op.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUEUE_PATH = ROOT / "posts" / "queue.json"
IMG_DIR = Path.home() / "koval-recipes-2026-05-27"

# Bi-weekly cadence — Mondays 09:00 (best IG slot per brand config)
START = datetime(2026, 6, 1, 9, 0, 0)
CADENCE_DAYS = 14

# Hashtag block — #KovalKollab is the campaign anchor (used every post so
# KOVAL can grep them). Then Spirit Library core, then cocktail-specific.
CORE_TAGS = "#KovalKollab #SpiritLibrary #KovalDistillery #CraftCocktails #HomeBar #MixologyApp #CocktailRecipes #Bartending"


def caption_for(name: str, ingredients_block: str, method: str, garnish: str, glassware: str) -> str:
    return (
        f"KOVAL KOLLAB — {name}\n\n"
        f"A signature recipe from our partners at @kovaldistillery — single-grain organic spirits from Chicago.\n\n"
        f"📝 RECIPE\n{ingredients_block}\n\n"
        f"🥃 GLASS — {glassware}\n"
        f"🌿 GARNISH — {garnish}\n\n"
        f"⚙️ METHOD\n{method}\n\n"
        f"Save it (and the rest of the KOVAL Kocktails collection) in Spirit Library — link in bio."
    )


POSTS = [
    {
        "slug": "koval-cran-gin-spritz",
        "name": "Cran Gin Spritz",
        "image": "KOVAL_cran-gin-spritz.png",
        "ingredients_block": "• 2 oz KOVAL Cranberry Gin Liqueur\n• 3.5 oz soda water\n• 0.25 oz lime juice\n• Splash of dry sparkling wine",
        "method": "Build ingredients over ice. Garnish with sliced citrus.",
        "garnish": "Sliced citrus",
        "glassware": "Stemless wine glass",
        "extra_tags": "#Spritz #SummerCocktails #Gin",
    },
    {
        "slug": "koval-old-fashioned",
        "name": "KOVAL Old Fashioned",
        "image": "KOVAL_Old_Fashioned.png",
        "ingredients_block": "• 2 oz KOVAL Bourbon\n• 0.25 oz turbinado syrup\n• 3 dashes cherry bark vanilla bitters",
        "method": "Stir ingredients in a glass with ice. Strain and serve over ice. Garnish with an orange peel twist.",
        "garnish": "Orange peel twist",
        "glassware": "Rocks glass",
        "extra_tags": "#OldFashioned #Bourbon #ClassicCocktails",
    },
    {
        "slug": "koval-chicago-sunset",
        "name": "Chicago Sunset",
        "image": "KOVAL_Chicago_Sunset.png",
        "ingredients_block": "• 1.5 oz KOVAL Bourbon\n• 0.5 oz KOVAL Cranberry Gin Liqueur\n• 0.5 oz turbinado syrup\n• 0.75 oz lemon juice",
        "method": "Shake Bourbon, turbinado, and lemon juice with ice. Double strain into a glass with fresh ice. Use a bar spoon to add Cranberry Gin. Garnish with a lemon wheel.",
        "garnish": "Lemon wheel",
        "glassware": "Rocks glass",
        "extra_tags": "#ChicagoCocktails #Bourbon #HappyHour",
    },
    {
        "slug": "koval-ryes-and-shine",
        "name": "Ryes & Shine",
        "image": "KOVAL_Ryes_N_Shine.png",
        "ingredients_block": "• 1 oz KOVAL Rye\n• 0.5 oz KOVAL Ginger Liqueur\n• 0.5 oz simple syrup\n• 0.5 oz lime juice",
        "method": "Shake ingredients with ice. Double strain into glass. Garnish with a lime twist.",
        "garnish": "Lime twist",
        "glassware": "Nick and Nora",
        "extra_tags": "#Rye #BrunchCocktails #GingerCocktails",
    },
    {
        "slug": "koval-gold-rush",
        "name": "KOVAL Gold Rush",
        "image": "KOVAL_Gold Rush.png",
        "ingredients_block": "• 2 oz KOVAL Rye\n• 0.5 oz KOVAL Chrysanthemum & Honey\n• 0.75 oz lemon juice\n• 0.5 oz honey",
        "method": "Shake ingredients with ice. Double strain into glass. Garnish with a lemon twist.",
        "garnish": "Lemon twist",
        "glassware": "Coupe",
        "extra_tags": "#GoldRush #Rye #HoneyCocktails",
    },
    {
        "slug": "koval-shamelessly-nameless",
        "name": "Shamelessly Nameless",
        "image": "KOVAL_Shamelessly_Nameless.png",
        "ingredients_block": "• 1.75 oz KOVAL Dry Gin\n• 0.5 oz KOVAL Ginger Liqueur\n• 0.5 oz lemon juice\n• 0.25 oz allspice syrup\n• 5 dashes angostura bitters",
        "method": "Shake ingredients (sans bitters) with ice. Double strain over fresh ice. Garnish with a lemon slice. Dash angostura bitters over top.",
        "garnish": "Lemon slice, dash angostura bitters on top",
        "glassware": "Rocks glass",
        "extra_tags": "#Gin #SpicyCocktails #ModernMixology",
    },
]


def build_entry(post: dict, slot_index: int) -> dict:
    scheduled_dt = START + timedelta(days=CADENCE_DAYS * slot_index)
    image_path = IMG_DIR / post["image"]
    if not image_path.exists():
        raise FileNotFoundError(f"KOVAL image not found: {image_path}")
    caption = caption_for(
        post["name"], post["ingredients_block"], post["method"], post["garnish"], post["glassware"],
    )
    hashtags = f"{CORE_TAGS} {post['extra_tags']}"
    return {
        "id": f"spirit-library_instagram_kovalkollab_{post['slug']}",
        "brand": "spirit-library",
        "platform": "instagram",
        "campaign": "KovalKollab",
        "caption": caption,
        "hashtags": hashtags,
        "image_path": str(image_path),
        "post_idea": f"KOVAL Kollab #{slot_index + 1} of 6 — {post['name']}",
        "scheduled_at": scheduled_dt.isoformat(),
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
    }


def main():
    queue = json.loads(QUEUE_PATH.read_text()) if QUEUE_PATH.exists() else []
    existing_ids = {q.get("id") for q in queue}
    added = 0
    for i, post in enumerate(POSTS):
        entry = build_entry(post, i)
        if entry["id"] in existing_ids:
            print(f"skip  {entry['id']} — already queued")
            continue
        queue.append(entry)
        added += 1
        print(f"queue {entry['scheduled_at'][:10]}  {entry['post_idea']}")
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))
    print(f"\nAdded {added} post(s) to {QUEUE_PATH}")


if __name__ == "__main__":
    main()
