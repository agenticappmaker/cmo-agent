"""
Generate a second image bank — specific named cocktails.
These give the content generator a deep pool of ready-to-use photorealistic images
so it never has to wait for generation mid-post.
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

# Specific named cocktails with precise visual descriptions
COCKTAILS = [
    ("paper_plane", "A Paper Plane cocktail in a chilled coupe glass — equal parts amber, bright yellow, and deep red layers creating a sunset gradient. Garnish-free, clean rim. Dark moody bar background, single dramatic spotlight, condensation on glass."),
    ("last_word", "A Last Word cocktail in a Nick & Nora glass — pale green, almost luminous from the Chartreuse. No garnish, crystal clear glass. Dark background, candlelight reflection in the liquid."),
    ("penicillin", "A Penicillin cocktail in a rocks glass over a large ice cube — smoky amber scotch float visible on top of the citrus base, candied ginger garnish on a cocktail pick. Warm dramatic bar lighting, dark wood surface."),
    ("naked_famous", "A Naked and Famous cocktail in a coupe glass — deep magenta-amber color, perfectly chilled. No garnish. Moody black background, single overhead light creating a halo effect on the liquid."),
    ("jungle_bird", "A Jungle Bird in a rocks glass or tiki mug — dark rum and Campari creating a deep red-brown color, pineapple wedge and cherry garnish. Tropical bar setting, warm golden light, lush green plants in background."),
    ("bee_knees", "A Bee's Knees cocktail in a coupe glass — pale golden yellow, foam-free surface, lemon twist spiral garnish. Art deco bar setting, warm amber light, polished brass fixtures."),
    ("toronto", "A Toronto cocktail in a coupe glass — deep amber from the rye whiskey and Fernet-Branca, orange peel garnish twisted over the top. Sophisticated dark bar setting, candle reflection in glass."),
    ("clover_club", "A Clover Club cocktail in a coupe glass — pale pink from raspberry syrup, silky egg white foam on top, three raspberries as garnish. Elegant feminine bar setting, rose gold tones, soft light."),
    ("trinidad_sour", "A Trinidad Sour in a coupe glass — vivid orange-red from the Angostura bitters, frothy from the egg white, complex and jewel-toned. Dark background, dramatic lighting highlighting the color."),
    ("oaxacan_old_fashioned", "An Oaxacan Old Fashioned in a lowball glass with one large ice cube — smoky amber with mezcal float visible, orange peel and chocolate bitters foam on top. Dark mezcaleria setting, warm amber glow."),
    ("corpse_reviver", "A Corpse Reviver #2 in a coupe glass — pale crystal clear with citrus tones, absinthe rinse leaving oily sheen on glass. Art deco 1920s bar atmosphere, dramatic black and white contrast with warm amber accents."),
    ("aviation", "An Aviation cocktail in a coupe glass — pale lavender-blue color from crème de violette, maraschino cherry garnish. Clean elegant bar setting, natural daylight, delicate and beautiful."),
    ("dark_stormy", "A Dark and Stormy in a highball glass with ice — dramatic layering of dark rum floating on golden ginger beer, lime wedge on rim. Nautical bar setting, warm tropical light."),
    ("moscow_mule", "A Moscow Mule in a traditional hammered copper mug — bubbles rising in ginger beer, fresh mint sprig and lime wedge. Bright natural light, rustic wooden surface, condensation on the copper."),
    ("paloma", "A Paloma in a tall glass with a salted rim — pale pink from grapefruit soda, grapefruit wedge and rosemary sprig garnish. Bright Mexican cantina setting, warm afternoon sun, terracotta tones."),
    ("blood_sand", "A Blood and Sand cocktail in a coupe glass — deep red-orange jewel tones from the cherry heering and blood orange, cherry garnish. Dramatic dark background, single spotlight making the color glow."),
    ("gimlet", "A Gimlet in a coupe glass — bright lime green, perfectly clear, lime wheel on the rim. Clean modern bar setting, bright natural light, minimalist aesthetic."),
    ("sidecar", "A Sidecar in a sugar-rimmed coupe glass — deep amber-gold from the cognac, lemon twist spiral. Parisian brasserie setting, warm candlelight, elegant vintage atmosphere."),
    ("bramble", "A Bramble on crushed ice in a rocks glass — deep purple-red from the crème de mûre drizzle over gin and lemon, fresh blackberries and lemon slice garnish. Modern cocktail bar, soft moody lighting."),
    ("spritz", "A Venetian Spritz in a large wine glass — vivid orange Aperol, prosecco bubbles rising, large orange slice and green olive on pick. Outdoor Italian café terrace, golden sunset light, Mediterranean atmosphere."),
]

BASE_SUFFIX = (
    "Photorealistic professional cocktail photography, high resolution, editorial quality. "
    "CRITICAL: Absolutely NO text, words, writing, labels, or readable characters anywhere. "
    "No non-English script of any kind. No watermarks. "
    "Shoot as a world-class beverage photographer: perfect lighting, beautiful composition, magazine-worthy."
)

print(f"\n🍸 Generating {len(COCKTAILS)} named cocktail images with gpt-image-2...\n")
generated, failed = [], []


def _generate(prompt: str) -> bytes:
    r = client.images.generate(model=MODEL, prompt=prompt, size="1024x1024", n=1)
    return base64.b64decode(r.data[0].b64_json)


for slug, prompt in COCKTAILS:
    try:
        image_bytes = _generate(f"{prompt} {BASE_SUFFIX}")
        filename = f"{slug}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = OUT / filename
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        size_kb = filepath.stat().st_size // 1024
        print(f"  ✓ {slug} ({size_kb}KB)")
        generated.append(slug)
        time.sleep(2)
    except Exception as e:
        print(f"  ✗ {slug}: {e}")
        failed.append(slug)
        time.sleep(5)

print(f"\n✅ Generated: {len(generated)} | Failed: {len(failed)}")
print(f"Bank total: {len(list(OUT.glob('*.png')))} images")
