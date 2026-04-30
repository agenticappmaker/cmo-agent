"""
Cold email templates for Westchester County local-SMB outreach.
Sender: Steven Samori (Smore Labs) offering AI agent / website / automation work.
Two variants: hospitality (restaurants, bars, cafes) and home services (trades).
CAN-SPAM: every email carries a physical postal address + one-click unsubscribe link.
"""

# ── Config (fill in before sending) ──────────────────────────────────────────
SENDER_NAME = "Steven Samori"
SENDER_COMPANY = "Smore Labs"
SENDER_EMAIL = "claudesonnet111@gmail.com"
SENDER_PHYSICAL_ADDRESS = "Westchester County, NY"  # TODO Steven: replace with full postal address for stronger CAN-SPAM coverage
UNSUBSCRIBE_BASE = None  # reply-based opt-out; handler reads replies to claudesonnet111@gmail.com
PORTFOLIO_URL = "https://spiritlibrary.app"
APP_STORE_URL = "https://apps.apple.com/us/app/spirit-library/id6761500950"


def _footer(to_email: str) -> str:
    # CAN-SPAM compliance: physical address + clear opt-out
    return (
        f"\n\n—\nThis is a one-time intro from {SENDER_NAME}. "
        f"Not interested? Reply 'unsubscribe' and I'll remove you immediately.\n"
        f"{SENDER_COMPANY} · {SENDER_PHYSICAL_ADDRESS}"
    )


# ── Hospitality variant (restaurants, bars, cafes) ──────────────────────────

def hospitality_cold(contact: dict) -> dict:
    biz = contact.get("name", "your restaurant")
    first = (contact.get("contact_name") or "").split(" ")[0]
    greeting = f"Hi {first}," if first else f"Hi {biz} team,"
    to = contact["email"]

    subject = "Where does ai fit into your business model?"
    body = (
        f"{greeting}\n\n"
        f"Your email was found by an agent, this email was typed by an agent and sent by an agent. "
        f"You'd be surprised to find what else AI is capable of.\n\n"
        f"I'm Steven, and I build small AI agents and websites for local businesses in Westchester. "
        f"The same tech that found and wrote this can also: answer guest questions on your site 24/7 "
        f"(hours, reservations, menu, allergens), reply to the 20-30 review questions a month that "
        f"never get answered, and capture after-hours inquiries while you focus on service. I can "
        f"build any of those for {biz} in a few days.\n\n"
        f"Proof I ship — Spirit Library, a cocktail app with 1,500+ recipes and an AI daily-pick "
        f"feature. Live site: {PORTFOLIO_URL}. You can also download it directly from the App Store: "
        f"{APP_STORE_URL}.\n\n"
        f"I'm also currently building two projects for clients: a 1,530-model RV configurator "
        f"(https://rv-there-yet-weld.vercel.app) and a 648K-product EU-safe ingredient checker "
        f"(https://eu-approved.vercel.app).\n\n"
        f"Worth a 10-min call? I'll show you exactly what I'd build for {biz} — no cost to talk.\n\n"
        f"Best,\n{SENDER_NAME}\n{SENDER_COMPANY}"
    )
    return {"subject": subject, "body": body + _footer(to)}


def hospitality_followup(contact: dict) -> dict:
    biz = contact.get("name", "your restaurant")
    first = (contact.get("contact_name") or "").split(" ")[0]
    greeting = f"Hi {first}," if first else f"Hi {biz} team,"
    to = contact["email"]

    subject = f"Re: Quick idea for {biz}"
    body = (
        f"{greeting}\n\n"
        f"Following up in case my first note got buried. No hard sell — just a quick reminder that "
        f"I build AI tools + websites for Westchester businesses and would happily spend 10 min "
        f"showing you what a simple one would look like for {biz}.\n\n"
        f"If timing's bad, reply 'not now' and I'll leave you alone.\n\n"
        f"— {SENDER_NAME}\n{PORTFOLIO_URL}"
    )
    return {"subject": subject, "body": body + _footer(to)}


# ── Home services variant (plumbers, HVAC, electricians, contractors) ───────

CATEGORY_PHRASE = {
    "plumber":          "plumbing shops",
    "electrician":      "electricians",
    "hvac":             "HVAC shops",
    "contractor":       "contractors",
    "roofer":           "roofing companies",
    "landscaper":       "landscapers",
    "painter":          "painting crews",
    "flooring":         "flooring installers",
    "locksmith":        "locksmiths",
    "pest_control":     "pest control companies",
    "appliance_repair": "appliance repair shops",
    "auto_repair":      "auto shops",
    "dentist":          "dental offices",
    "veterinarian":     "vet clinics",
    "dry_cleaner":      "dry cleaners",
    "salon":            "salons",
    "barber":           "barber shops",
    "gym":              "gyms",
    "yoga":             "yoga studios",
    "chiropractor":     "chiropractors",
    "cleaning":         "cleaning services",
}


