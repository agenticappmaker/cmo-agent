"""
Generate a bank of high-quality gpt-image-2 images for Spirit Library.
Covers: hero cocktails, feature showcases, lifestyle/hosting, seasonal, educational.
"""
import os, time, base64
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = "gpt-image-2"
OUT = Path("posts/images/spirit-library/bank")
OUT.mkdir(parents=True, exist_ok=True)

IMAGES = [
    # ── Hero cocktails ────────────────────────────────────────────────────────
    ("negroni_hero", "A perfectly crafted Negroni in a heavy crystal rocks glass with one large ice cube, garnished with a wide orange peel twist. Deep amber and ruby tones. Cinematic bar lighting, dark moody background, condensation on the glass. Professional cocktail photography, editorial quality."),
    ("espresso_martini_hero", "An Espresso Martini in an elegant coupe glass, velvety dark espresso foam on top with three coffee beans placed artfully. Steam rising gently. Dark marble bar surface, warm bokeh background. Luxurious and inviting, professional cocktail photography."),
    ("aperol_spritz_hero", "A vibrant Aperol Spritz in a large wine glass with ice, orange slice, and a rosemary sprig. Brilliant orange color. Sunlit terrace setting, Mediterranean vibes, golden hour light. Joyful and summery, professional food photography."),
    ("old_fashioned_hero", "A classic Old Fashioned in a thick-bottomed lowball glass, amber whiskey over a single large ice sphere, orange peel and Luxardo cherry garnish. Warm amber lighting, polished dark wood bar. Timeless and sophisticated, cinematic quality."),
    ("margarita_hero", "A classic Margarita in a salt-rimmed coupe glass, pale gold with a lime wheel garnish. Bright natural light, white marble surface, fresh limes and salt scattered artfully. Clean, fresh, inviting. Professional cocktail photography."),
    ("daiquiri_hero", "A classic Daiquiri in a chilled coupe glass, pale and frothy, lime wheel on rim. Bright white background, soft natural lighting. Simple, elegant, and refreshing. High-end cocktail photography."),
    ("whiskey_sour_hero", "A Whiskey Sour with a perfect frothy egg white foam top, Angostura bitters design on the foam, cherry and orange garnish. Rich amber glass. Warm moody lighting, dark wood bar. Artisan craft cocktail photography."),
    ("french_75_hero", "A French 75 in a tall champagne flute, pale gold bubbles rising, lemon twist spiraling down the glass. Elegant candlelit setting, celebration atmosphere. Luxurious and effervescent, editorial cocktail photography."),

    # ── My Bar feature ────────────────────────────────────────────────────────
    ("mybar_bottles", "A beautifully arranged home bar shelf with premium spirit bottles: bourbon, gin, rum, tequila, mezcal, Aperol, vermouth. Warm backlighting, bottles glowing. Sophisticated home interior, dark wood shelving. Lifestyle photography, aspirational home bar aesthetic."),
    ("mybar_discovery", "Close-up of elegant hands holding a modern iPhone displaying a cocktail recipe app with beautiful recipe cards visible. Premium lifestyle photography, soft bokeh background of a well-stocked home bar. Warm inviting light."),
    ("ingredients_flat_lay", "Overhead flat lay of cocktail ingredients on a dark marble surface: citrus fruits sliced open, herbs, sugar cubes, bitters bottles, a cocktail shaker. Artfully arranged, editorial food photography, rich colors and textures."),

    # ── Lifestyle / hosting ───────────────────────────────────────────────────
    ("hosting_dinner_party", "An elegant dinner party scene, beautifully set table with cocktails in various glasses, candles, flowers. Warm golden light, guests' hands reaching for drinks. Sophisticated entertaining, lifestyle photography."),
    ("share_menus_host", "A stylish host preparing cocktails for guests at a home bar, confidently mixing a drink while guests look on admiringly. Warm evening light, beautiful home interior. Aspirational lifestyle photography."),
    ("date_night_cocktails", "Two cocktail glasses clinking together in a romantic dimly lit setting. One Negroni, one Champagne coupe. Candlelight reflection, intimate atmosphere. Sophisticated date night aesthetic, professional photography."),
    ("backyard_summer", "Colorful cocktails on a wooden outdoor table in a sunny backyard: a bright Aperol Spritz, a Paloma, a tropical drink with umbrella. Summer vibes, green foliage background, golden afternoon light."),

    # ── Educational / feature ─────────────────────────────────────────────────
    ("citrus_garnish_technique", "Close-up of a bartender's hands expertly twisting a lemon peel over a cocktail glass, oils spraying visibly. Dark professional bar background, dramatic side lighting. Craft and technique, editorial quality."),
    ("ice_art", "A single large perfectly clear ice sphere being placed into an Old Fashioned glass with tongs. Crystal clarity of the ice, amber whiskey beneath. Macro photography, dramatic close-up, dark background."),
    ("herb_garden_cocktails", "Fresh herbs laid out beside cocktails: mint sprigs, rosemary, thyme, basil. A Mojito and a Gin & Tonic visible. Bright natural light, garden setting. Fresh and vibrant food photography."),
    ("cocktail_shaker_action", "A silver cocktail shaker mid-shake, motion blur on the hands, condensation forming on the metal. Dark moody bar background, dramatic lighting. Energy and craft, professional photography."),

    # ── Seasonal ──────────────────────────────────────────────────────────────
    ("winter_warm_cocktail", "A Hot Toddy in a glass mug with a cinnamon stick, lemon slice, and steam rising. Cozy fireplace in the background, warm amber tones, wool blanket visible. Winter comfort, lifestyle photography."),
    ("holiday_celebration", "Champagne flutes and a festive cocktail spread on a holiday-decorated table, fairy lights, pine cones, candles. Celebration atmosphere, warm gold tones. Holiday entertaining photography."),
    ("summer_pool_drinks", "Colorful tropical cocktails on the edge of a pool, condensation on the glasses, sparkling blue water. Summer vibes, sunshine, relaxed luxury. Lifestyle photography."),

    # ── Spirit education ──────────────────────────────────────────────────────
    ("whiskey_collection", "A curated collection of premium whiskey bottles on a wooden shelf: bourbon, scotch, rye, Irish whiskey. Warm amber backlighting, bottles glowing richly. Sophisticated spirits photography."),
    ("gin_botanicals", "A gin bottle surrounded by its botanicals: juniper berries, coriander, citrus peels, herbs. Artfully arranged on white marble. Clean editorial product photography with soft natural lighting."),
    ("tequila_agave", "Premium tequila bottle with agave plant in the background. Golden hour desert light, dramatic shadows. Authentic Mexican spirits photography, editorial quality."),
]

