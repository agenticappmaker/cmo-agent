"""
Image Generator — uses Imagen 3 (Google) to create post images from prompts.
"""

import os
import requests
from pathlib import Path
from datetime import datetime


def generate_image(image_prompt: str, brand_slug: str, post_id: str) -> str:
    """
    Generate an image using Imagen 3 via Google AI.
    Returns the local file path of the saved image.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    enhanced_prompt = (
        f"{image_prompt}. "
        "Photorealistic professional food and drink photography, high resolution, visually striking, "
        "suitable for Instagram. Shot by a professional photographer with beautiful natural or studio lighting. "
        "CRITICAL: Absolutely NO text, NO words, NO letters, NO numbers, NO writing anywhere in the image. "
        "NO phones, NO screens, NO devices, NO UI elements, NO app interfaces. "
        "NO watermarks, NO logos, NO brand names. NO non-English characters. "
        "The image must contain ONLY physical real-world objects — drinks, ingredients, glassware, bar scenes, food."
    )

    response = client.models.generate_images(
        model="imagen-4.0-ultra-generate-001",
        prompt=enhanced_prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="1:1",
            output_mime_type="image/png",
        ),
    )

    image_bytes = response.generated_images[0].image.image_bytes

    output_dir = Path(__file__).parent.parent / "posts" / "images" / brand_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{post_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = output_dir / filename

    with open(filepath, "wb") as f:
        f.write(image_bytes)

    print(f"✓ Image saved: {filepath}")
    return str(filepath)
