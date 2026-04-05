#!/bin/bash
cd /Users/claudecode/Documents/cmo-agent
source venv/bin/activate
python main.py post-now spirit-library --platform instagram >> logs/cron.log 2>&1
