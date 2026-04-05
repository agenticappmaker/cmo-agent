#!/usr/bin/env python3
"""
CMO Agent — Autonomous social media content generation and publishing.

Usage:
  python main.py generate <brand> [--platform instagram|tiktok]
  python main.py plan <brand> [--days 7]
  python main.py queue
  python main.py run        # publish all due posts
  python main.py daemon     # run continuously, publish on schedule
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def cmd_generate(brand: str, platform: str):
    """Generate a post, create the image, and add to queue."""
    from agents.content_generator import generate_post
    from agents.image_generator import generate_image
    from agents.scheduler import add_to_queue

    print(f"\n🤖 Generating {platform} post for {brand}...")
    post = generate_post(brand, platform)

    print(f"\n📝 Post idea: {post['post_idea']}")
    print(f"   Pillar: {post['pillar']}")
    print(f"   Caption preview: {post['caption'][:100]}...")
    print(f"   Reasoning: {post.get('reasoning', '')}")

    print(f"\n🎨 Generating image...")
    post_id = f"{brand}_{platform}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    image_path = generate_image(post["image_prompt"], brand, post_id)

    print(f"\n📅 Adding to queue...")
    entry = add_to_queue(post, brand, platform, image_path)

    print(f"\n✅ Done! Post queued for {entry['scheduled_at'][:16]}")
    print(f"   Caption: {post['caption']}")
    print(f"   Tags: {post['hashtags']}")
    print(f"   Image: {image_path}")


def cmd_plan(brand: str, days: int):
    """Plan a content calendar for the next N days."""
    from agents.content_generator import build_future_prompts

    print(f"\n🤖 Planning {days} days of content for {brand}...")
    plans = build_future_prompts(brand, days)

    print(f"\n📅 Content Calendar:")
    for p in plans:
        print(f"  Day {p['day']} [{p['platform']}] — {p['pillar']}: {p['post_idea']}")
        print(f"    Hook: {p['hook']}")


def cmd_queue():
    """Show the current post queue."""
    from agents.scheduler import show_queue
    show_queue()


def cmd_run():
    """Publish all posts that are currently due."""
    from agents.scheduler import get_due_posts, mark_published, mark_failed
    from agents.publisher import upload_image_to_imgbb, publish_instagram, publish_tiktok

    due = get_due_posts()
    if not due:
        print("No posts due for publishing.")
        return

    print(f"\n📤 Publishing {len(due)} post(s)...")

    for post in due:
        print(f"\n→ {post['brand']} / {post['platform']}: {post['post_idea']}")
        try:
            from agents.content_generator import load_brand
            config = load_brand(post["brand"])["config"]
            platform = post["platform"]

            if platform in ("instagram", "facebook"):
                from agents.publisher import publish_facebook
                account_id = config.get("instagram_account_id", "")
                page_id = config.get("facebook_page_id", "")
                image_url = upload_image_to_imgbb(post["image_path"])

                ig_pid = None
                fb_pid = None

                if account_id:
                    ig_pid = publish_instagram(post["caption"], post["hashtags"], image_url, account_id)
                else:
                    print("  ⚠ No instagram_account_id in brand config. Skipping Instagram.")

                if page_id:
                    fb_pid = publish_facebook(post["caption"], post["hashtags"], image_url, page_id)
                else:
                    print("  ⚠ No facebook_page_id in brand config. Skipping Facebook.")

                mark_published(post["id"], ig_pid or fb_pid or "")

            elif platform == "linkedin":
                from agents.publisher import publish_linkedin
                org_urn = config.get("linkedin_org_urn", "")
                if not org_urn:
                    print("  ⚠ No linkedin_org_urn in brand config. Skipping.")
                    continue
                pid = publish_linkedin(post["caption"], post["hashtags"], post["image_path"], org_urn)
                mark_published(post["id"], pid)

            elif platform == "twitter":
                from agents.publisher import publish_twitter
                pid = publish_twitter(post["caption"], post["hashtags"], post["image_path"])
                mark_published(post["id"], pid)

            elif platform == "tiktok":
                open_id = config.get("tiktok_open_id", "")
                if not open_id:
                    print("  ⚠ No tiktok_open_id in brand config. Skipping.")
                    continue
                pid = publish_tiktok(post["caption"], post["image_path"], open_id)
                mark_published(post["id"], pid)

            else:
                print(f"  ⚠ Unknown platform '{platform}'. Skipping.")

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            mark_failed(post["id"], str(e))


def cmd_post_now(brand: str, platform: str):
    """Generate a post and publish it immediately (used by cron)."""
    from agents.content_generator import generate_post
    from agents.image_generator import generate_image
    from agents.publisher import upload_image_to_imgbb, publish_instagram, publish_tiktok
    from agents.content_generator import load_brand

    print(f"\n🤖 Generating {platform} post for {brand}...")
    post = generate_post(brand, platform)

    print(f"\n📝 Post idea: {post['post_idea']}")
    print(f"   Caption preview: {post['caption'][:100]}...")

    print(f"\n🎨 Generating image...")
    post_id = f"{brand}_{platform}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    image_path = generate_image(post["image_prompt"], brand, post_id)

    print(f"\n📤 Publishing now...")
    config = load_brand(brand)["config"]

    if platform in ("instagram", "facebook"):
        from agents.publisher import publish_facebook
        account_id = config.get("instagram_account_id", "")
        page_id = config.get("facebook_page_id", "")
        image_url = upload_image_to_imgbb(image_path)

        if account_id:
            ig_pid = publish_instagram(post["caption"], post["hashtags"], image_url, account_id)
            print(f"  ✓ Instagram: {ig_pid}")
        if page_id:
            fb_pid = publish_facebook(post["caption"], post["hashtags"], image_url, page_id)
            print(f"  ✓ Facebook: {fb_pid}")

    elif platform == "linkedin":
        from agents.publisher import publish_linkedin
        org_urn = config.get("linkedin_org_urn", "")
        pid = publish_linkedin(post["caption"], post["hashtags"], image_path, org_urn)
        print(f"  ✓ LinkedIn: {pid}")

    elif platform == "twitter":
        from agents.publisher import publish_twitter
        pid = publish_twitter(post["caption"], post["hashtags"], image_path)
        print(f"  ✓ Twitter: {pid}")

    print(f"\n✅ Posted! Caption: {post['caption'][:120]}...")


def cmd_daemon(brand: str, platform: str):
    """
    Run continuously — generate and publish posts at 9am and 7pm daily.
    Each post spotlights a unique cocktail recipe.
    """
    import schedule

    def generate_and_publish():
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Generating post...")
        cmd_generate(brand, platform)
        cmd_run()

    def publish_job():
        cmd_run()

    # Generate + publish at 9am and 7pm
    schedule.every().day.at("09:00").do(generate_and_publish)
    schedule.every().day.at("19:00").do(generate_and_publish)
    # Check for due posts every 5 minutes (catches any that were queued ahead)
    schedule.every(5).minutes.do(publish_job)

    print(f"\n🤖 CMO Agent daemon running for {brand} / {platform}")
    print("   Posts daily at 09:00 and 19:00")
    print("   Each post spotlights a unique cocktail recipe")
    print("   Press Ctrl+C to stop\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


def main():
    parser = argparse.ArgumentParser(description="CMO Agent — Autonomous social media AI")
    subparsers = parser.add_subparsers(dest="command")

    gen = subparsers.add_parser("generate", help="Generate and queue a post")
    gen.add_argument("brand", help="Brand slug (e.g. spirit-library)")
    gen.add_argument("--platform", default="instagram", choices=["instagram", "facebook", "linkedin", "twitter", "tiktok"])

    plan = subparsers.add_parser("plan", help="Plan a content calendar")
    plan.add_argument("brand", help="Brand slug")
    plan.add_argument("--days", type=int, default=7)

    subparsers.add_parser("queue", help="Show the post queue")
    subparsers.add_parser("run", help="Publish all due posts")

    postnow = subparsers.add_parser("post-now", help="Generate and publish immediately (for cron)")
    postnow.add_argument("brand", help="Brand slug (e.g. spirit-library)")
    postnow.add_argument("--platform", default="instagram", choices=["instagram", "facebook", "linkedin", "twitter", "tiktok"])

    daemon = subparsers.add_parser("daemon", help="Run continuously")
    daemon.add_argument("brand", help="Brand slug")
    daemon.add_argument("--platform", default="instagram", choices=["instagram", "facebook", "linkedin", "twitter", "tiktok"])

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args.brand, args.platform)
    elif args.command == "post-now":
        cmd_post_now(args.brand, args.platform)
    elif args.command == "plan":
        cmd_plan(args.brand, args.days)
    elif args.command == "queue":
        cmd_queue()
    elif args.command == "run":
        cmd_run()
    elif args.command == "daemon":
        cmd_daemon(args.brand, args.platform)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
