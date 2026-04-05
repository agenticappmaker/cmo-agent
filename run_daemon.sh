#!/bin/bash
cd /Users/claudecode/Documents/cmo-agent
while true; do
  venv/bin/python main.py daemon spirit-library --platform instagram
  echo "Daemon crashed, restarting in 30s..."
  sleep 30
done
