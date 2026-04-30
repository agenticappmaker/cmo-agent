#!/bin/bash
cd /Users/claudecode/Documents/cmo-agent
source .env 2>/dev/null
export ANTHROPIC_API_KEY OPENAI_API_KEY META_ACCESS_TOKEN META_PAGE_ACCESS_TOKEN META_APP_ID META_APP_SECRET IMGBB_API_KEY
venv/bin/python -u main.py post-now spirit-library --platform instagram >> logs/cron.log 2>&1
