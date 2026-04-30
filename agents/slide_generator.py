"""
Slide Generator — Creates informative carousel slides for Instagram.

Each carousel has 3-6 content slides + 1 CTA slide (logo + "DOWNLOAD THE APP").
Slides are 1080x1350 (4:5 Instagram optimal ratio).

Visual language:
- Title slide opens with an AI-generated blurred background prompted from slide content
  (marketing-grade scroll-stopper) with gold title overlay.
- Content / bullet / recipe slides rotate between three palette themes so the
  carousel doesn't feel monotonous: warm (amber→burgundy), cool (midnight→navy),
  and classic gold (charcoal→black). Accent colors stay gold-family for brand consistency.
- CTA slide keeps the Spirit Library logo centered but replaces "FOLLOW FOR MORE"
  with a download-the-app push + App Store search hint.
"""

import os
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Canvas ────────────────────────────────────────────────────────────────────
SLIDE_W, SLIDE_H = 1080, 1350

# ── Palette ───────────────────────────────────────────────────────────────────
# Gold family — brightened from original (was (212,175,55))
GOLD = (230, 190, 70)                 # base gold
GOLD_BRIGHT = (255, 215, 100)         # headline gold — much brighter
GOLD_SOFT = (245, 210, 120)           # secondary gold
CREAM = (245, 235, 200)               # bright cream for body copy (replaces muted gold on body)
MUTED = (180, 150, 70)                # dimmer gold for tertiary

# Three theme gradients — (top, bottom) RGB
THEMES = {
    "classic": ((25, 20, 10), (5, 5, 5)),        # charcoal → near-black
    "warm":    ((70, 30, 15), (20, 10, 5)),      # deep amber → burgundy
    "cool":    ((15, 20, 45), (5, 8, 20)),       # midnight → navy
}
THEME_ORDER = ("classic", "warm", "cool")

