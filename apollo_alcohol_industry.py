#!/usr/bin/env python3
"""
Apollo: Find alcohol industry contacts for Spirit Library outreach.
Generates Apollo search URLs for batch export.
(Apollo free plan doesn't have API access, so we generate URLs for manual export)

Run: python3 apollo_alcohol_industry.py
Output: Prints URLs to open in browser, CSVs saved to outreach/apollo_exports/
"""

import webbrowser
import os

BASE = "https://app.apollo.io/people"

# Search queries for alcohol industry contacts
SEARCHES = [
    {
        "name": "Bar Owners & Managers — Top 50 US Cities",
        "params": {
            "personTitles[]": ["Owner", "General Manager", "Bar Manager", "Beverage Director", "Head Bartender"],
            "organizationIndustryTagIds[]": ["5567cd4e7369643b72b70000"],  # Food & Beverages
            "personLocations[]": ["United States"],
            "contactEmailStatus[]": ["verified"],
        },
        "notes": "Sort by company size. Export first 200.",
    },
    {
        "name": "Spirits Brand Marketing Teams",
        "params": {
            "personTitles[]": ["Marketing Manager", "Brand Manager", "Marketing Director", "CMO", "VP Marketing", "Brand Ambassador"],
            "qOrganizationName": "spirits OR distillery OR vodka OR whiskey OR gin OR rum OR tequila",
            "personLocations[]": ["United States"],
            "contactEmailStatus[]": ["verified"],
        },
        "notes": "Target: Hendrick's, Aviation, Patron, Buffalo Trace, Maker's Mark, Campari, Diageo, Pernod Ricard, Bacardi, Brown-Forman",
    },
    {
        "name": "Cocktail / Mixology Influencers",
        "params": {
            "personTitles[]": ["Content Creator", "Influencer", "Blogger", "Brand Ambassador", "Mixologist"],
            "qKeywords": "cocktail OR mixology OR bartender OR spirits",
            "personLocations[]": ["United States"],
            "contactEmailStatus[]": ["verified"],
        },
        "notes": "Look for 10K+ followers on Instagram/TikTok",
    },
    {
        "name": "Beverage Distributors & Wholesalers",
        "params": {
            "personTitles[]": ["Sales Manager", "Account Executive", "Territory Manager", "VP Sales"],
            "organizationIndustryTagIds[]": ["5567cd4e7369643b72b70000"],
            "qOrganizationName": "distributor OR wholesale OR beverage OR wine and spirits",
            "personLocations[]": ["United States"],
            "contactEmailStatus[]": ["verified"],
        },
        "notes": "Southern Glazer's, Republic National, Breakthru Beverage, RNDC",
    },
    {
        "name": "Restaurant Group Beverage Directors",
        "params": {
            "personTitles[]": ["Beverage Director", "Wine Director", "Director of Operations", "Corporate Chef"],
            "organizationIndustryTagIds[]": ["5567cd4e7369643b72b70000"],
            "organizationNumEmployeesRanges[]": ["51,200", "201,500", "501,1000", "1001,5000"],
            "personLocations[]": ["United States"],
            "contactEmailStatus[]": ["verified"],
        },
        "notes": "Target multi-location restaurant groups",
    },
    {
        "name": "Cocktail Competition & Event Organizers",
        "params": {
            "qKeywords": "cocktail competition OR bartender competition OR spirits award OR Tales of the Cocktail OR Speed Rack",
            "personLocations[]": ["United States"],
            "contactEmailStatus[]": ["verified"],
        },
        "notes": "Tales of the Cocktail, Speed Rack, USBG, Diageo World Class",
    },
    {
        "name": "Spirits PR & Communications",
        "params": {
            "personTitles[]": ["PR Manager", "Communications Director", "Public Relations", "Media Relations"],
            "qKeywords": "spirits OR wine OR beverage OR cocktail OR distillery",
            "personLocations[]": ["United States"],
            "contactEmailStatus[]": ["verified"],
        },
        "notes": "PR agencies that handle spirits accounts",
    },
    {
        "name": "Cocktail Recipe / Food Media Writers",
        "params": {
            "personTitles[]": ["Editor", "Writer", "Journalist", "Contributor", "Food Editor", "Drinks Editor"],
            "qKeywords": "cocktail OR spirits OR beverage OR mixology OR drinks",
            "personLocations[]": ["United States"],
            "contactEmailStatus[]": ["verified"],
        },
        "notes": "Punch, Imbibe, VinePair, Eater, Bon Appetit drinks section, Food & Wine",
    },
]

def main():
    print("=" * 60)
    print("Apollo Alcohol Industry Contact Search URLs")
    print("=" * 60)
    print()
    print("Open these URLs in Apollo, filter results, and export CSVs.")
    print(f"Save CSVs to: ~/cmo-agent/outreach/apollo_exports/")
    print()

    os.makedirs(os.path.expanduser("~/cmo-agent/outreach/apollo_exports"), exist_ok=True)

    for i, search in enumerate(SEARCHES, 1):
        print(f"[{i}/{len(SEARCHES)}] {search['name']}")
        print(f"  Notes: {search['notes']}")

        # Build URL (simplified — Apollo URL params are complex)
        url = f"{BASE}#"
        for key, values in search["params"].items():
            if isinstance(values, list):
                for v in values:
                    url += f"&{key}={v}"
            else:
                url += f"&{key}={values}"

        print(f"  URL: {url[:120]}...")
        print()

    print("=" * 60)
    print(f"Target: 500+ verified email addresses across {len(SEARCHES)} categories")
    print("After exporting, run: python3 apollo_import_csv.py")
    print("Then n8n will auto-send outreach sequences")


if __name__ == "__main__":
    main()
