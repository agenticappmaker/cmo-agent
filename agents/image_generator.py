"""
Image Generator — uses DALL-E to create post images from prompts.
"""

import os
import requests
from openai import OpenAI
from pathlib import Path
from datetime import datetime


def generate_image(image_prompt: str, brand_slug: str, post_id: str) -> str:
    """
    Generate an image using DALL-E 3.
    Returns the local file path of the saved image.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Enhance prompt for social media quality
    enhanced_prompt = (
        f"{image_prompt}. "
        "Professional photography style, high resolution, visually striking, "
        "suitable for Instagram. Cinematic lighting, rich colors, editorial quality."
    )

    response = client.images.generate(
        model="dall-e-3",
        prompt=enhanced_prompt,
        size="1024x1024",
        quality="hd",
        n=1,
    )

    image_url = response.data[0].url

    # Download and save locally
    img_data = requests.get(image_url).content
    output_dir = Path(__file__).parent.parent / "posts" / "images" / brand_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{post_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = output_dir / filename

    with open(filepath, "wb") as f:
        f.write(img_data)

    print(f"✓ Image saved: {filepath}")
    return str(filepath)
