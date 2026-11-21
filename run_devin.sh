#!/bin/bash
# Step 3: hand one scoped task to a Devin Cloud session.
# Needs the Devin CLI (brew install --cask devin-cli) signed in to a Pro account.
# Usage: ./run_devin.sh out/tasks/01-<name>.md
set -euo pipefail
task="$1"
devin --cloud -- "$(cat "$task")

When the PR is open, print its URL on the last line."
echo "Add the PR URL to pilot_prs.txt, then run: python3 scorecard.py"
