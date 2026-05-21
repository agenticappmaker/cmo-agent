# Sender Profiles

Each `<profile>.json` declares one outreach pipeline end-to-end: identity, audience, pitch pack, cadence, opt-out, approval gates.

Two entrypoints consume the same profile schema, split by `approval.auto_send`:

| `approval.auto_send` | Entrypoint | What it does |
|---|---|---|
| `true`  | `engine.py --sender <name>`  | Loads profile, sources/filters/sorts leads, SMTP-sends with per-lead personalization + demo URL injection, manages 3-step drip, records bounces. Driven by launchd (`com.smorelabs.westchester-outreach` 10am, `com.smorelabs.spiritlibrary-outreach` 11am). |
| `false` | `drafter.py --sender <name>` | Loads profile, dispatches to the wired `pitch_*.py` (from `integration.queue_writer`), respects `rate_limits.daily_max` against the day's already-drafted count, writes drafts to Gmail Drafts + JSON outbox. Driven by `morning_pitch_sequence.sh` (manual). |

Engine + drafter share the same `load_profile()` shape, the same `--sender <name>` CLI, the same suppression-list semantics. Pick the one that matches `auto_send`.

The engine will hard-exit if you point it at a draft profile (line 431-432: `Profile has auto_send=false — use the drafter path instead.`). The drafter does the symmetric check.

## Schema

```jsonc
{
  "name": "<profile name>",            // unique
  "version": 1,
  "description": "...",
  "identity": {                         // who sends
    "email": "...",
    "from_name": "...",
    "signature": "...",
    "persona_voice": "..."
  },
  "audience": {                         // who receives
    "source": { "type": "obsidian_markdown|csv|sql", "path": "..." },
    "filter": { ... },
    "enrichment": { ... }
  },
  "pitch_pack": {                       // what to say
    "subjects": [...],
    "body_template": "...",
    "category_variants": { ... },
    "proof_assets": { ... }
  },
  "cadence": {                          // when to follow up
    "cold_to_followup_days": 4,
    "max_followups": 1,
    "followup_templates": [...]
  },
  "rate_limits": {                      // pace
    "daily_max": 5, "hourly_max": 2, "seconds_between_sends": 90
  },
  "opt_out": {                          // honor unsubscribe
    "method": "reply_based",
    "honor_window_hours": 24,
    "footer": "...",
    "suppression_list": "state/optout.txt"
  },
  "personalization": {                  // per-lead first-line
    "first_line_generator": { "model": "claude-haiku-4-5-20251001", "cost_per_email_usd": 0.0001 },
    "free_fallback": "...",
    "scrape_at_queue_time": true
  },
  "approval": {                         // human gate
    "auto_send": false,                 // press + influencer always false
    "review_required": true,
    "review_destination": "Gmail Drafts (...)",
    "reason": "..."
  },
  "reply_classification": {             // hook to process_replies + closer
    "delegates_to": "outreach_westchester/process_replies.py",
    "delegates_drafter_to": "outreach_westchester/cmo_drafter.py",
    "delegates_closer_to": "outreach_westchester/reply_closer.py"
  },
  "metrics": {                          // tracking + alerting
    "logging_file": "logs/<profile>_sends.csv",
    "expected_baseline_reply_rate": 0.03,
    "alert_below_reply_rate": 0.01
  },
  "integration": {                      // wires to other tools
    "queue_writer": "cmo-agent/pitch_<profile>.py",
    "morning_sequence_hook": "morning_pitch_sequence.sh",
    "pm_digest_surfaced_in": [...]
  }
}
```

## Profiles

| File | `auto_send` | Entrypoint | Source | Cadence | Notes |
|---|---|---|---|---|---|
| `claudesonnet111.json` | ✅ true  | `engine.py` | `~/axon/state/heuristic_grades.csv` (2,761 graded leads) | cold + 4d followup + 7d breakup | Min grade B. Sort by grade desc. `demo_gate` enabled — `case-study-cloner` agent builds Vercel previews for grade-A+ leads, URLs injected via `{demo_block}` |
| `spiritlibraryapp.json` | ✅ true  | `engine.py` | `targets/master_leads.csv` (hospitality-only filter) | cold + 10d followup + 7d breakup | Sort by has-website + biz-email |
| `press.json`            | ❌ false | `drafter.py` | Apollo press list (Obsidian md) | cold + 3d / 5d followups | `pitch_press.py` writes drafts to Gmail Drafts; Steven reviews |
| `influencer.json`       | ❌ false | `drafter.py` | Apollo influencer list (Obsidian md), ≥10k followers | cold + 4d followup | Tier-aware (micro/mid/macro). Email + IG DM dual path |

## How it links to the rest of the stack

- **Engine** consumes `senders/<profile>.json` → SMTP → logs to `logs/<profile>_emails.csv` → state in `state/<file>` (shared with axon auto-sender + legacy senders for unified pacing/dedup)
- **Drafter** consumes `senders/<profile>.json` → invokes `integration.queue_writer` script → drafts land in `outreach/<profile>_drafts.json` and Gmail Drafts
- **process_replies.py** classifies replies for BOTH auto-send and draft profiles, drafts replies via `cmo_drafter.py`, marks bounces via `record_ndr_bounce()` → state shared
- **reply_closer.py** (launchd `com.smorelabs.reply-closer` daily 08:15) generates closing artifacts (coaster mocks, demo URLs, proposals) for hot replies regardless of which profile they came from
- **PM digest scripts** (`daily_debrief.py`, `pm_report.py`, `marketing_pipeline_digest.py`) surface BOTH lanes in the daily 7am email to `stevensamori@gmail.com`
- **morning_pitch_sequence.sh** orchestrates the drafter side (manual trigger or wire to your own launchd)

## Naming

Profile = the pitch pipeline, NOT just the sending Gmail account. Both `press` and `influencer` use `spiritlibraryapp@gmail.com` as the sending identity but are separate profiles because they have separate pitch packs, cadences, audiences, and approval rules. Don't conflate identity with profile.

## Approval gate is load-bearing

`approval.auto_send: false` is the difference between "draft for Steven" and "blast." Press + influencer profiles must NEVER flip to `true` without explicit Steven sign-off — the reason field on those profiles spells out why.
