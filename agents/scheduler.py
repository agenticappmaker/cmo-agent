"""
Scheduler — manages the post queue with randomized timing
so posts never look automated.
"""

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


QUEUE_PATH = Path(__file__).parent.parent / "posts" / "queue.json"
DAILY_POST_LIMIT = 2


def load_queue() -> list:
    if QUEUE_PATH.exists():
        with open(QUEUE_PATH) as f:
            return json.load(f)
    return []


def save_queue(queue: list):
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_PATH, "w") as f:
        json.dump(queue, f, indent=2)


def add_to_queue(post: dict, brand_slug: str, platform: str, image_path: str):
    """
    Add a post to the queue with a randomized scheduled time.
    Uses the brand's best_times config + random offset to avoid patterns.
    """
    from agents.content_generator import load_brand
    config = load_brand(brand_slug)["config"]

    best_times = config.get("best_times", {}).get(platform, ["12:00", "18:00"])
    chosen_time = random.choice(best_times)
    hour, minute = map(int, chosen_time.split(":"))

    # Add random offset of ±45 minutes so posts never go out at predictable times
    offset = random.randint(-45, 45)
    scheduled_dt = datetime.now().replace(
        hour=hour, minute=minute, second=0, microsecond=0
    ) + timedelta(minutes=offset)

    # If that time has already passed today, schedule for tomorrow
    if scheduled_dt < datetime.now():
        scheduled_dt += timedelta(days=1)

    queue = load_queue()
    entry = {
        "id": f"{brand_slug}_{platform}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "brand": brand_slug,
        "platform": platform,
        "caption": post.get("caption", ""),
        "hashtags": post.get("hashtags", ""),
        "image_path": image_path,
        "post_idea": post.get("post_idea", ""),
        "scheduled_at": scheduled_dt.isoformat(),
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
    }
    queue.append(entry)
    save_queue(queue)

    print(f"✓ Scheduled for {scheduled_dt.strftime('%Y-%m-%d %H:%M')} ({platform})")
    return entry


def count_posts_today(brand: str) -> int:
    """Count posts already generated/published for this brand today (local time)."""
    path = Path(__file__).parent.parent / "posts" / f"{brand}_history.json"
    if not path.exists():
        return 0
    with open(path) as f:
        history = json.load(f)
    today = datetime.now().date()
    count = 0
    for post in history:
        ts = post.get("generated_at", "")
        if not ts:
            continue
        try:
            post_date = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone().date()
            if post_date == today:
                count += 1
        except Exception:
            pass
    return count


def get_due_posts(brand: str = None, platform: str = None) -> list:
    """Return queued posts that are due to be published, optionally filtered by brand/platform."""
    queue = load_queue()
    now = datetime.now()
    return [
        p for p in queue
        if p["status"] == "queued"
        and datetime.fromisoformat(p["scheduled_at"]) <= now
        and (brand is None or p["brand"] == brand)
        and (platform is None or p["platform"] == platform)
    ]


def mark_published(post_id: str, platform_post_id: str = ""):
    queue = load_queue()
    for post in queue:
        if post["id"] == post_id:
            post["status"] = "published"
            post["published_at"] = datetime.utcnow().isoformat()
            post["platform_post_id"] = platform_post_id
    save_queue(queue)


def mark_failed(post_id: str, error: str):
    queue = load_queue()
    for post in queue:
        if post["id"] == post_id:
            post["status"] = "failed"
            post["error"] = error
    save_queue(queue)


def show_queue():
    queue = load_queue()
    if not queue:
        print("Queue is empty.")
        return
    print(f"\n{'ID':<40} {'Brand':<20} {'Platform':<12} {'Scheduled':<22} {'Status'}")
    print("-" * 110)
    for p in sorted(queue, key=lambda x: x["scheduled_at"]):
        print(
            f"{p['id']:<40} {p['brand']:<20} {p['platform']:<12} "
            f"{p['scheduled_at'][:16]:<22} {p['status']}"
        )
