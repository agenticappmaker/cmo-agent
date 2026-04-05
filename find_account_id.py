"""Run this to find your correct Instagram Business Account ID."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.environ["META_ACCESS_TOKEN"]

# Step 1: Get Facebook Pages
pages_resp = requests.get(
    "https://graph.facebook.com/v19.0/me/accounts",
    params={"access_token": token}
)
print("Facebook Pages:", pages_resp.json())

# Step 2: For each page, get connected Instagram account
data = pages_resp.json().get("data", [])
for page in data:
    page_id = page["id"]
    ig_resp = requests.get(
        f"https://graph.facebook.com/v19.0/{page_id}",
        params={"fields": "instagram_business_account", "access_token": token}
    )
    print(f"\nPage '{page['name']}' Instagram:", ig_resp.json())
