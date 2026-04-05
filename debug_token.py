"""Check Meta token, pages, and Instagram account."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.environ["META_ACCESS_TOKEN"]

# Check token info
print("=== Token Info ===")
r = requests.get(
    "https://graph.facebook.com/v19.0/me",
    params={"fields": "id,name", "access_token": token}
)
print(r.json())

# Get pages managed by this user
print("\n=== My Pages (me/accounts) ===")
r2 = requests.get(
    "https://graph.facebook.com/v19.0/me/accounts",
    params={"access_token": token}
)
data = r2.json()
print(data)

# If pages found, show their Instagram accounts
if "data" in data and data["data"]:
    for page in data["data"]:
        print(f"\n=== Instagram account for page: {page['name']} ({page['id']}) ===")
        r3 = requests.get(
            f"https://graph.facebook.com/v19.0/{page['id']}",
            params={
                "fields": "instagram_business_account",
                "access_token": page["access_token"],
            }
        )
        print(r3.json())
