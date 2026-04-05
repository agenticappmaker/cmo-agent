#!/bin/bash
cd /Users/claudecode/Documents/cmo-agent
source /Users/claudecode/Documents/cmo-agent/venv/bin/activate
exec python main.py daemon spirit-library --platform instagram