LOGO_PATH = os.path.expanduser("~/Documents/spiritlibrary-mobile/assets/icon.png")
OUTPUT_DIR = Path(os.path.expanduser("~/cmo-agent/posts/images/spirit-library/carousels"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_font(size, bold=False):
    font_paths = [
        "/System/Library/Fonts/SFNSText.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    bold_paths = [
        "/System/Library/Fonts/SFNSTextBold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    paths = bold_paths + font_paths if bold else font_paths
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _gradient_bg(theme: str = "classic") -> Image.Image:
    """Vertical gradient between theme top/bottom colors."""
    top, bottom = THEMES.get(theme, THEMES["classic"])
    img = Image.new("RGB", (SLIDE_W, SLIDE_H), top)
    px = img.load()
    for y in range(SLIDE_H):
        t = y / (SLIDE_H - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(SLIDE_W):
            px[x, y] = (r, g, b)
    return img


def _draw_text_block(draw, text, x, y, max_width, font, color, line_spacing=1.4):
    lines = textwrap.wrap(text, width=int(max_width / (font.size * 0.55)))
    for line in lines:
        draw.text((x, y), line, font=font, fill=color)
        y += int(font.size * line_spacing)
    return y


def _draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.pieslice([x0, y0, x0 + 2*radius, y0 + 2*radius], 180, 270, fill=fill)
    draw.pieslice([x1 - 2*radius, y0, x1, y0 + 2*radius], 270, 360, fill=fill)
    draw.pieslice([x0, y1 - 2*radius, x0 + 2*radius, y1], 90, 180, fill=fill)
    draw.pieslice([x1 - 2*radius, y1 - 2*radius, x1, y1], 0, 90, fill=fill)


def _prep_title_bg(bg_image_path: str) -> Image.Image:
    """Load user-supplied bg image, cover-crop to slide dims, blur, and darken."""
    src = Image.open(bg_image_path).convert("RGB")
    # Cover-crop
    src_ratio = src.width / src.height
    target_ratio = SLIDE_W / SLIDE_H
    if src_ratio > target_ratio:
        new_h = src.height
        new_w = int(new_h * target_ratio)
        left = (src.width - new_w) // 2
        src = src.crop((left, 0, left + new_w, new_h))
    else:
        new_w = src.width
        new_h = int(new_w / target_ratio)
        top = (src.height - new_h) // 2
        src = src.crop((0, top, new_w, top + new_h))
    src = src.resize((SLIDE_W, SLIDE_H), Image.LANCZOS)
    # Blur so text stays readable
    src = src.filter(ImageFilter.GaussianBlur(18))
    # Darkening overlay
    overlay = Image.new("RGB", (SLIDE_W, SLIDE_H), (0, 0, 0))
    return Image.blend(src, overlay, 0.55)


# ── Slide builders ────────────────────────────────────────────────────────────

def generate_title_slide(title, subtitle, bg_image_path=None, series_name=None):
    """
    Slide 1: hero marketing grab.
    - If bg_image_path given, use blurred+darkened generated image as background.
    - Otherwise falls back to a warm gradient.
    """
    if bg_image_path and os.path.exists(bg_image_path):
        img = _prep_title_bg(bg_image_path)
    else:
        img = _gradient_bg("warm")

    draw = ImageDraw.Draw(img)

    # Series badge at top
    if series_name:
        badge_font = _get_font(28, bold=True)
        badge_text = series_name.upper()
        bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        bw = bbox[2] - bbox[0] + 50
        bx = (SLIDE_W - bw) // 2
        _draw_rounded_rect(draw, (bx, 260, bx + bw, 312), 16, (0, 0, 0))
        _draw_rounded_rect(draw, (bx + 2, 262, bx + bw - 2, 310), 14, (40, 30, 10))
        draw.text((bx + 25, 269), badge_text, font=badge_font, fill=GOLD_BRIGHT)

    # Accent bar above title
    draw.rectangle([80, 420, 360, 428], fill=GOLD_BRIGHT)

    # Big bright-gold title
    title_font = _get_font(92, bold=True)
    y = 460
    y = _draw_text_block(draw, title, 80, y, SLIDE_W - 160, title_font, GOLD_BRIGHT)

    # Subtitle — cream for readability over photo bg
    y += 30
    sub_font = _get_font(40)
    _draw_text_block(draw, subtitle, 80, y, SLIDE_W - 160, sub_font, CREAM)

    return img


def generate_content_slide(heading, body_text, number=None, theme="classic"):
    """Content slide with gradient bg + theme-rotating accents."""
    img = _gradient_bg(theme)
    draw = ImageDraw.Draw(img)

    y = 200

    # Big number watermark
    if number is not None:
        num_font = _get_font(220, bold=True)
        # Subtle ghosted number — theme-tinted
        ghost = {"classic": (40, 32, 10), "warm": (90, 45, 20), "cool": (25, 35, 70)}[theme]
        draw.text((60, 70), str(number), font=num_font, fill=ghost)
        y = 320

    # Heading — bright gold
    head_font = _get_font(74, bold=True)
    y = _draw_text_block(draw, heading, 80, y, SLIDE_W - 160, head_font, GOLD_BRIGHT)
    y += 40

    # Accent line under heading
    draw.rectangle([80, y, 260, y + 6], fill=GOLD)
    y += 50

    # Body — cream (much more readable than old dim gold)
    body_font = _get_font(44)
    _draw_text_block(draw, body_text, 80, y, SLIDE_W - 160, body_font, CREAM, line_spacing=1.5)

    return img


def generate_bullet_slide(heading, bullets, theme="classic"):
    """Heading + bullets — theme-aware bg."""
    img = _gradient_bg(theme)
    draw = ImageDraw.Draw(img)

    # Heading
    head_font = _get_font(70, bold=True)
    y = 200
    y = _draw_text_block(draw, heading, 80, y, SLIDE_W - 160, head_font, GOLD_BRIGHT)

    # Accent line
    draw.rectangle([80, y + 10, 260, y + 16], fill=GOLD)
    y += 70

    # Bullets
    bullet_font = _get_font(46)
    for bullet in bullets[:4]:
        draw.text((80, y), "◆", font=_get_font(32), fill=GOLD_BRIGHT)
        y = _draw_text_block(draw, bullet, 140, y, SLIDE_W - 220, bullet_font, CREAM, line_spacing=1.35)
        y += 30

    return img


def generate_recipe_slide(cocktail_name, ingredients, glass=None, garnish=None, theme="warm"):
    """Recipe card — warm theme default, cocktail-forward."""
    img = _gradient_bg(theme)
    draw = ImageDraw.Draw(img)

    # Soft glow card
    card_color = {"classic": (20, 18, 8), "warm": (45, 20, 10), "cool": (15, 20, 40)}[theme]
    _draw_rounded_rect(draw, (50, 90, SLIDE_W - 50, SLIDE_H - 90), 28, card_color)

    # Cocktail name
    name_font = _get_font(74, bold=True)
    y = 200
    y = _draw_text_block(draw, cocktail_name, 100, y, SLIDE_W - 200, name_font, GOLD_BRIGHT)
    y += 20

    # Gold underline
    draw.rectangle([100, y, 520, y + 6], fill=GOLD_BRIGHT)
    y += 50

    # Ingredients
    ing_font = _get_font(42)
    for ing in ingredients[:6]:
        draw.text((100, y), "◆", font=_get_font(26), fill=GOLD_BRIGHT)
        draw.text((140, y), ing, font=ing_font, fill=CREAM)
        y += 62

    # Glass & garnish
    if glass or garnish:
        y += 30
        detail_font = _get_font(34)
        if glass:
            draw.text((100, y), f"🥃 {glass}", font=detail_font, fill=GOLD_SOFT)
            y += 50
        if garnish:
            draw.text((100, y), f"🍋 {garnish}", font=detail_font, fill=GOLD_SOFT)

    return img


def generate_cta_slide():
    """Final slide: logo + DOWNLOAD THE APP + App Store hint."""
    img = _gradient_bg("warm")
    draw = ImageDraw.Draw(img)

    # Load and paste logo (centered, LARGE)
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo_size = 500
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        lx = (SLIDE_W - logo_size) // 2
        ly = 200
        img.paste(logo, (lx, ly), logo)
    except Exception as e:
        print(f"  ⚠ Could not load logo: {e}")

    # "Spirit Library"
    brand_font = _get_font(76, bold=True)
    text = "Spirit Library"
    bbox = draw.textbbox((0, 0), text, font=brand_font)
    tw = bbox[2] - bbox[0]
    draw.text(((SLIDE_W - tw) // 2, 760), text, font=brand_font, fill=GOLD_BRIGHT)

    # "DOWNLOAD THE APP" — primary CTA
    cta_font = _get_font(56, bold=True)
    cta_text = "DOWNLOAD THE APP"
    bbox2 = draw.textbbox((0, 0), cta_text, font=cta_font)
    fw = bbox2[2] - bbox2[0]
    # Pill background behind CTA
    pill_pad_x, pill_pad_y = 50, 22
    pill_x0 = (SLIDE_W - fw) // 2 - pill_pad_x
    pill_x1 = (SLIDE_W + fw) // 2 + pill_pad_x
    _draw_rounded_rect(draw, (pill_x0, 860, pill_x1, 860 + cta_font.size + pill_pad_y * 2), 32, GOLD_BRIGHT)
    draw.text(((SLIDE_W - fw) // 2, 860 + pill_pad_y), cta_text, font=cta_font, fill=(15, 10, 5))

    # Sub-CTA
    sub_font = _get_font(34)
    sub_text = "Free on the App Store — search \"Spirit Library\""
    bbox3 = draw.textbbox((0, 0), sub_text, font=sub_font)
    aw = bbox3[2] - bbox3[0]
    draw.text(((SLIDE_W - aw) // 2, 1000), sub_text, font=sub_font, fill=CREAM)

    # URL hint
    url_font = _get_font(26)
    url_text = "spiritlibrary.app"
    bbox4 = draw.textbbox((0, 0), url_text, font=url_font)
    uw = bbox4[2] - bbox4[0]
    draw.text(((SLIDE_W - uw) // 2, 1060), url_text, font=url_font, fill=GOLD_SOFT)

    # Gold accent line
    line_w = 300
    draw.rectangle([(SLIDE_W - line_w) // 2, 1130, (SLIDE_W + line_w) // 2, 1136], fill=GOLD_BRIGHT)

    return img


# ── Infographic (single-image list post) ──────────────────────────────────────

def render_infographic(title: str, items: list, footer: str = None, theme: str = "classic",
                       subtitle: str = None) -> str:
    """
    Build a single 1080x1350 list-style infographic and save to disk.
    items: list of dicts {name, description} OR plain strings.
    Returns the saved image path.
    """
    import time
    img = _gradient_bg(theme)
    draw = ImageDraw.Draw(img)

    # Top accent
    draw.rectangle([80, 110, 240, 118], fill=GOLD_BRIGHT)

    # Brand label
    brand_font = _get_font(28, bold=True)
    draw.text((80, 130), "SPIRIT LIBRARY", font=brand_font, fill=GOLD_SOFT)

    # Title
    title_font = _get_font(72, bold=True)
    y = _draw_text_block(draw, title, 80, 180, SLIDE_W - 160, title_font, GOLD_BRIGHT, line_spacing=1.15)

    if subtitle:
        sub_font = _get_font(34)
        y = _draw_text_block(draw, subtitle, 80, y + 8, SLIDE_W - 160, sub_font, CREAM, line_spacing=1.3)

    y += 40
    draw.rectangle([80, y, 280, y + 6], fill=GOLD)
    y += 50

    n = min(len(items), 6)
    avail_h = (SLIDE_H - 180) - y
    row_h = max(88, avail_h // max(n, 1))
    num_font = _get_font(46, bold=True)
    name_font = _get_font(40, bold=True)
    desc_font = _get_font(30)

    for i, item in enumerate(items[:n]):
        if isinstance(item, dict):
            name = item.get("name") or item.get("title") or ""
            desc = item.get("description") or item.get("desc") or ""
        else:
            name = str(item)
            desc = ""
        # Numbered chip
        chip_x, chip_y = 80, y
        _draw_rounded_rect(draw, (chip_x, chip_y, chip_x + 70, chip_y + 70), 18, GOLD_BRIGHT)
        num = str(i + 1)
        nb = draw.textbbox((0, 0), num, font=num_font)
        nw = nb[2] - nb[0]
        draw.text((chip_x + (70 - nw) // 2, chip_y + 8), num, font=num_font, fill=(15, 10, 5))
        # Name + description
        draw.text((chip_x + 95, chip_y - 4), name, font=name_font, fill=CREAM)
        if desc:
            _draw_text_block(draw, desc, chip_x + 95, chip_y + 44, SLIDE_W - chip_x - 95 - 40,
                             desc_font, GOLD_SOFT, line_spacing=1.25)
        y += row_h

    # Footer
    foot_font = _get_font(30)
    foot_text = footer or "Find these and 1,700+ more in Spirit Library — free on the App Store"
    fb = draw.textbbox((0, 0), foot_text, font=foot_font)
    fw = fb[2] - fb[0]
    fy = SLIDE_H - 90
    if fw > SLIDE_W - 120:
        _draw_text_block(draw, foot_text, 80, fy - 20, SLIDE_W - 160, foot_font, GOLD_SOFT, line_spacing=1.25)
    else:
        draw.text(((SLIDE_W - fw) // 2, fy), foot_text, font=foot_font, fill=GOLD_SOFT)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR.parent / f"infographic_{timestamp}.jpg"
    img.save(str(path), "JPEG", quality=95)
    return str(path)


# ── Carousel builder ──────────────────────────────────────────────────────────

def build_carousel(slides_data, series_name=None, title_bg_image=None):
    """
    Build a full carousel from structured data.

    slides_data: list of dicts, each with:
      - type: "title", "content", "bullets", "recipe", "cta"
      - Plus type-specific fields (title, body_text, bullets, etc.)

    title_bg_image: optional path to an AI-generated image to use as the title
      slide's blurred background. Prompted from the carousel's content.

    Returns list of saved image file paths.
    """
    import time
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    paths = []

    # Content/bullet slides rotate themes for visual variety.
    theme_idx = 0

    for i, slide in enumerate(slides_data):
        stype = slide.get("type", "content")
        theme = THEME_ORDER[theme_idx % len(THEME_ORDER)]

        if stype == "title":
            img = generate_title_slide(
                slide["title"], slide.get("subtitle", ""),
                bg_image_path=title_bg_image, series_name=series_name,
            )
        elif stype == "content":
            img = generate_content_slide(slide["heading"], slide["body"], slide.get("number"), theme=theme)
            theme_idx += 1
        elif stype == "bullets":
            img = generate_bullet_slide(slide["heading"], slide["bullets"], theme=theme)
            theme_idx += 1
        elif stype == "recipe":
            img = generate_recipe_slide(
                slide["cocktail_name"], slide["ingredients"],
                slide.get("glass"), slide.get("garnish"),
                theme="warm",
            )
        elif stype == "cta":
            img = generate_cta_slide()
        else:
            continue

        path = OUTPUT_DIR / f"carousel_{timestamp}_slide{i+1}.jpg"
        img.save(str(path), "JPEG", quality=95)
        paths.append(str(path))

    return paths


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    slides = [
        {"type": "title", "title": "The Dry Shake", "subtitle": "Master the technique behind silky cocktail foam"},
        {"type": "content", "heading": "What Is It?", "body": "Shaking your cocktail WITHOUT ice first so the egg white emulsifies into silky foam.", "number": 1},
        {"type": "bullets", "heading": "When To Use It", "bullets": [
            "Any cocktail with egg white or aquafaba",
            "Whiskey Sour, Clover Club, Ramos Gin Fizz",
            "Pisco Sour, Amaretto Sour, Gin Fizz",
        ]},
        {"type": "content", "heading": "Pro Tip", "body": "Reverse dry shake — shake with ice first, strain, then shake again without. Foam goes wild.", "number": 2},
        {"type": "recipe", "cocktail_name": "Classic Whiskey Sour", "ingredients": [
            "2 oz Bourbon", "1 oz Fresh Lemon Juice", "0.75 oz Simple Syrup", "1 Egg White"
        ], "glass": "Rocks Glass", "garnish": "Angostura bitters dots on foam"},
        {"type": "cta"},
    ]
    paths = build_carousel(slides, series_name="Technique Explorer")
    print(f"Generated {len(paths)} slides:")
    for p in paths:
        print(f"  {p}")