print(f"\n🎨 Generating {len(IMAGES)} images with gpt-image-2...\n")
generated = []
failed = []


def _generate(prompt: str) -> bytes:
    """Generate via gpt-image-2 (no fallback)."""
    r = client.images.generate(model=MODEL, prompt=prompt, size="1024x1024", n=1)
    return base64.b64decode(r.data[0].b64_json)


for slug, prompt in IMAGES:
    try:
        enhanced = (
            f"{prompt} "
            "Photorealistic, professional photography, high resolution, visually striking, "
            "suitable for Instagram. No watermarks, no text overlays. English only if any text."
        )
        image_bytes = _generate(enhanced)
        filename = f"{slug}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = OUT / filename
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        size_kb = filepath.stat().st_size // 1024
        print(f"  ✓ {slug} ({size_kb}KB)")
        generated.append(str(filepath))
        time.sleep(2)  # gentle pacing
    except Exception as e:
        print(f"  ✗ {slug}: {e}")
        failed.append(slug)
        time.sleep(5)

print(f"\n✅ Generated: {len(generated)} | Failed: {len(failed)}")
if failed:
    print(f"Failed: {failed}")
print(f"\nImages saved to: {OUT}")
print(f"Total bank size: {len(list(OUT.glob('*.png')))} images")
