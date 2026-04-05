"""
Publisher — posts to Instagram, Facebook, LinkedIn, X (Twitter), and TikTok.
"""

import os
import base64
import requests
import json
from pathlib import Path


# ── Image hosting (imgbb) ─────────────────────────────────────────────────────

def upload_image_to_imgbb(image_path: str) -> str:
    """Upload a local image to catbox.moe and return the public URL.
    catbox.moe is reliably accessible by Meta's API crawlers."""
    resp = requests.post(
        "https://catbox.moe/user/api.php",
        data={"reqtype": "fileupload"},
        files={"fileToUpload": (Path(image_path).name, open(image_path, "rb"), "image/png")},
    )
    resp.raise_for_status()
    url = resp.text.strip()
    if not url.startswith("http"):
        raise ValueError(f"catbox upload failed: {url}")
    print(f"✓ Image hosted at: {url}")
    return url


# ── Instagram (Meta Graph API) ────────────────────────────────────────────────

def publish_instagram(caption: str, hashtags: str, image_url: str, account_id: str) -> str:
    """Publish an image post to Instagram. Returns post ID."""
    access_token = os.environ.get("META_PAGE_ACCESS_TOKEN") or os.environ["META_ACCESS_TOKEN"]
    full_caption = f"{caption}\n\n{hashtags}"

    container_resp = requests.post(
        f"https://graph.facebook.com/v19.0/{account_id}/media",
        data={"image_url": image_url, "caption": full_caption, "access_token": access_token},
    )
    if not container_resp.ok:
        raise ValueError(f"Instagram container error: {container_resp.status_code} — {container_resp.json()}")
    container_id = container_resp.json()["id"]

    # Wait for container to finish processing (up to 60s)
    import time
    for attempt in range(12):
        status_resp = requests.get(
            f"https://graph.facebook.com/v19.0/{container_id}",
            params={"fields": "status_code", "access_token": access_token}
        )
        status = status_resp.json().get("status_code", "")
        print(f"  Container status: {status}")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise ValueError(f"Instagram container processing failed: {status_resp.json()}")
        time.sleep(5)
    else:
        raise ValueError("Instagram container timed out — did not reach FINISHED status")

    publish_resp = requests.post(
        f"https://graph.facebook.com/v19.0/{account_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
    )
    if not publish_resp.ok:
        raise ValueError(f"Instagram publish error: {publish_resp.status_code} — {publish_resp.json()}")
    post_id = publish_resp.json()["id"]
    print(f"✓ Published to Instagram: {post_id}")
    return post_id


# ── Facebook (Meta Graph API — Page posts) ────────────────────────────────────

def publish_facebook(caption: str, hashtags: str, image_url: str, page_id: str) -> str:
    """Publish a photo post to a Facebook Page. Returns post ID."""
    access_token = os.environ.get("META_PAGE_ACCESS_TOKEN") or os.environ["META_ACCESS_TOKEN"]
    full_caption = f"{caption}\n\n{hashtags}"

    # Post photo to page feed
    resp = requests.post(
        f"https://graph.facebook.com/v19.0/{page_id}/photos",
        data={
            "url": image_url,
            "caption": full_caption,
            "access_token": access_token,
        },
    )
    if not resp.ok:
        raise ValueError(f"Facebook error: {resp.status_code} — {resp.json()}")
    post_id = resp.json().get("post_id") or resp.json().get("id", "")
    print(f"✓ Published to Facebook: {post_id}")
    return post_id


# ── LinkedIn (UGC Posts API) ──────────────────────────────────────────────────

def publish_linkedin(caption: str, hashtags: str, image_path: str, org_urn: str) -> str:
    """
    Publish an image post to a LinkedIn Organization page.
    org_urn format: 'urn:li:organization:123456789'
    Returns the LinkedIn post URN.
    """
    access_token = os.environ["LINKEDIN_ACCESS_TOKEN"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    # Step 1: Register image upload
    register_resp = requests.post(
        "https://api.linkedin.com/v2/assets?action=registerUpload",
        headers=headers,
        json={
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": org_urn,
                "serviceRelationships": [{
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }],
            }
        },
    )
    register_resp.raise_for_status()
    reg_data = register_resp.json()
    upload_url = reg_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    asset_urn = reg_data["value"]["asset"]

    # Step 2: Upload the image binary
    with open(image_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={"Authorization": f"Bearer {access_token}"},
            data=f.read(),
        )
    upload_resp.raise_for_status()

    # Step 3: Create the post
    full_text = f"{caption}\n\n{hashtags}"
    post_payload = {
        "author": org_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": full_text},
                "shareMediaCategory": "IMAGE",
                "media": [{
                    "status": "READY",
                    "description": {"text": caption[:200]},
                    "media": asset_urn,
                    "title": {"text": "Spirit Library"},
                }],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    post_resp = requests.post(
        "https://api.linkedin.com/v2/ugcPosts",
        headers=headers,
        json=post_payload,
    )
    post_resp.raise_for_status()
    post_urn = post_resp.headers.get("x-restli-id", post_resp.json().get("id", ""))
    print(f"✓ Published to LinkedIn: {post_urn}")
    return post_urn


# ── X / Twitter (API v2) ──────────────────────────────────────────────────────

def publish_twitter(caption: str, hashtags: str, image_path: str) -> str:
    """
    Publish a tweet with image to X (Twitter) using API v2.
    Requires OAuth 1.0a credentials in env.
    Returns the tweet ID.
    """
    try:
        import tweepy
    except ImportError:
        raise ImportError("Run: pip install tweepy")

    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )

    # Upload media via v1.1 API (v2 doesn't support media upload directly)
    auth = tweepy.OAuth1UserHandler(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_SECRET"],
    )
    api_v1 = tweepy.API(auth)
    media = api_v1.media_upload(filename=image_path)
    media_id = media.media_id

    # Tweet text: caption + hashtags, max 280 chars
    tweet_text = f"{caption}\n\n{hashtags}"
    if len(tweet_text) > 280:
        tweet_text = caption[:240] + "…\n" + hashtags[:30]

    response = client.create_tweet(text=tweet_text, media_ids=[media_id])
    tweet_id = response.data["id"]
    print(f"✓ Published to X/Twitter: {tweet_id}")
    return tweet_id


# ── TikTok (Content Posting API) ─────────────────────────────────────────────

def publish_tiktok(caption: str, image_path: str, open_id: str) -> str:
    """Publish a photo post to TikTok. Returns publish ID."""
    access_token = os.environ["TIKTOK_ACCESS_TOKEN"]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    payload = {
        "post_info": {
            "title": caption[:150],
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "photo_cover_index": 0,
            "photo_images": [],
        },
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }

    resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/content/init/",
        headers=headers,
        json=payload,
    )
    resp.raise_for_status()
    publish_id = resp.json().get("data", {}).get("publish_id", "")
    print(f"✓ TikTok publish initiated: {publish_id}")
    return publish_id