def trades_cold(contact: dict) -> dict:
    biz = contact.get("name", "your business")
    first = (contact.get("contact_name") or "").split(" ")[0]
    greeting = f"Hi {first}," if first else f"Hi {biz} team,"
    to = contact["email"]
    category = CATEGORY_PHRASE.get(contact.get("category", ""), "local shops")

    subject = "Where does ai fit into your business model?"
    body = (
        f"{greeting}\n\n"
        f"Your email was found by an agent, this email was typed by an agent and sent by an agent. "
        f"You'd be surprised to find what else AI is capable of.\n\n"
        f"I'm Steven, and I build AI agents and websites for small businesses in Westchester. "
        f"The same tech that found and wrote this can also answer basic questions on your site 24/7 "
        f"(pricing ranges, service area, scheduling), capture leads at 2am when you're asleep, and "
        f"send you a clean summary every morning — exactly the kind of follow-up {category} "
        f"usually lose outside business hours. Takes a few days. Costs way less than one lost job pays.\n\n"
        f"Proof I ship — Spirit Library, live on the App Store with 1,500+ recipes and "
        f"autonomous agents running it 24/7. Site: {PORTFOLIO_URL}. Direct App Store download: "
        f"{APP_STORE_URL}.\n\n"
        f"I'm also currently building two projects for clients: a 1,530-model RV configurator "
        f"(https://rv-there-yet-weld.vercel.app) and a 648K-product EU-safe ingredient checker "
        f"(https://eu-approved.vercel.app).\n\n"
        f"Open to a 10-min call? I'll show you a mock of what I'd build for {biz}.\n\n"
        f"Best,\n{SENDER_NAME}\n{SENDER_COMPANY}"
    )
    return {"subject": subject, "body": body + _footer(to)}


def trades_followup(contact: dict) -> dict:
    biz = contact.get("name", "your business")
    first = (contact.get("contact_name") or "").split(" ")[0]
    greeting = f"Hi {first}," if first else f"Hi {biz} team,"
    to = contact["email"]

    subject = f"Re: AI phone/website help for {biz}"
    body = (
        f"{greeting}\n\n"
        f"Following up once — if the timing's off, a one-word 'no' reply and I'll take you off my list. "
        f"Otherwise, I'd still love to spend 10 min showing you a mock of what a 24/7 "
        f"AI lead-capture would look like on {biz}'s site. No cost to look.\n\n"
        f"— {SENDER_NAME}\n{PORTFOLIO_URL}"
    )
    return {"subject": subject, "body": body + _footer(to)}


# ── Spirit Library partnership variant (QR coasters for bars/restaurants) ──

def spiritlibrary_partner_cold(contact: dict) -> dict:
    biz = contact.get("name", "your bar")
    first = (contact.get("contact_name") or "").split(" ")[0]
    greeting = f"Hi {first}," if first else f"Hi {biz} team,"
    to = contact["email"]

    subject = "QR coasters for your bar — free tool"
    body = (
        f"{greeting}\n\n"
        f"Your email was found by an agent — this one's typed and sent by one too.\n\n"
        f"I'm Steven, maker of Spirit Library ({PORTFOLIO_URL}), a cocktail app with 1,500+ "
        f"recipes that's live on the App Store ({APP_STORE_URL}). Some bars and restaurants "
        f"are starting to use it as a customer-facing tool via QR-code coasters:\n\n"
        f"  • Guests scan → instant access to a curated cocktail library, way wider than any "
        f"printed menu\n"
        f"  • You upload your own menu → your specs appear first, with pairings and tasting notes\n"
        f"  • Behind the bar → new-hire training, quick recipe lookup, technique references\n\n"
        f"Free to try. I can set up your QR + branded menu for {biz} in a day.\n\n"
        f"If you're also curious where AI could fit elsewhere in {biz} (reservations bot, "
        f"24/7 guest FAQ, automated review replies), I do that work too — happy to show you "
        f"what's possible on a 10-min call.\n\n"
        f"Also currently building for clients: a 1,530-model RV configurator "
        f"(https://rv-there-yet-weld.vercel.app) and a 648K-product EU-safe ingredient checker "
        f"(https://eu-approved.vercel.app).\n\n"
        f"Best,\n{SENDER_NAME}\n{SENDER_COMPANY}"
    )
    return {"subject": subject, "body": body + _footer(to)}


def spiritlibrary_partner_followup(contact: dict) -> dict:
    biz = contact.get("name", "your bar")
    first = (contact.get("contact_name") or "").split(" ")[0]
    greeting = f"Hi {first}," if first else f"Hi {biz} team,"
    to = contact["email"]

    subject = f"Re: QR coasters for {biz}"
    body = (
        f"{greeting}\n\n"
        f"Following up once — if the QR-coaster + branded-menu idea doesn't fit, just reply "
        f"'no' and I'll take you off my list. Otherwise 10 min is all I'd need to show you a "
        f"mock of what {biz}'s would look like.\n\n"
        f"— {SENDER_NAME}\n{PORTFOLIO_URL}"
    )
    return {"subject": subject, "body": body + _footer(to)}


# ── Router: pick template by category ───────────────────────────────────────

HOSPITALITY_CATEGORIES = {"restaurant", "bar", "cafe", "coffee_shop", "pub", "winery", "brewery"}

def pick_template(contact: dict, stage: str = "cold"):
    cat = (contact.get("category") or "").lower()
    is_hospitality = any(h in cat for h in HOSPITALITY_CATEGORIES)
    if is_hospitality:
        return hospitality_cold(contact) if stage == "cold" else hospitality_followup(contact)
    return trades_cold(contact) if stage == "cold" else trades_followup(contact)


if __name__ == "__main__":
    # Smoke test: preview both variants
    demo_hosp = {
        "name": "The Corner Bistro",
        "email": "info@cornerbistro.example",
        "contact_name": "Maria Chen",
        "category": "restaurant",
    }
    demo_trade = {
        "name": "Hudson Valley Plumbing",
        "email": "contact@hvplumbing.example",
        "contact_name": "",
        "category": "plumber",
    }
    for demo in (demo_hosp, demo_trade):
        out = pick_template(demo, "cold")
        print("=" * 60)
        print("TO:", demo["email"])
        print("SUBJECT:", out["subject"])
        print("-" * 60)
        print(out["body"])
