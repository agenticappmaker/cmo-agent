# Apollo.io Contact Export Workflow

## Step 1: Generate Search URLs

```bash
cd ~/Documents/cmo-agent
python apollo_scraper.py
```

This creates 20 search URLs saved to `outreach/apollo_search_urls.json`.

## Step 2: Export Contacts from Apollo

For each URL:

1. Open the URL in your browser (make sure you're logged into Apollo.io)
2. Review the search results — Apollo's free tier shows up to 25 contacts per page
3. Click the checkbox at the top to **Select All** on the page
4. Click **Export** -> choose **CSV**
5. Save the downloaded CSV to: `~/Documents/cmo-agent/outreach/apollo_exports/`
6. Use the suggested filename from the script output (e.g., `apollo_bartenders_new_york.csv`)
7. Repeat for the next URL

Tip: Work through 3-5 URLs per session to avoid rate limits on the free tier.

## Step 3: Import and Deduplicate

After saving one or more CSVs:

```bash
cd ~/Documents/cmo-agent
python apollo_import_contacts.py
```

This will:
- Read all CSVs in `outreach/apollo_exports/`
- Extract name, email, job title, company, city
- Deduplicate against existing contacts in `outreach/targets/` and `outreach/scraped_contacts/`
- Save results to `outreach/apollo_contacts/apollo_imported.json` and `.csv`
- Print import stats

## File Locations

| File | Purpose |
|------|---------|
| `apollo_scraper.py` | Generates search URLs |
| `apollo_import_contacts.py` | Imports and deduplicates CSVs |
| `outreach/apollo_search_urls.json` | Generated URLs (JSON) |
| `outreach/apollo_exports/` | Put downloaded CSVs here |
| `outreach/apollo_contacts/apollo_imported.json` | Final imported contacts (JSON) |
| `outreach/apollo_contacts/apollo_imported.csv` | Final imported contacts (CSV) |

## Search Categories

The 20 URLs cover:

- **Bartenders** (5 URLs): bartender, mixologist, bar manager, head bartender
- **F&B Directors** (5 URLs): food & beverage director, F&B manager, beverage director
- **Bar Owners** (5 URLs): bar owner, restaurant owner, proprietor, founder
- **All Titles Combined** (5 URLs): broad search across NY, LA, Chicago, Miami, SF

Cities: New York, Los Angeles, Chicago, Miami, San Francisco, Austin, Nashville, Seattle, Portland, Denver
