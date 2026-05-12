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


def cmd_post_now(brand: str, platform: str, topic: str = None):
    """Generate a post and publish it immediately (used by cron).
    Series posts automatically become carousels on Instagram.

    Daily cap: if DAILY_POST_LIMIT posts already published today, the content is
    generated and queued for tomorrow instead of firing immediately.
    Queue drain: if a queued post is ready for this brand/platform, it is published
    instead of generating fresh content (so ideas added via `generate` get used).
    """
    from agents.content_generator import generate_post, generate_carousel_content
    from agents.image_generator import generate_image
    from agents.publisher import upload_image_to_imgbb, publish_instagram, publish_tiktok
    from agents.content_generator import load_brand
    from agents.scheduler import count_posts_today, DAILY_POST_LIMIT, get_due_posts, add_to_queue

    # --- Daily cap: if already at limit, queue instead of posting ---
    today_count = count_posts_today(brand)
    if today_count >= DAILY_POST_LIMIT:
        print(f"\n⚠ Daily post limit reached ({today_count}/{DAILY_POST_LIMIT} posts today for {brand}).")
        print(f"  Generating content and queuing for tomorrow instead...")
        post = generate_post(brand, platform, topic=topic)
        print(f"\n📝 Post idea: {post['post_idea']}")
        post_id = f"{brand}_{platform}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        image_path = generate_image(post["image_prompt"], brand, post_id)
        entry = add_to_queue(post, brand, platform, image_path)
        print(f"  ✓ Queued for {entry['scheduled_at'][:16]}")
        return

    # --- Queue drain: publish a pre-queued post if one is ready ---
    due = get_due_posts(brand=brand, platform=platform)
    if due:
        queued = due[0]
        print(f"\n📬 Using queued post: {queued['post_idea']}")
        config = load_brand(brand)["config"]
        from agents.scheduler import mark_published, mark_failed
        from agents.publisher import publish_facebook
        try:
            image_url = upload_image_to_imgbb(queued["image_path"])
            account_id = config.get("instagram_account_id", "")
            page_id = config.get("facebook_page_id", "")
            pid = None
            if account_id:
                pid = publish_instagram(queued["caption"], queued.get("hashtags", ""), image_url, account_id)
                print(f"  ✓ Instagram: {pid}")
            if page_id:
                fb_pid = publish_facebook(queued["caption"], queued.get("hashtags", ""), image_url, page_id)
                print(f"  ✓ Facebook: {fb_pid}")
            mark_published(queued["id"], pid or "")
            print(f"\n✅ Posted! Caption: {queued['caption'][:120]}...")
        except Exception as e:
            mark_failed(queued["id"], str(e))
            print(f"  ✗ Queued post failed ({e}), falling back to fresh generation...")
            # fall through to normal generation below
        else:
            return

    print(f"\n🤖 Generating {platform} post for {brand}..." + (f" [topic: {topic}]" if topic else ""))
    post = generate_post(brand, platform, topic=topic)

    print(f"\n📝 Post idea: {post['post_idea']}")
    print(f"   Caption preview: {post['caption'][:100]}...")

    config = load_brand(brand)["config"]

    # Series posts → carousel on Instagram
    if post.get("post_type") == "series" and platform in ("instagram", "facebook"):
        print(f"\n🎠 Building carousel slides...")
        try:
            from agents.slide_generator import build_carousel
            slides_data = generate_carousel_content(post)

            # Generate a marketing-grade title-slide background from Claude's
            # content-aware image prompt (new field added to the series schema).
            title_bg_path = None
            title_bg_prompt = post.get("title_slide_image_prompt")
            if title_bg_prompt:
                try:
                    title_bg_id = f"{brand}_{platform}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_titlebg"
                    print(f"\n🖼  Generating title-slide background...")
                    title_bg_path = generate_image(title_bg_prompt, brand, title_bg_id)
                except Exception as e:
                    print(f"  ⚠ Title bg generation failed ({e}); falling back to gradient")

            slide_paths = build_carousel(
                slides_data,
                series_name=post.get("series_name"),
                title_bg_image=title_bg_path,
            )
            print(f"  Generated {len(slide_paths)} slides")

            # Upload all slides
            slide_urls = []
            for sp in slide_paths:
                url = upload_image_to_imgbb(sp)
                slide_urls.append(url)

            # Publish as carousel
            account_id = config.get("instagram_account_id", "")
            page_id = config.get("facebook_page_id", "")

            if account_id and len(slide_urls) >= 2:
                from agents.publisher import publish_instagram_carousel
                ig_pid = publish_instagram_carousel(post["caption"], post.get("hashtags", ""), slide_urls, account_id)
                print(f"  ✓ Instagram carousel: {ig_pid}")

            # Facebook still gets single image (carousels more complex on FB)
            if page_id:
                from agents.publisher import publish_facebook
                fb_pid = publish_facebook(post["caption"], post.get("hashtags", ""), slide_urls[0], page_id)
                print(f"  ✓ Facebook: {fb_pid}")

            print(f"\n✅ Carousel posted! {len(slide_urls)} slides. Caption: {post['caption'][:100]}...")
            return
        except Exception as e:
            print(f"  ⚠ Carousel failed ({e}), falling back to single image...")

    # Infographic post → render locally, no AI image gen needed
    if post.get("post_type") == "infographic":
        print(f"\n📊 Rendering infographic...")
        from agents.slide_generator import render_infographic
        themes = ["classic", "warm", "cool"]
        theme = themes[datetime.utcnow().day % len(themes)]
        image_path = render_infographic(
            title=post.get("infographic_title", post.get("post_idea", "Spirit Library")),
            items=post.get("infographic_items", []),
            subtitle=post.get("infographic_subtitle") or None,
            theme=theme,
        )
        print(f"  ✓ Infographic saved: {image_path}")
    elif post.get("post_type") == "feature":
        # Feature posts: prefer a real app screenshot over a generated image
        import glob as _glob
        screenshots_dir = Path(__file__).parent / "screenshots"
        screenshots = [
            f for f in screenshots_dir.glob("*")
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".PNG")
            and f.parent == screenshots_dir  # exclude posted/ subfolder
        ] if screenshots_dir.exists() else []
        if screenshots:
            import random as _rand
            chosen = _rand.choice(screenshots)
            image_path = str(chosen)
            print(f"\n📱 Using app screenshot: {chosen.name}")
        else:
            print(f"\n🎨 Generating image (no screenshots available)...")
            post_id = f"{brand}_{platform}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            image_path = generate_image(post["image_prompt"], brand, post_id)
    else:
        # Single image post (recipes, series fallback)
        print(f"\n🎨 Generating image...")
        post_id = f"{brand}_{platform}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        image_path = generate_image(post["image_prompt"], brand, post_id)

    print(f"\n📤 Publishing now...")

    if platform in ("instagram", "facebook"):
        from agents.publisher import publish_facebook
        account_id = config.get("instagram_account_id", "")
        page_id = config.get("facebook_page_id", "")
        image_url = upload_image_to_imgbb(image_path)

        if account_id:
            ig_pid = publish_instagram(post["caption"], post.get("hashtags", ""), image_url, account_id)
            print(f"  ✓ Instagram: {ig_pid}")
        if page_id:
            fb_pid = publish_facebook(post["caption"], post.get("hashtags", ""), image_url, page_id)
            print(f"  ✓ Facebook: {fb_pid}")

    elif platform == "linkedin":
        from agents.publisher import publish_linkedin
        org_urn = config.get("linkedin_org_urn", "")
        pid = publish_linkedin(post["caption"], post.get("hashtags", ""), image_path, org_urn)
        print(f"  ✓ LinkedIn: {pid}")

    elif platform == "twitter":
        from agents.publisher import publish_twitter
        pid = publish_twitter(post["caption"], post.get("hashtags", ""), image_path)
        print(f"  ✓ Twitter: {pid}")

    print(f"\n✅ Posted! Caption: {post['caption'][:120]}...")


