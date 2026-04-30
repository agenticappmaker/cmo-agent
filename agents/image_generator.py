"""
Image Generator — uses OpenAI gpt-image-2 to create post images from prompts.

Primary: gpt-image-2. Emergency fallback only: Imagen 4 Ultra (Google) — invoked
ONLY when gpt-image-2 returns a hard billing/rate cap (HTTP 400 billing_hard_limit
or 429 rate_limit). Memory rule `feedback_imagen_only.md` (2026-04-23) says no
casual fallback to OpenAI in bulk; this file is the inverse path — keep posts
shipping when OpenAI is capped, instead of crashing the scheduled run and
triggering retry-storms.
"""

import os
import base64
from pathlib import Path
from datetime import datetime


_PROMPT_GUARDRAILS = (
    "Photorealistic professional photography, high resolution, visually striking, suitable for Instagram. "
    "CRITICAL RULES: "
    "(1) Absolutely NO text, words, writing, labels, signs, or readable characters anywhere in the image. "
    "(2) If a smartphone or phone appears, it must be shown from a side or back angle, screen dark or facing away from camera — never show a phone screen with readable UI or text. "
    "(3) Zero non-English characters — no Chinese, Japanese, Korean, Arabic, Cyrillic, or any non-Latin script anywhere. "
    "(4) No watermarks, no logos, no brand names rendered as text. "
    "Shoot as a professional food/lifestyle photographer would: beautiful natural or studio lighting, perfect composition, award-winning editorial quality."
)

_MODEL = "gpt-image-2"
_BILLING_MARKERS = ("billing_hard_limit", "insufficient_quota", "rate_limit_exceeded")


def _save_bytes(image_bytes: bytes, brand_slug: str, post_id: str, suffix: str) -> str:
    output_dir = Path(__file__).parent.parent / "posts" / "images" / brand_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{post_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}{suffix}.png"
    filepath = output_dir / filename
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    print(f"✓ Image saved: {filepath}")
    return str(filepath)


def _imagen4_fallback(prompt: str, brand_slug: str, post_id: str) -> str:
    """Emergency fallback to Imagen 4 Ultra when OpenAI is capped."""
    from google import genai as genai_client

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY missing — cannot use Imagen 4 fallback")

    client = genai_client.Client(api_key=api_key)
    resp = client.models.generate_images(
        model="imagen-4.0-ultra-generate-001",
        prompt=prompt,
        config={"number_of_images": 1, "aspect_ratio": "1:1"},
    )
    img_bytes = resp.generated_images[0].image.image_bytes
    print("  ✓ Generated via imagen-4.0-ultra (OpenAI fallback)")
    return _save_bytes(img_bytes, brand_slug, post_id, "_imagen4")


def generate_image(image_prompt: str, brand_slug: str, post_id: str) -> str:
    """Generate an image. Tries OpenAI gpt-image-2 first; falls back to Imagen 4
    only on confirmed OpenAI billing/quota caps. Returns the local file path."""
    from openai import OpenAI

    enhanced_prompt = f"{image_prompt}. {_PROMPT_GUARDRAILS}"
    try:
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.images.generate(model=_MODEL, prompt=enhanced_prompt, size="1024x1024", n=1)
        image_bytes = base64.b64decode(resp.data[0].b64_json)
        print(f"  ✓ Generated via {_MODEL}")
        return _save_bytes(image_bytes, brand_slug, post_id, "")
    except Exception as e:
        msg = str(e).lower()
        is_capped = any(m in msg for m in _BILLING_MARKERS) or "billing hard limit" in msg
        if not is_capped:
            raise
        print(f"  ⚠ {_MODEL} capped ({e.__class__.__name__}); falling back to Imagen 4 Ultra")
        return _imagen4_fallback(enhanced_prompt, brand_slug, post_id)
