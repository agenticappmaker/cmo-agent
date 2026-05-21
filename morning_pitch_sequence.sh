#!/bin/bash
# Smore Labs — morning pitch sequence
#
# Runs all DRAFT-ONLY outreach pipelines. The auto-send pipelines
# (claudesonnet111, spiritlibraryapp) are driven by engine.py via launchd
# (com.smorelabs.westchester-outreach 10am, com.smorelabs.spiritlibrary-outreach
# 11am) — this script handles the human-review side.
#
# Press + Influencer go through outreach_westchester/drafter.py (the symmetric
# counterpart to engine.py). Distillery + Bev Director are still one-shot
# scrapers — they'll fold into drafter.py once promoted to full sender profiles.
#
# Usage:
#   ./morning_pitch_sequence.sh           # default limit from each profile's daily_max
#   ./morning_pitch_sequence.sh 10        # override limit to 10 each
#
# Output: ~/cmo-agent/logs/morning_sequence_<date>.log + drafts in
#         outreach/press_drafts.json, outreach/influencer_drafts.json,
#         outreach/distillery_outbox.json, outreach/bevdir_outbox.json
set -euo pipefail

LIMIT="${1:-}"  # empty = use profile's daily_max
ROOT="$HOME/cmo-agent"
WX="$ROOT/outreach_westchester"
VENV="$HOME/spirit_venv/bin/python"
LOG="$ROOT/logs/morning_sequence_$(date +%Y%m%d).log"
mkdir -p "$ROOT/logs"

cd "$ROOT"
echo "=== Morning Pitch Sequence — $(date) ===" | tee -a "$LOG"
if [[ -n "$LIMIT" ]]; then
    echo "Limit override: $LIMIT drafts per profile" | tee -a "$LOG"
    LIMIT_FLAG=(--limit "$LIMIT")
else
    echo "Limit: profile daily_max (set in senders/<name>.json)" | tee -a "$LOG"
    LIMIT_FLAG=()
fi
echo "" | tee -a "$LOG"

run_step() {
    local name="$1"; shift
    echo "── $name ──" | tee -a "$LOG"
    if "$@" 2>&1 | tee -a "$LOG"; then
        echo "✓ $name done" | tee -a "$LOG"
    else
        echo "✗ $name failed (continuing)" | tee -a "$LOG"
    fi
    echo "" | tee -a "$LOG"
}

# Profile-driven drafts via drafter.py — same shape as engine.py, just
# for auto_send:false profiles.
run_step "drafter --sender press"      "$VENV" "$WX/drafter.py" --sender press "${LIMIT_FLAG[@]}"
run_step "drafter --sender influencer" "$VENV" "$WX/drafter.py" --sender influencer "${LIMIT_FLAG[@]}"
# Distillery + bev-director are long-running scrapes — only run if not run today
DISTIL_FILE="outreach/targets/distilleries.json"
if [[ ! -f "$DISTIL_FILE" ]] || [[ $(find "$DISTIL_FILE" -mtime +1) ]]; then
    run_step "distillery-hunter" "$VENV" find_distilleries.py
else
    echo "── distillery-hunter — skipped (ran <24h ago) ──" | tee -a "$LOG"
fi
BEVDIR_FILE="outreach/targets/bev_directors.json"
if [[ ! -f "$BEVDIR_FILE" ]] || [[ $(find "$BEVDIR_FILE" -mtime +6) ]]; then
    run_step "bev-director-finder" "$VENV" find_bev_directors.py
else
    echo "── bev-director-finder — skipped (ran <7d ago) ──" | tee -a "$LOG"
fi

echo "=== Sequence complete ===" | tee -a "$LOG"
echo "Review drafts:" | tee -a "$LOG"
echo "  press status:        $VENV $WX/drafter.py --sender press --status" | tee -a "$LOG"
echo "  influencer status:   $VENV $WX/drafter.py --sender influencer --status" | tee -a "$LOG"
echo "  all draft profiles:  $VENV $WX/drafter.py --sender all --status" | tee -a "$LOG"
echo "  press:               jq '.[-5:][] | {to:.to_email, subject}' outreach/press_drafts.json" | tee -a "$LOG"
echo "  influencers:         jq '.[-5:][] | {name, dm:.dm_text}' outreach/influencer_drafts.json" | tee -a "$LOG"
echo "  distillery:          jq '.[-5:][] | {to:.to_email, distillery, tier}' outreach/distillery_outbox.json" | tee -a "$LOG"
echo "  bev-director:        jq '.[-5:][] | {to:.to_email, group, venue_count}' outreach/bevdir_outbox.json" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Auto-send pipelines (run separately via launchd):" | tee -a "$LOG"
echo "  engine claudesonnet111:  $VENV $WX/engine.py --sender claudesonnet111 --dry-run --preview 3" | tee -a "$LOG"
echo "  engine spiritlibraryapp: $VENV $WX/engine.py --sender spiritlibraryapp --dry-run --preview 3" | tee -a "$LOG"
