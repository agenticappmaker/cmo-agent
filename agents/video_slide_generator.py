"""
Video Slide Generator — Creates Instagram Reels/carousel videos with stock bartending footage.

Downloads free cocktail/bartending clips from Pexels, overlays gold text on black.
Each series post becomes a video carousel or Reel.
"""

import os
import json
import subprocess
import urllib.request
import urllib.parse
import time
from pathlib import Path

PEXELS_API_KEY = "ffbzgAgNgb53v6dJVy5EiGGsdgt5wVd6LJ5E5HApvmIZkzcZZxFYCFct"
OUTPUT_DIR = Path(os.path.expanduser("~/cmo-agent/posts/videos/spirit-library"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = Path("/tmp/spirit-video-slides")
TEMP_DIR.mkdir(parents=True, exist_ok=True)
LOGO_PATH = os.path.expanduser("~/Documents/spiritlibrary-mobile/assets/icon.png")


def search_pexels_videos(query, per_page=5, orientation="portrait"):
    """Search Pexels for stock videos via curl (avoids SSL issues)."""
    params = urllib.parse.urlencode({
        "query": query,
        "per_page": per_page,
        "orientation": orientation,
    })
    url = f"https://api.pexels.com/videos/search?{params}"
    result = subprocess.run(
        ["curl", "-s", "-H", f"Authorization: {PEXELS_API_KEY}", url],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        return []
    data = json.loads(result.stdout)
    return data.get("videos", [])


def download_video(video_data, max_duration=15):
    """Download the best quality video file from Pexels video data. Returns local path."""
    files = video_data.get("video_files", [])
    # Prefer HD portrait/square
    best = None
    for f in files:
        w = f.get("width", 0)
        h = f.get("height", 0)
        if h >= 1080 and w <= h:  # Portrait or square
            best = f
            break
    if not best:
        # Fallback to any HD
        for f in files:
            if f.get("height", 0) >= 720:
                best = f
                break
    if not best and files:
        best = files[0]
    if not best:
        return None

    url = best["link"]
    ext = "mp4"
    local_path = TEMP_DIR / f"pexels_{video_data['id']}.{ext}"

    if not local_path.exists():
        print(f"  Downloading {url[:80]}...")
        subprocess.run(["curl", "-sL", "-o", str(local_path), url], timeout=60)

    return str(local_path)


def get_video_for_topic(topic):
    """Search and download a relevant bartending video."""
    # Try specific search first, then fallback to generic
    searches = [
        topic,
        f"cocktail {topic}",
        "bartender making cocktail",
        "cocktail pouring",
        "bar cocktail mixing",
    ]
    for query in searches:
        videos = search_pexels_videos(query, per_page=3)
        if videos:
            path = download_video(videos[0])
            if path:
                return path
    return None


def create_text_overlay_video(bg_video_path, text_lines, output_path, duration=5):
    """
    Overlay gold text on a stock video clip using ffmpeg.
    text_lines: list of {"text": str, "size": int, "y_offset": int}
    """
    # Build ffmpeg drawtext filters
    filters = []

    # Darken the background video for text readability
    filters.append("colorlevels=rimax=0.4:gimax=0.4:bimax=0.4")

    for i, line in enumerate(text_lines):
        text = line["text"].replace("'", "'\\''").replace(":", "\\:")
        size = line.get("size", 60)
        y = line.get("y", f"(h/2)+{(i - len(text_lines)//2) * 80}")
        color = line.get("color", "0xD4AF37")  # Gold

        filters.append(
            f"drawtext=text='{text}'"
            f":fontsize={size}"
            f":fontcolor={color}"
            f":x=(w-text_w)/2"
            f":y={y}"
            f":font=Helvetica-Bold"
            f":shadowcolor=black:shadowx=3:shadowy=3"
        )

    filter_str = ",".join(filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", bg_video_path,
        "-t", str(duration),
        "-vf", filter_str,
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  ffmpeg error: {result.stderr[:200]}")
        return False
    return True


def create_black_text_video(text_lines, output_path, duration=4):
    """Create a pure black background video with gold text (no stock footage needed)."""
    filters = [f"color=black:s=1080x1350:d={duration}"]

    for i, line in enumerate(text_lines):
        text = line["text"].replace("'", "'\\''").replace(":", "\\:")
        size = line.get("size", 70)
        y = line.get("y", str(300 + i * 100))
        color = line.get("color", "0xD4AF37")

        filters.append(
            f"drawtext=text='{text}'"
            f":fontsize={size}"
            f":fontcolor={color}"
            f":x=(w-text_w)/2"
            f":y={y}"
            f":font=Helvetica-Bold"
        )

    filter_str = "[0:v]" + ",".join(filters[1:]) if len(filters) > 1 else ""
    full_filter = filters[0] + "," + ",".join(filters[1:])

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", full_filter,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode == 0


def create_cta_video(output_path, duration=5):
    """Create the final CTA slide as video — black bg, logo area, gold text."""
    text_lines = [
        {"text": "Spirit Library", "size": 80, "y": "500"},
        {"text": "FOLLOW FOR MORE", "size": 55, "y": "620"},
        {"text": "Free on the App Store", "size": 35, "y": "720", "color": "0xAA8C32"},
    ]
    return create_black_text_video(text_lines, output_path, duration)


def concat_videos(video_paths, output_path):
    """Concatenate multiple video clips into one final video."""
    # Create concat file
    concat_file = TEMP_DIR / "concat_list.txt"
    with open(concat_file, "w") as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0


def build_video_carousel(slides_data, topic="cocktail", series_name=None):
    """
    Build a video from carousel slide data.
    Uses stock footage for the first slide, black+gold text for the rest.
    Returns path to final video.
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    segment_paths = []

    # Get a stock video for the background of slide 1
    print(f"  Searching Pexels for '{topic}' footage...")
    bg_video = get_video_for_topic(topic)

    for i, slide in enumerate(slides_data):
        stype = slide.get("type", "content")
        segment_path = str(TEMP_DIR / f"segment_{timestamp}_{i}.mp4")

        if stype == "title" and bg_video:
            # Title slide: stock footage with text overlay
            text_lines = [
                {"text": slide.get("title", ""), "size": 80, "y": "450"},
                {"text": slide.get("subtitle", ""), "size": 40, "y": "570", "color": "0xAA8C32"},
            ]
            if series_name:
                text_lines.insert(0, {"text": series_name.upper(), "size": 30, "y": "380", "color": "0xD4AF37"})
            if create_text_overlay_video(bg_video, text_lines, segment_path, duration=4):
                segment_paths.append(segment_path)
                continue

        if stype == "cta":
            if create_cta_video(segment_path):
                segment_paths.append(segment_path)
            continue

        # All other slides: black bg + gold text
        text_lines = []
        if stype == "content":
            heading = slide.get("heading", "")
            body = slide.get("body", "")
            num = slide.get("number")
            if num:
                text_lines.append({"text": str(num), "size": 140, "y": "200", "color": "0x1E1905"})
            text_lines.append({"text": heading, "size": 70, "y": "380"})
            text_lines.append({"text": body, "size": 42, "y": "500", "color": "0xAA8C32"})

        elif stype == "bullets":
            text_lines.append({"text": slide.get("heading", ""), "size": 65, "y": "200"})
            for j, b in enumerate(slide.get("bullets", [])[:4]):
                text_lines.append({"text": f"◆ {b}", "size": 44, "y": str(380 + j * 80), "color": "0xD4AF37"})

        elif stype == "recipe":
            text_lines.append({"text": slide.get("cocktail_name", ""), "size": 75, "y": "200"})
            for j, ing in enumerate(slide.get("ingredients", [])[:5]):
                text_lines.append({"text": f"◆ {ing}", "size": 40, "y": str(380 + j * 70), "color": "0xD4AF37"})
            g = slide.get("glass", "")
            if g:
                text_lines.append({"text": g, "size": 34, "y": str(380 + len(slide.get("ingredients", [])) * 70 + 40), "color": "0xAA8C32"})

        elif stype == "title":
            # Fallback title without video
            text_lines.append({"text": slide.get("title", ""), "size": 80, "y": "450"})
            text_lines.append({"text": slide.get("subtitle", ""), "size": 40, "y": "570", "color": "0xAA8C32"})

        if text_lines:
            if create_black_text_video(text_lines, segment_path, duration=4):
                segment_paths.append(segment_path)

    if not segment_paths:
        print("  No video segments created")
        return None

    # Concatenate all segments
    final_path = str(OUTPUT_DIR / f"reel_{timestamp}.mp4")
    print(f"  Concatenating {len(segment_paths)} segments...")
    if concat_videos(segment_paths, final_path):
        print(f"  ✓ Final video: {final_path}")
        return final_path
    return None


def build_video_from_images(slides_data, topic="cocktail", series_name=None):
    """
    Alternative approach: use PIL slide images + stock video clip.
    1. Generate gold-on-black text slides as images (using slide_generator.py)
    2. Download a stock bartending clip from Pexels
    3. Combine: stock clip intro → slide images as video frames → CTA
    Returns path to final video.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agents.slide_generator import build_carousel as build_image_slides

    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # Step 1: Build image slides
    print(f"  Building image slides...")
    image_paths = build_image_slides(slides_data, series_name=series_name)
    if not image_paths:
        return None

    # Step 2: Get stock footage for intro
    print(f"  Searching Pexels for '{topic}' footage...")
    bg_video = get_video_for_topic(topic)

    segments = []

    # Step 3: Trim stock clip to 3 seconds for intro (if available)
    if bg_video:
        intro_path = str(TEMP_DIR / f"intro_{timestamp}.mp4")
        cmd = [
            "ffmpeg", "-y", "-i", bg_video, "-t", "3",
            "-vf", "scale=1080:1350:force_original_aspect_ratio=increase,crop=1080:1350",
            "-c:v", "libx264", "-preset", "fast", "-an",
            "-pix_fmt", "yuv420p", intro_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            segments.append(intro_path)
            print(f"  ✓ Stock footage intro (3s)")

    # Step 4: Convert each image slide to a 4-second video segment
    for i, img_path in enumerate(image_paths):
        seg_path = str(TEMP_DIR / f"slide_{timestamp}_{i}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-t", "6",
            "-vf", "scale=1080:1350",
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-an",
            seg_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            segments.append(seg_path)

    if not segments:
        return None

    # Step 5: Concatenate all segments
    final_path = str(OUTPUT_DIR / f"reel_{timestamp}.mp4")
    print(f"  Concatenating {len(segments)} segments...")
    if concat_videos(segments, final_path):
        # Get duration
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", final_path],
            capture_output=True, text=True,
        )
        dur = probe.stdout.strip()
        print(f"  ✓ Final video: {final_path} ({dur}s)")
        return final_path
    return None


if __name__ == "__main__":
    slides = [
        {"type": "title", "title": "The Dry Shake", "subtitle": "Silky foam, every time"},
        {"type": "content", "heading": "What Is It?", "body": "Shake without ice first for perfect foam", "number": 1},
        {"type": "bullets", "heading": "Best For", "bullets": ["Whiskey Sour", "Clover Club", "Pisco Sour"]},
        {"type": "recipe", "cocktail_name": "Whiskey Sour", "ingredients": ["2 oz Bourbon", "1 oz Lemon", "0.75 oz Syrup", "1 Egg White"], "glass": "Rocks Glass"},
        {"type": "cta"},
    ]
    result = build_video_from_images(slides, topic="cocktail shaking", series_name="Technique Explorer")
    if result:
        print(f"\nDone! Video at: {result}")
        print(f"Preview: open {result}")