def cmd_post_screenshot(brand: str, platform: str, image_path: str = None):
    """Post a user-provided screenshot with an AI-generated caption."""
    from agents.content_generator import generate_screenshot_caption
    from agents.publisher import upload_image_to_imgbb, publish_instagram
    from agents.content_generator import load_brand

    screenshots_dir = Path(__file__).parent / "screenshots"

    # If no image_path given, find the newest screenshot in the drop folder
    if not image_path:
        images = sorted(
            [f for f in screenshots_dir.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")],
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        if not images:
            print("❌ No screenshots found in cmo-agent/screenshots/")
            print("   Drop a screenshot there and re-run, or pass --image /path/to/image.png")
            return
        image_path = str(images[0])
        print(f"📱 Using newest screenshot: {Path(image_path).name}")
    else:
        if not Path(image_path).exists():
            print(f"❌ Image not found: {image_path}")
            return

    print(f"\n🤖 Generating caption from screenshot for {brand}...")
    post = generate_screenshot_caption(brand, image_path, platform)

    print(f"\n📝 Post idea: {post['post_idea']}")
    print(f"   Caption preview: {post['caption'][:100]}...")

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

    print(f"\n✅ Posted! Caption: {post['caption'][:120]}...")

    # Move used screenshot to an "posted" subfolder so it's not reused
    posted_dir = screenshots_dir / "posted"
    posted_dir.mkdir(exist_ok=True)
    src = Path(image_path)
    dest = posted_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{src.name}"
    src.rename(dest)
    print(f"   📁 Screenshot moved to screenshots/posted/")


def cmd_daemon(brand: str, platform: str):
    """
    Run continuously — generate and publish ONE post at 9am (recipe) and ONE at 7pm (feature).
    Uses a daily cap and lock file to prevent double-posting.
    """
    import schedule
    from pathlib import Path

    LOCK_FILE = Path(__file__).parent / "posts" / ".post_lock"
    DAILY_LOG = Path(__file__).parent / "posts" / "daily_post_log.json"

    def _daily_count() -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        if DAILY_LOG.exists():
            log = json.load(open(DAILY_LOG))
            return log.get(today, 0)
        return 0

    def _increment_daily():
        today = datetime.now().strftime("%Y-%m-%d")
        log = json.load(open(DAILY_LOG)) if DAILY_LOG.exists() else {}
        log[today] = log.get(today, 0) + 1
        # Keep only last 7 days
        log = {k: v for k, v in sorted(log.items())[-7:]}
        json.dump(log, open(DAILY_LOG, "w"), indent=2)

    def generate_and_publish():
        """Generate exactly one post and publish it. Lock prevents concurrent runs."""
        if LOCK_FILE.exists():
            print(f"[{datetime.now().strftime('%H:%M')}] Lock file exists — skipping (another post in progress)")
            return

        if _daily_count() >= 2:
            print(f"[{datetime.now().strftime('%H:%M')}] Daily limit reached (2 posts) — skipping")
            return

        try:
            # Acquire lock
            LOCK_FILE.write_text(datetime.now().isoformat())
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Generating post ({_daily_count() + 1}/2 today)...")

            cmd_post_now(brand, platform)
            _increment_daily()

        except Exception as e:
            print(f"  ✗ Post failed: {e}")
        finally:
            # Always release lock
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()

    # Post 1 at 9am (recipe), Post 2 at 7pm (feature)
    schedule.every().day.at("09:00").do(generate_and_publish)
    schedule.every().day.at("19:00").do(generate_and_publish)

    print(f"\n🤖 CMO Agent daemon running for {brand} / {platform}")
    print("   Post 1: 09:00 — cocktail recipe")
    print("   Post 2: 19:00 — app feature showcase")
    print("   Max 2 posts per day, no repeats ever")
    print("   Press Ctrl+C to stop\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


def cmd_outreach(subcommand: str, args):
    """Dispatch outreach sub-commands."""
    if subcommand == "research":
        from agents.outreach_researcher import research_all_targets
        research_all_targets(
            force_refresh=getattr(args, "force", False),
            category_filter=getattr(args, "category", None)
        )

    elif subcommand == "draft":
        from agents.outreach_generator import draft_all_pitches
        draft_all_pitches(
            force_refresh=getattr(args, "force", False),
            category_filter=getattr(args, "category", None)
        )

    elif subcommand == "send-emails":
        from agents.outreach_emailer import send_all_emails
        send_all_emails(
            dry_run=getattr(args, "dry_run", False),
            delay_seconds=getattr(args, "delay", 90),
            limit=getattr(args, "limit", None)
        )

    elif subcommand == "show-dms":
        from agents.outreach_generator import show_dm_queue
        show_dm_queue(platform_filter=getattr(args, "platform", None))

    elif subcommand == "show-emails":
        from agents.outreach_generator import show_outbox
        show_outbox()

    elif subcommand == "mark-sent":
        from agents.outreach_emailer import mark_dm_sent
        handle = getattr(args, "handle", "").lstrip("@")
        mark_dm_sent(handle)

    elif subcommand == "status":
        from agents.outreach_emailer import outreach_status
        outreach_status()

    elif subcommand == "follow-up":
        from agents.outreach_followup import run_followups
        run_followups(
            dry_run=getattr(args, "dry_run", False),
            days=getattr(args, "days", 14)
        )

    elif subcommand == "summary":
        from agents.outreach_researcher import show_research_summary
        show_research_summary()

    else:
        print(f"Unknown outreach subcommand: {subcommand}")
        print("Available: research, draft, send-emails, show-dms, show-emails, mark-sent, follow-up, status, summary")


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
    postnow.add_argument("--topic", default=None, help="Optional theme override (e.g. 'frozen cocktails')")

    postss = subparsers.add_parser("post-screenshot", help="Post a screenshot with AI-generated caption")
    postss.add_argument("brand", help="Brand slug (e.g. spirit-library)")
    postss.add_argument("--platform", default="instagram", choices=["instagram", "facebook", "linkedin", "twitter", "tiktok"])
    postss.add_argument("--image", default=None, help="Path to screenshot (default: newest in screenshots/)")

    daemon = subparsers.add_parser("daemon", help="Run continuously")
    daemon.add_argument("brand", help="Brand slug")
    daemon.add_argument("--platform", default="instagram", choices=["instagram", "facebook", "linkedin", "twitter", "tiktok"])

    # ── Outreach commands ──────────────────────────────────────────────────────
    outreach = subparsers.add_parser("outreach", help="Partnership outreach: research, draft, send")
    outreach_sub = outreach.add_subparsers(dest="outreach_cmd")

    # research
    research_p = outreach_sub.add_parser("research", help="Research all targets via Claude + web search")
    research_p.add_argument("--force", action="store_true", help="Re-research even if cached")
    research_p.add_argument("--category", default=None, help="Only research targets from this file (e.g. brands, delivery, influencers)")

    # draft
    draft_p = outreach_sub.add_parser("draft", help="Generate tailored pitches for all researched targets")
    draft_p.add_argument("--force", action="store_true", help="Re-draft even if already drafted")
    draft_p.add_argument("--category", default=None, help="Only draft for this category/file")

    # send-emails
    send_p = outreach_sub.add_parser("send-emails", help="Send all email pitches via Gmail SMTP")
    send_p.add_argument("--dry-run", action="store_true", help="Preview emails without sending")
    send_p.add_argument("--delay", type=int, default=90, help="Seconds between emails (default 90)")
    send_p.add_argument("--limit", type=int, default=None, help="Max emails to send this run")

    # show-dms
    show_dms_p = outreach_sub.add_parser("show-dms", help="Print DM queue (copy-paste ready)")
    show_dms_p.add_argument("--platform", default=None, choices=["instagram", "tiktok"], help="Filter by platform")

    # show-emails
    outreach_sub.add_parser("show-emails", help="Print full email outbox")

    # mark-sent (for DMs you've manually sent)
    mark_p = outreach_sub.add_parser("mark-sent", help="Mark a DM as sent after you've manually sent it")
    mark_p.add_argument("handle", help="Instagram handle (with or without @)")

    # status
    outreach_sub.add_parser("status", help="Dashboard: research + draft + send progress")

    # follow-up
    followup_p = outreach_sub.add_parser("follow-up", help="Send follow-ups to non-responders (14-day window)")
    followup_p.add_argument("--dry-run", action="store_true", help="Preview without sending")
    followup_p.add_argument("--days", type=int, default=14, help="Days since original send (default 14)")

    # summary
    outreach_sub.add_parser("summary", help="Research summary by category")
    # ──────────────────────────────────────────────────────────────────────────

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args.brand, args.platform)
    elif args.command == "post-now":
        cmd_post_now(args.brand, args.platform, topic=getattr(args, 'topic', None))
    elif args.command == "post-screenshot":
        cmd_post_screenshot(args.brand, args.platform, args.image)
    elif args.command == "plan":
        cmd_plan(args.brand, args.days)
    elif args.command == "queue":
        cmd_queue()
    elif args.command == "run":
        cmd_run()
    elif args.command == "daemon":
        cmd_daemon(args.brand, args.platform)
    elif args.command == "outreach":
        if not args.outreach_cmd:
            outreach.print_help()
        else:
            cmd_outreach(args.outreach_cmd, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
